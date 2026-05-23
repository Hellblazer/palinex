---
title: "Packaging: Claude Code Plugin + Claude Desktop .mcpb Bundle + nexus-front-end Role + src/ Layout"
id: RDR-003
type: Architecture
status: accepted
priority: high
author: Hal Hildebrand
reviewed-by: self
created: 2026-05-22
accepted_date: 2026-05-23
related_rdrs: [RDR-001, RDR-002]
related_external: [a2ui-v0.9-spec, claude-code-plugins, claude-desktop-mcpb, fastmcp]
---

# RDR-003: Packaging — Claude Code Plugin + nexus-front-end Role + src/ Layout

> palinex is the **UI front-end for nexus**. The library layer stays
> nexus-agnostic; the plugin layer integrates with nexus via the
> `[nexus]` extra. The HTTP sidecar that was briefly scoped is dropped
> in favor of Pyodide-based pages (per RDR-002).

## Problem Statement

palinex 0.0.x shipped as a library + a single-file renderer + a host-bridge
reference + a Pyodide inspector. That's enough to demonstrate the protocol
but doesn't deliver "I want to render a2ui surfaces in Claude Code." The
0.0.x ↔ 0.1.0 gap is the packaging that makes the library actually usable
where it matters.

The candidate packagings considered:

1. **nexus depends on palinex** — nexus imports palinex, ships a
   `render_surface` MCP tool. Tried during this session; rejected because
   the dependency direction was backward and nexus shouldn't carry surface-
   rendering concerns.
2. **palinex depends on nexus (optional via `[nexus]` extra)** — palinex
   owns the integration; nexus stays clean. Chosen.
3. **palinex ships its own HTTP sidecar that fronts nexus** — initially in
   scope, then dropped: the sidecar is a daemon, and RDR-002 says default
   to Pyodide for anything that would otherwise need one. The
   inspector.html's Pyodide-based live-render panel covers the
   "I want to see this payload rendered locally" use case without a service.

This RDR records (2), explicitly drops (3), and documents the source
reorganization (src-layout, web/, plugin/) that supports the shift.

## Decision

### Approach

**Item 1 — palinex is the UI front-end for nexus.** palinex depends on nexus
via a `[nexus]` optional extra. The library layer (`Surface`,
`wrap_as_mcp_ui_resource`, builders) stays nexus-agnostic so anyone can use
it for any data source. The integration layer (`palinex.nexus_bridge`,
`palinex.mcp.server`, the Claude Code plugin) uses nexus when present.
Without `[nexus]`, the MCP server's `render_surface` tool still works — it
just doesn't substitute chashes.

Nexus does **not** depend on palinex. The dependency arrow runs strictly one
direction. Nexus RDR-127 records this decision on the nexus side.

**Item 2 — Source layout: src/ + web/ + plugin/.**

```
palinex/
├── src/palinex/                     ← src-layout; pyproject pythonpath = ["src"]
│   ├── __init__.py                  Surface builders, wrap_as_mcp_ui_resource
│   ├── nexus_bridge.py              lazy nexus import; chash_resolver; is_available
│   ├── mcp/                         FastMCP server
│   │   ├── __init__.py
│   │   ├── __main__.py              python -m palinex.mcp
│   │   └── server.py                render_surface tool
│   └── (server/ — explicitly NOT created per Item 4)
├── web/                             ← static frontend
│   ├── index.html                   renderer
│   ├── host-bridge.html             postMessage protocol reference
│   └── inspector.html               Pyodide-loaded validator + live-render
├── plugin/                          ← Claude Code plugin
│   ├── .claude-plugin/plugin.json   manifest
│   ├── .mcp.json                    declares palinex-mcp server
│   ├── skills/                      palinex-overview, surface-emission
│   ├── commands/                    /palinex-render
│   └── README.md
├── tests/
├── docs/rdr/                        RDR-001, RDR-002, RDR-003
└── pyproject.toml                   hatchling, extras: [validate] [nexus] [mcp] [all]
```

