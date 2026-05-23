# SPDX-License-Identifier: Apache-2.0
"""Structural sanity check for RDR-004 (trust-gate signature design).

The Phase 4b implementation will live behind palinex-4ae; until that ships,
this test catches drift in the design doc itself — missing sections,
removed normative fields, broken cross-references to RDR-001 and the
postMessage RPC spec. Once Phase 4b lands, this file gets replaced (or
joined) by behavioural tests in test_signing.py / test_trust_gate.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RDR_PATH = REPO_ROOT / "docs" / "rdr" / "rdr-004-trust-gate-signature.md"
RDR_INDEX_PATH = REPO_ROOT / "docs" / "rdr" / "README.md"


@pytest.fixture(scope="module")
def rdr_text() -> str:
    assert RDR_PATH.exists(), f"RDR-004 missing: {RDR_PATH}"
    return RDR_PATH.read_text(encoding="utf-8")


def test_rdr_004_listed_in_index() -> None:
    index = RDR_INDEX_PATH.read_text(encoding="utf-8")
    assert "[004]" in index, "RDR-004 must be linked from docs/rdr/README.md"
    assert "rdr-004-trust-gate-signature.md" in index


def test_rdr_004_frontmatter_has_required_fields(rdr_text: str) -> None:
    for field in ("id: RDR-004", "type: Security", "status:", "related_rdrs: [RDR-001]"):
        assert field in rdr_text, f"RDR-004 frontmatter missing: {field!r}"


@pytest.mark.parametrize(
    "section",
    [
        "## Problem Statement",
        "## Context",
        "## Decision",
        "### Approach",
        "## Alternatives Considered",
        "## Trade-offs",
        "## Implementation Plan",
        "## Test Plan",
        "## Validation",
        "## References",
        "## Revision History",
    ],
)
def test_rdr_004_has_canonical_section(rdr_text: str, section: str) -> None:
    assert section in rdr_text, f"RDR-004 missing canonical section: {section}"


@pytest.mark.parametrize(
    "field",
    [
        "producerId",
        "producerName",
        "publicKey",
        "algorithm",
        "actions",
        "issuedAt",
        "expiresAt",
        "nonce",
        "signature",
    ],
)
def test_rdr_004_documents_trust_block_field(rdr_text: str, field: str) -> None:
    assert field in rdr_text, f"RDR-004 missing trust-block field: {field}"


def test_rdr_004_documents_ed25519_choice(rdr_text: str) -> None:
    assert "Ed25519" in rdr_text
    assert "RFC 8032" in rdr_text


def test_rdr_004_documents_jcs_canonicalization(rdr_text: str) -> None:
    assert re.search(r"RFC 8785|JCS|canonicalization", rdr_text, re.I), \
        "RDR-004 must reference RFC 8785 JCS for canonicalization"


def test_rdr_004_documents_replay_protection(rdr_text: str) -> None:
    """Critical critic finding: replay-within-window must have a row."""
    assert "Replay" in rdr_text, "RDR-004 must address replay attacks"
    assert re.search(r"nonce", rdr_text, re.I), \
        "RDR-004 must specify the nonce mechanism for replay protection"


def test_rdr_004_documents_gap_5_param_scoping(rdr_text: str) -> None:
    """Critical critic finding: param-level confused-deputy must be acknowledged."""
    assert "Gap 5" in rdr_text or "param_constraints" in rdr_text, \
        "RDR-004 must acknowledge param-level confused-deputy limitation"
    assert "palinex-rjm" in rdr_text, \
        "RDR-004 must reference the Gap 5 follow-up bead"


def test_rdr_004_documents_gap_6_operator_ux(rdr_text: str) -> None:
    """Significant critic finding: operator UX gap acknowledged + follow-up bead."""
    assert "Gap 6" in rdr_text or "log-only → deny" in rdr_text
    assert "palinex-ciy" in rdr_text, \
        "RDR-004 must reference the Gap 6 follow-up bead"


def test_rdr_004_documents_effective_expiry_formula(rdr_text: str) -> None:
    """Significant critic finding: dual freshness paths need a precedence rule."""
    assert "effective_expiry" in rdr_text or re.search(
        r"min\(expiresAt", rdr_text,
    ), "RDR-004 must specify effective_expiry = min(expiresAt, issuedAt + max_age_seconds)"


def test_rdr_004_documents_renderer_must_verify(rdr_text: str) -> None:
    """Significant critic finding: renderer-local actions need MUST-verify."""
    # The renderer side has a MUST-verify rule when pubkey is available.
    assert re.search(
        r"renderer\s*\*?\*?.*MUST\*?\*? verify",
        rdr_text,
        re.S,
    ), "RDR-004 must require renderer-side verification when pubkey is available"


def test_rdr_004_documents_trust_store_keyed_by_producer_id(rdr_text: str) -> None:
    """Significant critic finding: trust store lookup ambiguity."""
    assert re.search(
        r"trust store is\s*\*\*?keyed by `producerId`",
        rdr_text,
    ), "RDR-004 must specify trust store is keyed by producerId, not producerName"


def test_rdr_004_references_phase_4b_bead(rdr_text: str) -> None:
    assert "palinex-4ae" in rdr_text, "RDR-004 must reference Phase 4b bead"


def test_rdr_004_cross_references_rdr_001(rdr_text: str) -> None:
    assert "RDR-001" in rdr_text
    assert re.search(r"Item 7|action allowlist", rdr_text, re.I)


def test_rdr_004_cross_references_postmessage_rpc_spec(rdr_text: str) -> None:
    assert "postmessage-rpc.md" in rdr_text or "postMessage RPC" in rdr_text


def test_rdr_004_has_three_scenarios(rdr_text: str) -> None:
    """Per bead requirement: design must include three concrete examples."""
    for scenario in (
        "Scenario A",
        "Scenario B",
        "Scenario C",
    ):
        assert scenario in rdr_text, f"RDR-004 missing concrete {scenario}"


def test_rdr_004_has_revision_history_entry_for_critique(rdr_text: str) -> None:
    """The substantive-critic gate must leave a paper trail."""
    assert re.search(
        r"substantive-critic", rdr_text, re.I,
    ), "RDR-004 revision history must record the substantive-critic gate"