# SPDX-License-Identifier: Apache-2.0
"""Optional nexus integration shim for palinex.

This module is the bridge between palinex (the surface emission library)
and nexus (the knowledge / catalog / T3 substrate). Imported lazily so
palinex itself never gains a hard dependency on nexus — only the
``[nexus]`` extra needs `conexus` installed.

The exported callable is ``chash_resolver(chash)`` which the palinex
MCP server, HTTP sidecar, and any user code can pass to
``wrap_as_mcp_ui_resource`` as its ``chash_resolver=`` argument.
Returns chunk text from nexus T3 when the input looks like a chash
(32 lowercase hex chars per RDR-108) and the chunk exists. Returns
``None`` for anything else.

When nexus is not installed, ``chash_resolver`` raises a clear
``ImportError`` on first invocation rather than at import time, so
callers that don't actually need nexus resolution don't pay the
import cost.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Sentinel used by lazy_chash_resolver to avoid re-importing nexus on every
# call. Set to True after a successful import; set to the ImportError
# instance after a failed one.
_NEXUS_AVAILABLE: bool | ImportError = False


def chash_resolver(chash: str, *, collection: str = "knowledge") -> str | None:
    """Resolve a candidate chash string to chunk text via nexus T3.

    Per RDR-108, T3 document IDs are ``chunk_text_hash[:32]`` — 32-char
    lowercase hex. This resolver:

    1. Validates the input string's shape (rejects non-chash inputs
       without exception so it can be passed arbitrary data-model
       strings via ``wrap_as_mcp_ui_resource``).
    2. Looks up the entry in nexus T3 under the given collection.
    3. Returns the entry's ``content`` field if found, else ``None``.

    Raises ImportError on the first call if nexus is not installed
    (i.e. ``pip install palinex[nexus]`` was not performed).
    """
    if not isinstance(chash, str) or len(chash) != 32:
        return None
    if not all(c in "0123456789abcdef" for c in chash):
        return None

    nexus_mod = _load_nexus()
    if isinstance(nexus_mod, ImportError):
        raise nexus_mod

    try:
        t3 = nexus_mod["get_t3"]()
        col_name = nexus_mod["t3_collection_name"](collection, t3=t3)
        entry = t3.get_by_id(col_name, chash)
        if entry is None:
            return None
        content = entry.get("content")
        return content if isinstance(content, str) else None
    except Exception as e:
        logger.warning(
            "palinex.nexus_bridge.chash_resolver: lookup failed for %s: %s",
            chash[:12],
            e,
        )
        return None


def _load_nexus() -> dict | ImportError:
    """Lazy-import nexus internals; cache the result.

    Returns either a dict of the symbols we use or an ImportError to be
    raised by the caller. Cached on the module so subsequent calls are
    O(1) regardless of import success or failure.
    """
    global _NEXUS_AVAILABLE
    if _NEXUS_AVAILABLE is True:
        from nexus.mcp_infra import get_t3
        from nexus.corpus import t3_collection_name
        return {"get_t3": get_t3, "t3_collection_name": t3_collection_name}
    if isinstance(_NEXUS_AVAILABLE, ImportError):
        return _NEXUS_AVAILABLE
    try:
        from nexus.mcp_infra import get_t3
        from nexus.corpus import t3_collection_name
        _NEXUS_AVAILABLE = True
        return {"get_t3": get_t3, "t3_collection_name": t3_collection_name}
    except ImportError as e:
        msg = (
            "palinex.nexus_bridge requires the [nexus] extra. Install with:\n"
            "  pip install palinex[nexus]\n"
            f"Underlying ImportError: {e}"
        )
        err = ImportError(msg)
        _NEXUS_AVAILABLE = err
        return err


def is_available() -> bool:
    """Return True if nexus is importable (no exception on first try).

    Useful for callers that want to feature-detect nexus availability
    without paying the cost of a raised ImportError.
    """
    return not isinstance(_load_nexus(), ImportError)