Tests find the package via `[tool.pytest.ini_options] pythonpath = ["src"]`,
not via PYTHONPATH=. or editable install. Pages deploys from `web/` via a
GitHub Actions workflow.

**Item 3 — Distribution channels.** palinex ships through eight channels (five PyPI extras plus three host-facing distributions):

| Channel | Install | Contents |
|---|---|---|
| PyPI `palinex` | `pip install palinex` | Library only |
| PyPI `palinex[validate]` | `pip install palinex[validate]` | + jsonschema deep validation |
| PyPI `palinex[mcp]` | `pip install palinex[mcp]` | + FastMCP runtime |
| PyPI `palinex[nexus]` | `pip install palinex[nexus]` | + conexus dep |
| PyPI `palinex[all]` | `pip install palinex[all]` | All extras combined |
| Claude Code plugin | `/plugin install Hellblazer/palinex` (or local path) | The `plugin/` subtree |
| Claude Desktop `.mcpb` extension | Drag bundle into Claude Desktop → Settings → Developer → Install extension | The `mcpb/` subtree (see Item 3a) |
| GitHub Pages | `https://hellblazer.github.io/palinex/` | `web/` deployed via `.github/workflows/pages.yml` |

Console script: `palinex-mcp` (from `[project.scripts]`) starts the FastMCP
server. The plugin's `.mcp.json` references it by name. The `.mcpb` bundle's
`manifest.json` invokes `src/server.py` via `uv run --directory ${__dirname}`,
where `src/server.py` is a thin entry point that delegates to the same
`palinex.mcp.server.main()` function — behaviorally equivalent to the console
script, just dispatched differently because Claude Desktop's extension runner
expects a script path rather than a script name.

**Item 3a — Claude Desktop `.mcpb` bundle.** Added in 0.2.0 (commit `fe03232`).
The bundle vendors a uv-managed `.venv` that pulls `palinex[mcp]>=<version>`
from PyPI and exposes the same `render_surface` MCP tool as the Claude Code
plugin. Bundle layout:

```
mcpb/
├── .gitignore       ignores .venv/, uv.lock, *.mcpb, __pycache__/
├── .mcpbignore      excludes dev artifacts from the built archive
├── manifest.json    Claude Desktop extension manifest (v0.4 schema)
├── pyproject.toml   palinex-mcpb wrapper package; depends on palinex[mcp]
├── src/server.py    thin entry point: `from palinex.mcp.server import main; main()`
└── uv.lock          pinned dep tree resolved at build time
```

Built `.mcpb` archives (`palinex-<version>.mcpb`) and the local `.venv/` are
gitignored — they're build/runtime artifacts, not source. As of 0.4.2 the
bundle is also built automatically by `.github/workflows/release.yml` on
every `v*` tag push (closes palinex-hg3): the workflow runs
`mcpb pack mcpb /tmp/palinex-<version>.mcpb` via `@anthropic-ai/mcpb`,
asserts `mcpb/manifest.json` `version` equals the tag, and attaches the
archive as a GitHub Release asset alongside the wheel + sdist. Local
builds still work for testing; the workflow is the canonical published
artifact.

The bundle's versioning rule is unchanged: `mcpb/pyproject.toml` version
and `mcpb/manifest.json` version both track `palinex` semver — bump
together with the root `pyproject.toml` at release time. `tests/test_plugin_structure.py`
enforces this on every CI run.

**Known limitation as of 0.2.0 (Claude Code Desktop v2.1.149):** the host
does not currently render `ui://` HTML resources as inline iframes (per
RDR-001 §Context A1). The bundle therefore provides the MCP server only;
inline visible surfaces require a host that mounts `ui://` resources, or
fall back to the embedded-artifact / external-URL delivery shapes from
RDR-001 Item 4. The bundle's `manifest.json` description reflects this
honestly; see RDR-001 §Item 9 for the cross-reference.

