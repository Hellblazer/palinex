# SPDX-License-Identifier: Apache-2.0
"""FastMCP server exposing ``render_surface`` — the palinex Claude Code
plugin's primary tool.

Wraps an a2ui v0.9 surface payload as an MCP UI resource so Claude Code
renders it inline as a sandboxed iframe in the chat. Chash references
in the payload's data model are resolved against nexus T3 automatically
when the ``[nexus]`` extra is installed; without it, the payload is
emitted as-is (callers that want resolution pre-substitute themselves).

Run via ``python -m palinex.mcp`` (or directly via the Claude Code
plugin's ``.mcp.json`` registration).
"""
from __future__ import annotations

import json
import secrets
from typing import Any

from mcp.server.fastmcp import FastMCP

from palinex import wrap_as_mcp_ui_resource
from palinex.nexus_bridge import chash_resolver, is_available as _nexus_available

mcp = FastMCP("palinex")


@mcp.tool()
def render_surface(
    payload: str | dict[str, Any],
    *,
    title: str = "palinex surface",
    collection: str = "knowledge",
    renderer_url: str = "https://hellblazer.github.io/palinex/index.html",
) -> dict[str, Any]:
    """Wrap an a2ui v0.9 surface payload as an inline MCP UI resource.

    Claude Code receives the returned resource and renders the HTML
    inline as a sandboxed iframe. The user sees the surface (citation
    cards, RDR audit dashboards, plan inspectors, subagent findings,
    whatever the payload describes) directly in the chat.

    When the palinex ``[nexus]`` extra is installed AND nexus is
    importable, chash references in the payload's data model
    (32-char lowercase-hex strings, per RDR-108) are looked up in
    nexus T3 and substituted with the actual chunk text. Button
    actions of type ``openChash`` are rewritten to
    ``copyToClipboard`` carrying the resolved text. The resulting
    page is a static snapshot — no live host bridge needed.

    Without the [nexus] extra, the payload is wrapped as-is. Callers
    that want chash resolution should pre-substitute the data model
    themselves before calling this tool.

    Args:
        payload: a2ui v0.9 surface payload. Accepts a dict (envelope
            shape ``{version, messages: [...]}`` or flat shape
            ``{components, dataModel}``) or a JSON string. JSON
            strings are convenient when upstream tools return text.
        title: HTML ``<title>`` for the wrapper page. Defaults to
            ``"palinex surface"``.
        collection: nexus T3 collection to look up chashes in (when
            nexus integration is available). Defaults to
            ``"knowledge"``.
        renderer_url: URL of the palinex renderer to embed. Defaults
            to the hosted GitHub Pages renderer; override to point at
            a local copy for offline work.

    Returns:
        MCP UI resource dict: ``{type: "resource", resource:
        {uri: "ui://palinex/<id>", mimeType: "text/html",
        text: <wrapper HTML>}}``.

    Raises:
        ValueError: if ``payload`` is a string that can't be parsed
            as JSON, or if it isn't a dict / valid JSON string.
    """
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as e:
            raise ValueError(f"payload string is not valid JSON: {e}") from e
    if not isinstance(payload, dict):
        raise ValueError(
            f"payload must be a dict or JSON string; got {type(payload).__name__}"
        )

    resolver = None
    if _nexus_available():
        # Closure binds collection — keeps the user's choice across calls
        # without changing palinex.wrap_as_mcp_ui_resource's signature.
        def resolver(chash: str) -> str | None:
            return chash_resolver(chash, collection=collection)

    html = wrap_as_mcp_ui_resource(
        payload,
        chash_resolver=resolver,
        renderer_url=renderer_url,
        title=title,
    )
    return {
        "type": "resource",
        "resource": {
            "uri": f"ui://palinex/{secrets.token_hex(8)}",
            "mimeType": "text/html",
            "text": html,
        },
    }


def main() -> None:
    """Entry point — runs the FastMCP server over stdio."""
    mcp.run()
