# SPDX-License-Identifier: Apache-2.0
"""Source-conformance tests for web/host-bridge.html backend method registry.

RDR-001 Phase 3 Item 2 (palinex-i10) and Item 3 (palinex-xwr) commit to
reference-bridge handlers for ``runSkill`` (nexus-specific) and ``openFile``
(editor-host-specific) in both the mock and HTTP backends. These tests
catch silent removal or rename via regex match against the HTML source,
matching the existing test_protocol_spec.py / test_trust_gate.py pattern
(no JS runtime in pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOST_BRIDGE_HTML = REPO_ROOT / "web" / "host-bridge.html"


@pytest.fixture(scope="module")
def bridge_text() -> str:
    return HOST_BRIDGE_HTML.read_text(encoding="utf-8")


# ---- Backend registry shape ----------------------------------------------


def test_mock_backend_declared(bridge_text: str) -> None:
    assert "MOCK_BACKEND" in bridge_text, "MOCK_BACKEND object must exist"


def test_http_backend_declared(bridge_text: str) -> None:
    assert "HTTP_BACKEND" in bridge_text, "HTTP_BACKEND factory must exist"


# ---- runSkill (palinex-i10, RDR-001 Phase 3 Item 2) ----------------------


def test_mock_backend_implements_run_skill(bridge_text: str) -> None:
    """MOCK_BACKEND.runSkill MUST exist for the demo to work without a sidecar."""
    mock_block = re.search(
        r"const MOCK_BACKEND\s*=\s*\{(.+?)\n\};", bridge_text, re.S,
    )
    assert mock_block, "MOCK_BACKEND must be defined as `const MOCK_BACKEND = { … };`"
    assert "runSkill" in mock_block.group(1), \
        "MOCK_BACKEND must declare a runSkill handler"


def test_http_backend_implements_run_skill(bridge_text: str) -> None:
    """HTTP_BACKEND.runSkill MUST POST to {baseUrl}/skill/{name}."""
    http_block = re.search(
        r"const HTTP_BACKEND\s*=\s*\([^)]*\)\s*=>\s*\(\{(.+?)\n\}\);", bridge_text, re.S,
    )
    assert http_block, "HTTP_BACKEND must be defined as `const HTTP_BACKEND = (baseUrl) => ({…});`"
    body = http_block.group(1)
    assert "runSkill" in body, "HTTP_BACKEND must declare a runSkill handler"
    assert "/skill/" in body, "HTTP_BACKEND.runSkill must reference /skill/ path"


def test_run_skill_param_shape(bridge_text: str) -> None:
    """runSkill params shape is {name: string, args?: object}."""
    # Mock handler signature
    assert re.search(
        r"runSkill\(\{\s*name,\s*args\s*\}\)", bridge_text,
    ), "runSkill MUST take destructured {name, args} params"


# ---- openFile (palinex-xwr, RDR-001 Phase 3 Item 3) ----------------------


def test_mock_backend_implements_open_file(bridge_text: str) -> None:
    """MOCK_BACKEND.openFile MUST exist as the documented editor-host extension."""
    assert re.search(
        r"MOCK_BACKEND\s*=\s*\{[\s\S]*?openFile", bridge_text,
    ), "MOCK_BACKEND must declare an openFile handler"


def test_http_backend_implements_open_file(bridge_text: str) -> None:
    """HTTP_BACKEND.openFile MUST POST to {baseUrl}/file/open."""
    assert re.search(
        r"openFile\([^)]*\)[\s\S]*?/file/open", bridge_text,
    ), "HTTP_BACKEND.openFile must POST to {baseUrl}/file/open"


def test_open_file_param_shape(bridge_text: str) -> None:
    """openFile params shape is {path: string, line?: number, column?: number}."""
    assert re.search(
        r"openFile\(\{\s*path,\s*line,\s*column\s*\}\)", bridge_text,
    ), "openFile MUST take destructured {path, line, column} params"


def test_open_file_mock_returns_documented_shape(bridge_text: str) -> None:
    """Mock openFile returns {opened: false, reason, message} so callers can branch."""
    assert "opened: false" in bridge_text, \
        "mock openFile must return opened: false to signal no-op"
    assert re.search(r"reason:\s*'mock-backend'", bridge_text), \
        "mock openFile must tag the reason for the no-op"


# ---- Documentation: three resolver paths ---------------------------------


def test_backend_comment_documents_resolver_paths(bridge_text: str) -> None:
    """Per palinex-xwr §5: comment must document the three resolver paths."""
    for keyword in ("MOCK_BACKEND", "HTTP_BACKEND", "hostBridgeResolver"):
        assert keyword in bridge_text, f"resolver-path docs must mention {keyword}"


# ---- LOC budget guard (html-tool-patterns) --------------------------------


def test_host_bridge_under_warn_threshold(bridge_text: str) -> None:
    """html-tool-patterns warn at 600 LOC, hard ceiling 900."""
    lines = bridge_text.splitlines()
    assert len(lines) < 900, (
        f"host-bridge.html at {len(lines)} lines exceeds the 900 hard ceiling"
    )
    # Soft warning at 600 — print a note but don't fail (mirrors the
    # pre-commit hook convention).
    if len(lines) > 600:
        # Soft cap exceeded but well under hard ceiling; flag for future
        # refactor consideration. Tests still pass.
        pytest.skip(
            f"host-bridge.html at {len(lines)} lines exceeds the 600 LOC warn "
            "threshold (hard ceiling 900); consider extracting trust-gate "
            "primitives into a shared module if growth continues"
        )