_Previously a known gap (palinex-hg3): there was no automated release
workflow for the `.mcpb` bundle (unlike PyPI publishing). Closed in 0.4.2 by
extending `.github/workflows/release.yml` with an `mcpb pack` step rather
than a separate `release-mcpb.yml` workflow — keeping a single release job
prevents two workflows from racing on the same GitHub Release creation and
isolates failures from PyPI publish under one rollup status check._

**Item 4 — No HTTP sidecar.** Briefly scoped as `src/palinex/server/`,
dropped per RDR-002 (Pyodide-as-default). The use cases the sidecar would
have served are covered by:

- Inside Claude Code: the MCP plugin (Item 3, via `palinex[mcp]`).
- Local browser-side development / debugging / demo: `inspector.html`'s
  Pyodide-loaded palinex + live-render iframe. No daemon.
- Anything else (webhooks, scripts, custom shells): `import palinex` and
  invoke `wrap_as_mcp_ui_resource` directly from whatever Python process
  the consumer runs. The library is already there; no service needed.

A future RDR can revisit if a real "Python HTTP service fronting nexus"
demand surfaces. RDR-003 explicitly forecloses building it speculatively.

**Item 5 — Versioning policy update.** palinex 0.x.y tracks a2ui v0.9.
Bump history under this policy:

- **0.0.x → 0.1.0** — substantial restructure (src/ layout, plugin shipped, nexus integration)
- **0.1.0 → 0.2.0** (shipped 2026-05-23) — about:blank race fix in the wrapper bootstrap with the retry-until-ack handshake (RDR-001 §Item 6 amendment), Phase 2 Basic Catalog components (Tabs / DateTimeInput / Video / AudioPlayer), and the new `.mcpb` Claude Desktop bundle (Item 3a)

Forward-looking: 0.2.x patches for the same scope; 0.3.0 lands when Phase 3
(RDR-001 action registry hardening — protocol doc, runSkill, openFile,
trust-gate) ships incrementally per the bead chain `palinex-ytv`,
`palinex-i10`, `palinex-xwr`, `palinex-pr1`. 1.0.0 remains reserved for a2ui
v1.0 if/when that ships upstream.

**Item 6 — palinex.nexus_bridge is the only nexus-aware module.** All
nexus access in palinex routes through `palinex.nexus_bridge`. This keeps
the dependency surface scoped to one file, makes the
"is nexus available?" check uniform, and lets future swaps (e.g.,
non-nexus data sources via a different bridge module) plug in cleanly.

**Item 7 — Inspector.html is the playground.** No separate
`playground.html`. Inspector ships the live-render tab alongside
validation/markdown/paths so a single page serves both
"is my payload valid?" and "what does it look like?" The same Pyodide
runtime serves both — no duplication.

## Alternatives Considered

### Alt 1 — nexus depends on palinex (rejected)

Tried this session. Dependency direction was backward; nexus shouldn't ship
surface-rendering code. The implementation half on nexus's RDR-127 branch
was withdrawn. See RDR-127 v2.

### Alt 2 — HTTP sidecar exposes nexus over HTTP (rejected)

Briefly scoped as `src/palinex/server/`. Three endpoints planned:
`/api/chash`, `/api/search`, `/api/render`. Dropped because:
- It's a daemon. RDR-002 says don't.
- Pyodide-based pages serve the same use cases for non-Claude-Code consumers.
- The MCP plugin handles Claude Code.
- No real use case for "Python HTTP service fronting nexus" surfaced
  besides theoretical browser-fetched chash resolution, which has
  security and CORS issues that make it the wrong default anyway.

### Alt 3 — Hard nexus dependency (no extra)

`pip install palinex` would pull conexus + chromadb + mineru + voyageai +
torch — 3-5 GB. Rejected because it forces the heavy install on users who
only want the library. Keeping it as `[nexus]` extra preserves the
lightweight library install for non-nexus use cases (which exist: testing,
docs, anyone using a different data source).

### Alt 4 — Defer the plugin to a separate repo

