# Changelog

All notable changes to palinex are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project adheres to [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
