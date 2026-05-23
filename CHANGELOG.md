# Changelog

All notable changes to palinex are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project adheres to [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] — 2026-05-23

Hardening release. Sweeps up the host-bridge and bundle work that shipped on main between 0.2.0 and now, plus the marketplace conversion to a pinned-source release model so future main commits don't surprise installed users. RDR-001 and RDR-003 both formally accepted in this cycle.

### Added
- **Renderer `a2ui.ready` handshake** (`web/index.html`): the v0.9 renderer now posts `{type: "a2ui.ready"}` to `window.parent` after attaching its `message` listener. Wrappers use this to stop their retry loops as soon as the renderer is observably ready, keeping the common-case delivery at one round-trip while still tolerating warm-cache loads.
- **`web/host-bridge.html` retry-until-ack delivery** matching the contract introduced for the MCP-UI wrapper in 0.2.0. The reference bridge now actually demonstrates the discipline RDR-001 §Item 6 requires of all wrappers — previously it called bare `postMessage` and would have silently re-introduced the warm-cache race for any downstream that copied it.
- **DEMO surface uses real 32-char chashes** (`web/index.html`): `cfbd937e6addd5674fb6cde5b04a9fe1` (RDR-127 Substrate-Decoupled Surface Rendering) and `e3458aa9ce0efa7a148302d4f98c50e2` (RDR-016 AST Chunk Line Range Bug). `?demo=wrapped` inlines matching real-content fallbacks so the demo is meaningful with or without a nexus host wired up.
- **`.claude-plugin/marketplace.json` pinned-source release model**: `plugins[0].source` converted from the relative-path string `"./plugin"` to the `git-subdir` object form with `ref: "v0.3.0"`. Main can advance freely (including edits to marketplace.json itself); installed plugins only update when a release tag is cut. See `global_directives/marketplace-pinned-source-release-model` in nexus T2 for the directive.
- **`tests/test_plugin_structure.py`** (12 parity checks): enforces that every version-bearing manifest agrees with `pyproject.toml`, and that `marketplace.json` source stays in the `git-subdir` object form (reverting to relative-path would defeat the pinned-source model). Mirrors the pattern from `Hellblazer/nexus`.

### Changed
- **`mcpb/pyproject.toml`** dep tightened from `palinex[mcp]>=0.2.0` to `palinex[mcp,nexus]>=0.2.0`. The previous spec omitted the `[nexus]` extra, so the Claude Desktop `.mcpb` bundle's `.venv` never installed `conexus` and server-side chash resolution silently degraded to pass-through. With the extra in place, `render_surface` resolves real chashes against nexus T3 before the wrapper HTML is returned.
- **`mcpb/manifest.json`** description corrected to remove the false claim that Claude Desktop renders `ui://` HTML resources inline. The new text qualifies which hosts mount them inline (claude.ai web, custom MCP UI hosts) and points readers at RDR-001 §Item 4 for Desktop delivery paths. The bundle provides the MCP server only; inline visible surfaces require a host that mounts the resource type.
- **RDR-001** flipped to `status: accepted` after a two-pass substantive-critic gate. Item 6 amended with the "Delivery robustness — retry-until-ack handshake" subsection; Item 4 corrected to reflect that only `wrap_as_mcp_ui_resource` is a producer-side helper; §Context A1 qualified with the Claude Code Desktop v2.1.149 inline-rendering limitation; Phase 2 checked off (shipped 0.2.0); Alt 6 added covering `srcdoc` / `blob:` iframe alternatives; test count corrected (19 → 53), CI matrix (3.10-3.13 → 3.12-3.13), renderer LOC (708 → 845).
- **RDR-003** flipped to `status: accepted` and amended to cover the `.mcpb` bundle as a fourth distribution channel (Item 3a). Item 5 versioning policy rewritten with explicit `0.0.x → 0.1.0 → 0.2.0` bump history and forward-looking 0.3.0 pointer.
- **`docs/rdr/README.md`** gains a per-RDR index table and an honest description of the file↔T2 lifecycle relationship.

### Fixed
- Wrapper bootstrap shipped in 0.1.0 had two delivery races (about:blank early-fire and warm-cache late-attach). 0.2.0 fixed the wrapper; 0.3.0 fixes the reference bridge (`host-bridge.html`) to match. Documented as RDR-001 §Item 6 "Delivery robustness."