`palinex` (PyPI) + `palinex-claude-plugin` (separate repo). Considered for
cleaner separation; rejected because the plugin is small (1 manifest,
1 mcp.json, 2 skills, 1 command, 1 README — under 200 LOC total) and
versioning a separate repo for that adds friction without value. The
plugin lives in the palinex repo under `plugin/`.

### Briefly rejected

- **Vendoring nexus into palinex** — duplicates maintenance; defeats the
  semver dep arrangement.
- **Per-host catalogs (`palinex.lumino.v1`, `palinex.notcurses.v1`)** —
  scrapped RDR-119 idea; not relevant to palinex 0.1.0 since we're not
  targeting non-Claude-Code hosts yet. Revisit if/when a real host
  besides Claude Code shows up.

## Trade-offs

### Consequences

- **(+)** One repo for the full palinex story — library + plugin + renderer
  + inspector. Easy to find, easy to release.
- **(+)** `palinex[nexus]` extra makes the integration opt-in; library
  users not coupled to nexus's heavy deps.
- **(+)** Plugin shipping in the same repo means version moves in lock-step
  with the library it depends on. No drift.
- **(+)** No sidecar = no second service to maintain, secure, or document.
  Aligns with RDR-002.
- **(+)** Source layout (src/ + web/ + plugin/) supports future growth
  without restructuring again.
- **(−)** "palinex" now names three distinct artifacts (PyPI package,
  Claude Code plugin, hosted renderer). Docs need to disambiguate where
  it matters; mostly they reinforce each other.
- **(−)** Anyone wanting palinex with a non-nexus data source has to
  write their own resolver (per RDR-001 the API supports it; just no
  built-in alternatives shipped).

### Risks and Mitigations

- **Risk:** nexus's heavy install scares users away even from the
  library-only `pip install palinex`.
  **Mitigation:** bare install has zero non-stdlib deps. Only the extras
  pull anything. README leads with the bare install.

- **Risk:** Plugin install discoverability is poor — Claude Code's plugin
  ecosystem is young, no marketplace yet (as of this writing).
  **Mitigation:** README documents direct-from-GitHub install. As the
  ecosystem matures, list in any marketplaces that emerge.

- **Risk:** Console script `palinex-mcp` collides with another tool on PATH.
  **Mitigation:** unlikely (search shows no existing tool by that name);
  if it happens, rename the script in pyproject without breaking the API.

- **Risk:** nexus's API moves under us, breaking nexus_bridge.
  **Mitigation:** pin `conexus>=4.34,<5` in the `[nexus]` extra; bump
  deliberately when nexus releases breaking changes.

## Implementation Plan

### Prerequisites

- [x] RDR-001 — architecture
- [x] RDR-002 — Pyodide-as-default discipline
- [x] palinex 0.0.x released to PyPI (current: 0.0.6 + tag v0.0.6)
- [x] Nexus PR #926 (RDR-127 v2) — pending merge; doesn't block 0.1.0
- [ ] RDR-003 accepted

### Phase 1 (this RDR's release work)

1. **Source reorganization** — palinex/ → src/palinex/; HTML files → web/.
   Pytest pythonpath = ["src"]. Pages workflow deploys from web/. **Done.**
2. **`[nexus]` + `[mcp]` extras + nexus_bridge** — pyproject extras +
   `src/palinex/nexus_bridge.py` + 13 tests. **Done.**
3. **MCP server** — `src/palinex/mcp/{server.py, __main__.py, __init__.py}`
   + 11 tests + `palinex-mcp` console script. **Done.**
4. **Inspector live-render panel** — tabbed right column with
   Markdown/Paths/Live; iframe-loaded `./index.html` with postMessage
   payload delivery; edit/re-render loop. **Done.**
5. **Plugin scaffold** — `plugin/.claude-plugin/plugin.json`, `.mcp.json`,
   skills (palinex-overview + surface-emission), `/palinex-render`
   command, README. **Done.**
