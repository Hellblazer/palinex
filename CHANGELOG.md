# Changelog

All notable changes to palinex are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project adheres to [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
