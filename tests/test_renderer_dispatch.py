# SPDX-License-Identifier: Apache-2.0
"""Source-conformance tests for web/index.html renderer dispatch.

Regression guard for palinex-lc9 (live-shakeout finding 2026-05-23):
the renderer's handleFunctionCall MUST dispatch extension methods using
the actual action name as `method`, not wrap them as a meta-method
`functionCall`. RDR-001 §Item 7 mandates this; RDR-004's trust gate
relies on it for per-method allowlisting.

Pre-fix behaviour (broken in 0.4.0):
    default:
      hostBridge('functionCall', { call: fn.call, args, sourceId });

Post-fix behaviour (this test enforces):
    default:
      hostBridge(fn.call, { ...args, sourceId });
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDERER_HTML = REPO_ROOT / "web" / "index.html"


@pytest.fixture(scope="module")
def renderer_text() -> str:
    return RENDERER_HTML.read_text(encoding="utf-8")


def test_renderer_does_not_wrap_extension_methods_as_function_call(renderer_text: str) -> None:
    """palinex-lc9 fix: the meta-method dispatch MUST be gone.

    The pre-fix pattern `hostBridge('functionCall', { call: fn.call, ... })`
    breaks RDR-001 §Item 7 and RDR-004's trust gate intersection on method
    names. The post-fix pattern uses `fn.call` as the method directly.
    """
    assert not re.search(
        r"hostBridge\(\s*['\"]functionCall['\"]\s*,\s*\{\s*call:\s*fn\.call",
        renderer_text,
    ), (
        "renderer regressed to pre-palinex-lc9 dispatch wrapping extension "
        "methods as method='functionCall'; the trust gate (RDR-004) can no "
        "longer enforce per-method allowlisting against the producer's "
        "trust.actions list. Restore: hostBridge(fn.call, { ...args, sourceId })"
    )


def test_renderer_dispatches_by_action_name(renderer_text: str) -> None:
    """Post-fix renderer MUST call hostBridge with fn.call as the method name."""
    assert re.search(
        r"default:\s*\n(?:\s*//[^\n]*\n)*\s*hostBridge\(\s*fn\.call\s*,",
        renderer_text,
    ), (
        "handleFunctionCall default branch MUST dispatch with fn.call as "
        "the method name (RDR-001 §Item 7)"
    )


def test_renderer_first_class_actions_use_correct_method_names(renderer_text: str) -> None:
    """The three first-class actions MUST keep their direct-dispatch shape.

    Regression guard: the palinex-lc9 fix changed only the default branch.
    openUrl and copyToClipboard stay renderer-local (no bridge call). openChash
    stays a bridge call with method='openChash'.
    """
    # openChash should still appear as the literal method name in a hostBridge call.
    assert re.search(
        r"hostBridge\(\s*['\"]openChash['\"]\s*,", renderer_text,
    ), "openChash MUST still dispatch with method='openChash'"
    # openUrl resolved locally — should NOT appear as a hostBridge method.
    assert not re.search(
        r"hostBridge\(\s*['\"]openUrl['\"]", renderer_text,
    ), "openUrl is renderer-local; MUST NOT be dispatched via the bridge"
    # copyToClipboard resolved locally — same.
    assert not re.search(
        r"hostBridge\(\s*['\"]copyToClipboard['\"]", renderer_text,
    ), "copyToClipboard is renderer-local; MUST NOT be dispatched via the bridge"


def test_renderer_under_loc_ceiling(renderer_text: str) -> None:
    """html-tool-patterns: warn at 600, hard at 900."""
    lines = renderer_text.splitlines()
    assert len(lines) < 900, (
        f"web/index.html at {len(lines)} lines exceeds the 900 hard ceiling; "
        "consider extracting the 18-component dispatch into a small helper"
    )