6. **RDR-003 (this document).** Done with this write.
7. **Update CHANGELOG, AGENTS.md, architecture-sequence.md.**
8. **Bump pyproject to 0.1.0.**
9. **Promote develop → main + tag v0.1.0.** Release workflow fires
   matrix tests + OIDC publish to PyPI + GitHub Release with sdist + wheel.

### Phase 2 (future, not in 0.1.0)

- Plugin marketplace listing if/when one exists
- Interactive flows (the bidirectional postMessage protocol)
- Additional resolvers (non-nexus data sources)
- Possibly: per-host catalogs if a real second host materializes

## References

- palinex RDR-001 — architecture (a2ui v0.9 as IR, SurfaceBroker,
  three delivery shapes, postMessage RPC, markdown sidecar)
- palinex RDR-002 — Pyodide as preferred runtime augmentation
- nexus RDR-127 v2 — records the corresponding non-decision on the
  nexus side (no palinex dep in nexus; palinex is downstream)
- a2ui v0.9 specification — https://a2ui.org/specification/v0.9-a2ui/
- Claude Code plugin docs — https://docs.claude.com/en/docs/claude-code/plugins
- FastMCP — https://github.com/jlowin/fastmcp

## Revision History

_2026-05-22 — initial sketch. Captures the packaging decisions made during
the same session that wrote and reversed the nexus-side integration
(RDR-127 v1 → v2). HTTP sidecar dropped per RDR-002. Inspector subsumes
playground. Source layout codified._

_2026-05-23 — accepted alongside palinex 0.2.0. Amendments before acceptance:_
- _Title extended to include "Claude Desktop .mcpb Bundle" — the bundle was a real packaging path that landed in 0.2.0 (commit fe03232) but the original title and Item 3 didn't mention it._
- _Item 3 distribution table extended from three channels to four (added `.mcpb` row); console-script note clarified that both the plugin's `.mcp.json` and the bundle's `manifest.json` reference the same `palinex-mcp` entry point._
- _Item 3a "Claude Desktop .mcpb bundle" added — covers the `mcpb/` directory layout, the uv-managed `.venv` that pulls `palinex[mcp]` from PyPI, version-bump coupling between `mcpb/pyproject.toml` and `mcpb/manifest.json` and root `pyproject.toml`, the Claude Code Desktop v2.1.149 inline-rendering limitation (cross-references RDR-001 §Context A1), and the gap around .mcpb release automation (no workflow exists yet — flagged as future work)._
- _`related_external` extended with `claude-desktop-mcpb`._

_Status flipped from draft to accepted. T2 records under palinex_rdr/003 and palinex_rdr/003-gate-latest mirror the file state. Phase 2 items (plugin marketplace listing, interactive flows, additional resolvers, per-host catalogs) remain out of scope for the accepted architecture._

_Second-pass corrections from substantive-critic gate (after the initial amendments above):_
- _Item 3 prose corrected from "four channels" to "eight channels" — the count was stale after the table was extended._
- _Item 3a layout diagram extended to mention `.gitignore` and `.mcpbignore`; added explicit note that built `.mcpb` archives and the `.venv/` are gitignored (so the local `mcpb/palinex-<version>.mcpb` artifact a developer sees after a build isn't a tracked file)._
- _Item 3 console-script paragraph corrected: the `.mcpb` bundle's `manifest.json` invokes `src/server.py` directly via `uv run --directory ${__dirname} src/server.py`, not the `palinex-mcp` console script. The behavior is equivalent (`src/server.py` delegates to `palinex.mcp.server.main()`) but the dispatch path is different._
- _Item 5 versioning policy rewritten — it had still framed 0.2.x as hypothetical when palinex 0.2.0 had already shipped today. New text records the 0.0.x → 0.1.0 → 0.2.0 bump history and points the forward-looking 0.3.0 line at the RDR-001 Phase 3 bead chain._
- _Item 3a release-automation gap upgraded from "future ticket should" to a tracked bead (`palinex-hg3`, P2)._
