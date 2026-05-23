# AGENTS.md

Project guidance for AI coding agents working in this repository. `CLAUDE.md` is a symlink to this file.

**palinex** (palin- "again" + nexus "bond") — Python builders + single-file HTML renderer + host-bridge wrapper for [a2ui v0.9](https://a2ui.org/) surfaces. Published on PyPI as `palinex`; renderer hosted at <https://hellblazer.github.io/palinex/>.

## Quick start

```bash
pip install palinex                              # builders only
pip install palinex[validate]                    # + jsonschema for deep validation
pip install palinex[nexus]                       # + nexus integration (chash resolver, sidecar)
pip install palinex[mcp]                         # + MCP server entry point

open web/index.html?demo=1                       # renderer with built-in demo
open web/inspector.html                          # Pyodide-loaded surface validator
open web/host-bridge.html                        # host-side postMessage bridge reference

python3 -m venv .venv && .venv/bin/pip install pytest jsonschema
.venv/bin/pytest tests/ -v                       # pytest picks up src/ via pyproject pythonpath
```

## Architecture at a glance

Two halves that meet through a2ui v0.9 JSON:

- **Producer** (Python): `palinex.Surface` builds v0.9 message envelopes (`createSurface`, `updateComponents`, `updateDataModel`, `deleteSurface`) from typed inputs. Structural validation always; deep jsonschema validation opt-in via `[validate]`.
- **Renderer** (single HTML file): lit-html consumes the same payload, renders all 18 v0.9 Basic Catalog components, dispatches actions via postMessage RPC to a host bridge.
- **Host bridge** (separate single HTML file): reference wrapper showing how a containing host (Claude Code MCP UI resource, custom shell, sidecar HTTP proxy) routes `a2ui.request` / `a2ui.response` messages.
- **Inspector** (single HTML file): Pyodide-loaded validator. Same `Surface.validate()` runs in-browser; same markdown sidecar.

## Load-bearing protocols

### The four invariants (`html-tool-patterns` skill)

Apply to every HTML page in this repo:

1. **One file.** Inline CSS + JS. No build step.
2. **No React/Angular/Vue/Svelte.** Plain DOM or lit-html (ESM from CDN). Pinned version.
3. **CDN deps with pinned versions.** `@3.2.1`, never `@latest`. No `package.json`.
4. **Small.** Warn at 600 LOC, hard stop at 900. Full-catalog renderers land ~770-890. Above 900, restructure.

### Pyodide as default (RDR-002)

Any feature that would otherwise require a Python install or long-running daemon **defaults to Pyodide** (browser-loaded CPython via WebAssembly + micropip). Daemon proposals get pushback. See `docs/rdr/rdr-002-pyodide-as-runtime-augmentation.md`.

### a2ui v0.9 is the IR (RDR-001)

No parallel IR. No translation layer. Producers emit v0.9 JSON; renderers consume v0.9 JSON. Pin to v0.9 schemas; track v0.10 in future palinex major.

### Action allowlist (v1)

Three first-class actions resolve in-renderer or via host bridge:
- `openUrl` — pure browser
- `copyToClipboard` — pure browser
- `openChash` — host-bridged via postMessage RPC

All other actions go through the same postMessage path; host registry decides whether to execute. Default: log, don't execute. Adding to the allowlist requires explicit RDR or §Approach item.

### Markdown sidecar always

Every surface emission emits both a2ui JSON and a lossless markdown rendering. Hosts that can't render structured surfaces get the markdown. CI gate: round-trip from markdown to surface to markdown equals input on a representative corpus.

## Workflow (solo dev)

- **Develop branch.** All work lands on `develop`. CI doesn't fire on `develop` pushes — only on PR and push to `main`. Batch multiple commits, then promote `develop` → `main` and tag.
- **No PR churn.** Sole maintainer; chained commits on `develop`; one release per batched promotion.
- **Releases via tag push** (`v*`). Triggers OIDC trusted-publisher to PyPI + GitHub Release with sdist/wheel attached. Version-tag check matches `pyproject.toml`.
- **Bump version at promotion time**, not per commit. `0.0.x` for alpha; `0.x.y` tracks a2ui v0.9; `v1.x.y` reserved for a2ui v1.0.

## Git hooks

Local guardrails enforcing the protocols on every commit/push. Install once per clone:

```bash
scripts/install-hooks.sh
```

Sets `core.hooksPath` → `.githooks/`. Idempotent; re-run after pulls.

| Hook | What it does |
|---|---|
| `pre-commit` | Fast checks (<1s): HTML files ≤ 900 LOC (warn at 600), no unpinned CDN URLs (`@latest` or version-less), `pytest --collect-only` for syntax sanity on staged Python. |
| `pre-push` | Full `pytest` suite. CI matrix re-runs on PR / push to main, but this catches regressions before they hit the wire. |

Skip with `--no-verify` if you must, but the threshold breach should usually be a deliberate "raise the threshold AND document the new ceiling" decision, not a bypass.

## RDR convention

Markdown files under `docs/rdr/`, sequential `rdr-NNN-kebab-title.md`. Lightweight — no T2 lifecycle, no automated gates (palinex is small enough). Frontmatter mirrors nexus's: `title`, `id`, `type`, `status` (`draft` | `accepted` | `superseded` | `withdrawn`), `priority`, `author`, `created`, `related_rdrs`. See `docs/rdr/README.md`.

Active RDRs:
- **RDR-001** — Architecture (a2ui v0.9 IR, single-file renderer, three delivery shapes, postMessage RPC, markdown sidecar)
- **RDR-002** — Pyodide as preferred runtime augmentation

## Component coverage

All 18 a2ui v0.9 Basic Catalog components: Text · Image · Icon · Video · AudioPlayer · Row · Column · List · Card · Tabs · Modal · Divider · Button · TextField · CheckBox · ChoicePicker · Slider · DateTimeInput.

## Repo layout

```
palinex/
├── src/palinex/                 # Python package (src-layout)
│   ├── __init__.py              # Surface builders, wrap_as_mcp_ui_resource (~720 LOC)
│   ├── nexus_bridge.py          # nexus integration shim (optional via [nexus] extra)
│   ├── mcp/                     # MCP server: python -m palinex.mcp
│   │   ├── __main__.py
│   │   └── server.py            # render_surface tool
│   └── server/                  # HTTP sidecar: python -m palinex.server / palinex serve
│       ├── __main__.py
│       ├── app.py
│       └── handlers/            # /api/chash, /api/search, /api/render, /api/health
├── web/                         # Static frontend
│   ├── index.html               # Renderer (~770 LOC)
│   ├── host-bridge.html         # Reference host wrapper (~160 LOC)
│   └── inspector.html           # Pyodide-loaded validator (~890 LOC)
├── plugin/                      # Claude Code plugin
│   ├── plugin.json
│   ├── .mcp.json                # registers `python -m palinex.mcp`
│   ├── skills/
│   └── commands/
├── tests/                       # pytest; src/ on path via pyproject pythonpath
├── docs/
│   ├── rdr/                     # RDR-001, RDR-002, RDR-003
│   └── architecture-sequence.md
├── pyproject.toml               # hatchling, Apache-2.0, extras: [validate] [nexus] [mcp] [all]
├── README.md, CHANGELOG.md, AGENTS.md, CLAUDE.md (symlink), LICENSE
├── A2UI-V09-DIVERGENCE.md       # v0.9 audit notes
└── .github/workflows/           # ci.yml, release.yml, pages.yml (deploys web/)
```

## What lives in nexus (not here)

palinex is a standalone project. nexus depends on it via PyPI — never the other way around. Nexus's integration RDR is its own RDR-127 (`~/git/nexus/docs/rdr/rdr-127-substrate-decoupled-surface-rendering.md`); palinex itself stays project-agnostic.

## License

Apache-2.0 (compatible with a2ui's Apache-2.0 spec; downstream consumers including AGPLv3+ nexus can use).