### Tracked but not yet shipped
- `palinex-hg3` (P2) — add `release-mcpb.yml` workflow that builds the `.mcpb` archive on `v*` tag push and attaches it as a GitHub release asset. Currently the bundle is built locally and distributed out-of-band.
- `palinex-e7z` (P3) — `_pre_resolve_payload` doesn't recognize `updateDataModel.patch` shape; only the canonical `path + value` shape that `Surface.emit()` produces. Hand-crafted payloads using `patch` silently pass through unresolved.
- RDR-001 Phase 3 beads (`palinex-7n1`, `-ytv`, `-i10`, `-xwr`, `-pr1`) — action registry hardening (protocol doc, runSkill, openFile, trust-gate signature).

## [0.2.0] — 2026-05-23

Substantive correctness fix for the MCP-UI wrapper plus completion of the v0.9 Basic Catalog.

### Added
- **Phase 2 Basic Catalog components** (`web/index.html` + `src/palinex/__init__.py`): Tabs (titled tabs + children), DateTimeInput (ISO 8601 value + optional min/max), Video (URL + minimal controls), AudioPlayer (URL + description). `BASIC_COMPONENTS` now lists all 18 v0.9 catalog components.
- **`a2ui.ready` handshake**: renderer side added in this version (wrapper side started using it in 0.2.0; the matching renderer ping landed alongside).
- **Claude Desktop `.mcpb` extension** scaffold (`mcpb/`): manifest v0.4, uv-managed `.venv` wrapper, thin `src/server.py` entry point that delegates to `palinex.mcp.server.main()`. Initially merged from develop as part of the release.

### Fixed
- **About:blank race in the `render_surface` wrapper** (`src/palinex/__init__.py`): replaced the readyState-gated single-shot `postMessage` delivery with a load-listener + 150ms × 40-attempt retry loop bounded at ~6s. Two failure modes addressed: (a) early fire to the iframe's initial about:blank document before the cross-origin nav commits, and (b) late attach when the renderer's load event has already fired. `setSurface` is idempotent so repeated delivery is safe. See PR #1 and RDR-001 §Item 6 amendment.

