# SPDX-License-Identifier: Apache-2.0
"""Parity checks across palinex's release manifests.

Following the pattern established in Hellblazer/nexus and documented in the
``global_directives/marketplace-pinned-source-release-model`` directive, every
release-time version-bearing manifest in the repo must agree:

- ``pyproject.toml`` ``[project] version`` — canonical source of truth
- ``.claude-plugin/marketplace.json`` ``metadata.version``
- ``.claude-plugin/marketplace.json`` ``plugins[].version``
- ``.claude-plugin/marketplace.json`` ``plugins[].source.ref`` — the git tag
  that Claude Code will check out at install time; pinned to a release tag
  so main HEAD can advance without changing the user-installed plugin
- ``plugin/.claude-plugin/plugin.json`` ``version`` — what users see after
  install
- ``mcpb/manifest.json`` ``version`` and ``mcpb/pyproject.toml`` ``version``
  — Claude Desktop .mcpb extension bundle (RDR-003 §Item 3a)

If a future release bumps the canonical version but forgets one of the
mirrors, CI catches it here rather than at install time.

Source-shape sanity: marketplace.json plugins[].source MUST be the
``git-subdir`` object form (not a relative path string), because the
relative-path form ships main HEAD to users on every push — the bug the
pinned-source model was introduced to avoid.
"""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
PLUGIN_JSON = REPO_ROOT / "plugin" / ".claude-plugin" / "plugin.json"
MCPB_PYPROJECT = REPO_ROOT / "mcpb" / "pyproject.toml"
MCPB_MANIFEST = REPO_ROOT / "mcpb" / "manifest.json"


def _pyproject_version() -> str:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def _marketplace() -> dict:
    return json.loads(MARKETPLACE.read_text())


class TestMarketplaceStructure:
    def test_marketplace_present(self) -> None:
        assert MARKETPLACE.exists(), f"missing {MARKETPLACE}"

    def test_plugins_list_nonempty(self) -> None:
        assert _marketplace().get("plugins"), "marketplace.json has no plugins"

    def test_plugin_source_is_object_not_relative_path(self) -> None:
        """Source must be the git-subdir object form, not a relative-path string.

        The relative-path form (e.g. "./plugin") ships main HEAD to every
        user on every push — the bug the pinned-source release model
        explicitly avoids. See global_directives/marketplace-pinned-source-release-model.
        """
        for plugin in _marketplace()["plugins"]:
            src = plugin["source"]
            assert isinstance(src, dict), (
                f"plugin {plugin['name']!r} source is a relative-path string "
                f"({src!r}); convert to the git-subdir object form pinned to "
                f"a release tag. Relative-path sources ship main HEAD to users "
                f"on every push, defeating the pinned-source release model."
            )
            assert src.get("source") == "git-subdir", (
                f"plugin {plugin['name']!r} source.source is "
                f"{src.get('source')!r}, expected 'git-subdir'"
            )
            assert src.get("url"), f"plugin {plugin['name']!r} missing source.url"
            assert src.get("path"), f"plugin {plugin['name']!r} missing source.path"
            assert src.get("ref"), f"plugin {plugin['name']!r} missing source.ref"

    def test_plugin_source_ref_is_a_tag(self) -> None:
        for plugin in _marketplace()["plugins"]:
            ref = plugin["source"]["ref"]
            assert ref.startswith("v"), (
                f"plugin {plugin['name']!r} source.ref {ref!r} doesn't start "
                f"with 'v'; release tags follow the v<X.Y.Z> convention"
            )


class TestVersionParity:
    def test_metadata_version_matches_pyproject(self) -> None:
        pv = _pyproject_version()
        mv = _marketplace().get("metadata", {}).get("version")
        assert mv == pv, (
            f"marketplace.json metadata.version {mv!r} != pyproject.toml {pv!r}. "
            f"Update marketplace.json when bumping pyproject version."
        )

    def test_plugin_version_matches_pyproject(self) -> None:
        pv = _pyproject_version()
        for plugin in _marketplace()["plugins"]:
            assert plugin.get("version") == pv, (
                f"marketplace.json plugins[{plugin['name']!r}].version "
                f"{plugin.get('version')!r} != pyproject.toml {pv!r}"
            )

    def test_plugin_source_ref_matches_pyproject(self) -> None:
        """marketplace plugins[].source.ref must match pyproject version.

        The pinned-source release model couples version and source.ref: a
        partial bump (e.g. version bumped but source.ref forgotten) would
        ship old code under a new version label. CI rejects that here.
        """
        pv = _pyproject_version()
        for plugin in _marketplace()["plugins"]:
            ref = plugin["source"]["ref"]
            expected = f"v{pv}"
            assert ref == expected, (
                f"marketplace.json plugins[{plugin['name']!r}].source.ref "
                f"{ref!r} != v{pv} (derived from pyproject.toml). When bumping "
                f"version, update BOTH plugins[].version AND plugins[].source.ref."
            )

    def test_plugin_json_version_matches_pyproject(self) -> None:
        pv = _pyproject_version()
        pj = json.loads(PLUGIN_JSON.read_text())
        assert pj["version"] == pv, (
            f"plugin/.claude-plugin/plugin.json version {pj['version']!r} "
            f"!= pyproject.toml {pv!r}"
        )

    def test_mcpb_pyproject_version_matches_root(self) -> None:
        pv = _pyproject_version()
        with MCPB_PYPROJECT.open("rb") as f:
            mcpb_v = tomllib.load(f)["project"]["version"]
        assert mcpb_v == pv, (
            f"mcpb/pyproject.toml version {mcpb_v!r} != root pyproject.toml {pv!r}. "
            f"The .mcpb bundle versioning tracks palinex versioning (RDR-003 §Item 3a)."
        )

    def test_mcpb_manifest_version_matches_root(self) -> None:
        pv = _pyproject_version()
        manifest_v = json.loads(MCPB_MANIFEST.read_text())["version"]
        assert manifest_v == pv, (
            f"mcpb/manifest.json version {manifest_v!r} != root pyproject.toml {pv!r}"
        )


class TestPluginSourceMatchesRepoLayout:
    def test_plugin_source_path_exists(self) -> None:
        """The directory named by source.path must exist at the repo root.

        Catches typos like path: "plugin" when the dir was renamed.
        """
        for plugin in _marketplace()["plugins"]:
            sub = REPO_ROOT / plugin["source"]["path"]
            assert sub.is_dir(), (
                f"plugin {plugin['name']!r} source.path {plugin['source']['path']!r} "
                f"does not exist at repo root {REPO_ROOT}"
            )

    def test_plugin_source_path_has_claude_plugin_dir(self) -> None:
        """A valid plugin dir must contain .claude-plugin/plugin.json."""
        for plugin in _marketplace()["plugins"]:
            manifest = REPO_ROOT / plugin["source"]["path"] / ".claude-plugin" / "plugin.json"
            assert manifest.exists(), (
                f"plugin {plugin['name']!r} source.path missing "
                f".claude-plugin/plugin.json at {manifest}"
            )
