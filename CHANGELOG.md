# Changelog

All notable changes to palinex are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project adheres to [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