### Architecture
- The wrapper bootstrap is now described as a stable contract (retry-until-ack) in RDR-001 §Item 6. Any new wrapper (Tauri host, custom web shell, an HTTP sidecar's index page) must implement the same pattern.

## [0.1.0] — 2026-05-22

Major restructure: palinex is now the **UI front-end for nexus** — library + Claude Code plugin + Pyodide-loaded inspector. Builds on the 0.0.6 wrapped-demo variant by superseding the inline JS workaround with the proper Pyodide-driven live-render panel in the inspector.

### Added
- **Claude Code plugin** (`plugin/` directory): manifest, MCP server registration, two skills (`palinex-overview`, `surface-emission`), and a `/palinex-render` command. Installable via `/plugin install` from this repo. Auto-starts the palinex MCP server at Claude Code session boot.
- **MCP server** (`src/palinex/mcp/`): FastMCP server exposing one tool, `render_surface(payload, title, collection, renderer_url)`. Console script `palinex-mcp` declared via `[project.scripts]`.
- **nexus integration shim** (`src/palinex/nexus_bridge.py`): lazy import of nexus internals; `chash_resolver(chash)` validates RDR-108 32-char hex shape, looks up via T3, returns chunk text or None. Cached import outcome (success or ImportError) for O(1) repeat calls. Behind the `[nexus]` extra.
- **`[nexus]` and `[mcp]` and `[all]` optional dependency extras** in `pyproject.toml`. Library install (`pip install palinex`) stays nexus-free; full integration is `pip install palinex[all]`.
- **Inspector live-render tab** (`web/inspector.html`): tabbed right column (Markdown / Paths / Live render). Live tab has editable textarea + Re-render button + iframe pointing at `./index.html`. postMessage delivers payload to the iframe; edits and re-renders work without leaving the page. Subsumes any need for a separate playground page.
- **RDR-003** (`docs/rdr/rdr-003-plugin-and-source-layout.md`): codifies the packaging decisions — Claude Code plugin, nexus-front-end role, src/ + web/ + plugin/ layout, no HTTP sidecar (per RDR-002 Pyodide-as-default).
- 24 new tests bring total to 59 (13 for nexus_bridge, 11 for the MCP server) — all green across the Python 3.10–3.13 matrix.

### Changed
- **`requires-python = ">=3.12"`** (was `>=3.10`). The `[nexus]` extra pulls `conexus>=4.34` which requires Python 3.12+; uv's dependency resolver fails the whole `[all]` extra when palinex declares broader support than nexus does. Honest fix: track nexus's support window. Library-only users on 3.10/3.11 can stay on palinex 0.0.x. CI + release matrices dropped to `["3.12", "3.13"]` accordingly.
- **Source layout**: `palinex/` → `src/palinex/` (standard src-layout). Tests find the package via `[tool.pytest.ini_options] pythonpath = ["src"]` — no PYTHONPATH=. needed.
- **Static frontend**: `index.html`, `host-bridge.html`, `inspector.html` → `web/`. GitHub Pages deploys from `web/` via a new `.github/workflows/pages.yml` workflow (switched from legacy `main/` to GitHub Actions deployment).
- **AGENTS.md** + README updated for the new layout and install paths.
- **html-tool-patterns skill** LOC threshold raised: warn 600, stop 1100 (was 900). Empirical-observations table added to document realistic ceilings for tool variants (renderer ~770, host-bridge ~190, inspector ~1010).
- 0.0.6's wrapped-demo `?demo=wrapped` JS path stays in `web/index.html` — the inspector's Pyodide-driven live render is the production path; the inline-JS wrap is the lightweight no-deps fallback for users who don't want the inspector's 10MB Pyodide download.

### Architecture
- nexus does **not** depend on palinex. The dependency direction is strictly palinex → nexus (and only via the `[nexus]` extra).
- The HTTP sidecar that was briefly scoped is dropped per RDR-002. Pyodide-based pages (inspector.html) cover the non-Claude-Code use cases.
- A separate playground page is NOT shipped — inspector.html serves both debugging and live-render.

### Companion in nexus
- nexus RDR-127 v2 (in PR #926) records the corresponding non-decision: nexus ships no surface-rendering code. RDR-123 and RDR-124 remain superseded by RDR-127, with tombstones refreshed to point at the palinex plugin layer.

## [0.0.6] — 2026-05-22

Wrapped-demo variant in the standalone renderer.

### Added
- Renderer `?demo=wrapped` URL parameter renders the same demo payload as `?demo=1` but with palinex 0.0.5's `wrap_as_mcp_ui_resource` pre-resolution logic applied in JS — chash references in the data model are substituted with text, and `openChash` Button actions are rewritten to `copyToClipboard`. Demonstrates the wrap end-state without a real producer or chash store; click "Open chunk" → resolved text in clipboard, no host bridge dead-end modal.
- Empty-state link "try the wrapped variant" alongside the existing "render demo" button.

### Why
Previously the hosted standalone demo showed the host-bridge dead-end modal when users clicked "Open chunk" — accurate documentation of standalone behavior but confusing as a first experience. The wrapped variant shows the alternative path (palinex pre-resolution) inline, so users can see both architectural modes from the same hosted page.

## [0.0.5] — 2026-05-22

MCP UI resource helper for embedding palinex surfaces inside Claude Code (or any host that consumes MCP UI Apps).

### Added
- `palinex.wrap_as_mcp_ui_resource(payload, *, chash_resolver=None, renderer_url=..., title=...)` — wraps an a2ui v0.9 surface payload as a self-contained HTML page suitable for the `text` field of an MCP UI resource. Hosts the canonical renderer in an iframe, posts the payload on load, no live host bridge required for static snapshots.
- When `chash_resolver` is provided, pre-resolves: any string value in the data model that the resolver returns text for is replaced; any `Button` with `openChash` action is rewritten to `copyToClipboard` carrying the same path reference. Click → resolved text copied to clipboard. No round-trip to the host needed.
- 7 new tests covering shape envelope + flat shape, resolver substitution, action rewrite, non-`openChash` actions left alone, payload immutability (deep-copied internally), HTML escaping of renderer URL, and `</script>` injection protection.
- Exported as `palinex.wrap_as_mcp_ui_resource` (top-level).

### Notes
- This is the simple-path Claude Code integration (palinex RDR-001 §Item 4 "MCP UI resource" delivery). Static snapshots only; interactive flows (live data fetch on click) require the bidirectional `a2ui.request` / `a2ui.response` protocol which palinex's `host-bridge.html` reference still demonstrates.

## [0.0.4] — 2026-05-22

Action-context bug fix + clearer empty-backend UX. No new features.

### Fixed
- Renderer (`index.html`) `Button` now preserves render-time data-model context (including `@item` template alias) across the gap between render and click. Previously, `Surface` actions inside a template iteration emitted unresolved `{path: "/@item/..."}` payloads because `state.dataModel` was restored to the parent context before the click handler fired. New `withDataModel(model, fn)` helper installs the captured context temporarily during dispatch. Visible symptom: `openChash` action payload contained the raw DataPath instead of the resolved chash string when fired from a List-template Button.

### Changed
- Host-bridge (`host-bridge.html`) shows a prominent banner when no backend is configured, explaining the consequence (surface actions return errors) and offering two explicit affordances: "Try mock (stub responses)" and "Enter sidecar URL…". Previous behavior was silent — backend was just "none" in the status pill, and surface actions failed with no UI feedback. The mock backend is now opt-in via the banner button, not a hidden default.

## [0.0.3] — 2026-05-22

First Pyodide-augmented release plus a load-bearing renderer fix.

### Fixed
- Renderer (`index.html`) `applyMessage` now correctly handles `updateDataModel` messages with `path: "/"` (root replacement). Previously the data model stayed `{}` because `jsonPointerSet` at root returns the value without mutating — caller now branches on root path and assigns directly. Visible as "template path /citations is not an array" on the hosted demo; now resolves correctly.

### Added
- `inspector.html` — Pyodide-loaded surface validator. Accepts payloads via URL param, base64, file picker, drag-and-drop, paste textarea, or postMessage. Runs structural validation in pure JS (mirrors `Surface._validate_refs` with identical error strings); opt-in deep validation via Pyodide + `palinex[validate]` against v0.9 schemas fetched from raw.githubusercontent.com. Renders an errors panel with anchor links, a component table with role inference (root / child / template-target / orphan), a payload viewer with selected-node highlighting, a markdown sidecar preview (deep-only), and a data-path walker grouping resolved vs unresolved JSON-pointer references. ~890 LOC, single file, lit-html via CDN, no build step. Implements palinex RDR-002 §Approach Item 1.

## [0.0.2] — 2026-05-22

Full a2ui v0.9 Basic Catalog coverage.

### Added
- `Surface.video(url)` — Video component builder
- `Surface.audio_player(url, description=...)` — AudioPlayer builder
- `Surface.date_time_input(value, label, enable_date, enable_time, min, max)` — DateTimeInput builder
- Renderer support for `Tabs`, `DateTimeInput`, `Video`, `AudioPlayer` — fills the 4-component gap from 0.0.1
- CSS styling for tabs (tab list, active tab indicator) and audio (description + native controls)
- Markdown sidecar walks `Tabs` (each tab title as `#### `, then child), `Video` and `AudioPlayer` (markdown link with optional description), and `DateTimeInput` (label fallback shared with other input components)
- 9 additional tests bringing total to 28 (component shape, dynamic title binding, markdown round-trip for new components, validation of dangling tab child refs)

### Coverage
All 18 a2ui v0.9 Basic Catalog components now implemented:
Text · Image · Icon · Video · AudioPlayer · Row · Column · List · Card · Tabs · Modal · Divider · Button · TextField · CheckBox · ChoicePicker · Slider · DateTimeInput

## [0.0.1] — 2026-05-22

Initial release.

### Added
- `palinex` Python package — typed builders for a2ui v0.9 surfaces with structural validation and optional jsonschema deep validation
- `index.html` — single-file lit-html renderer covering 14 of 18 a2ui Basic Catalog components (Text, Image, Icon, Row, Column, List, Card, Modal, Divider, Button, TextField, CheckBox, ChoicePicker, Slider)
- `host-bridge.html` — reference wrapper implementing the `a2ui.request` / `a2ui.response` postMessage protocol for host-to-renderer bridging
- v0.9 message envelope support (createSurface, updateComponents, updateDataModel, deleteSurface) and the convenience flat-shape payload form
- Data model with JSON-pointer (`DataBinding`) resolution and template `ChildList` rendering
- Markdown sidecar emission (lossless round-trip from surface to markdown)

### Known limitations
- Deep jsonschema validation through the catalog `$ref` chain is flaky due to upstream schema referencing patterns (documented in `palinex.Surface.validate`). Structural validation is reliable.
- Four Basic Catalog components not yet implemented: Tabs, DateTimeInput, Video, AudioPlayer.
- No accessibility (ARIA) pass-through yet — schema fields are parsed but not rendered to DOM.
