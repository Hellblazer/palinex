# a2ui v0.9 Conformance — Divergence Report

Audit of the initial `surface-render.html` (v0) against the a2ui v0.9 specification at `/Users/hal.hildebrand/git/a2ui/specification/v0_9/json/`. Performed 2026-05-22.

## Bottom line

The initial renderer was a **plausible sketch of an a2ui-style format**, not actually v0.9-conformant. Substantial restructuring needed. The structural facts below drive the rewrite.

## Schema files audited

- `server_to_client.json` — message envelope (4 message types)
- `common_types.json` — DataBinding, DynamicString/Number/Boolean, ChildList, FunctionCall, Action
- `basic_catalog.json` — 18 component definitions

## Divergence summary

### Surface-level shape

| Aspect | Initial assumption | v0.9 actual |
|---|---|---|
| Top-level envelope | `{surfaceId, root, components}` | `{version: "v0.9", createSurface\|updateComponents\|updateDataModel\|deleteSurface: {...}}` |
| Lifecycle | Single payload | Stream of messages: createSurface → updateComponents [+ updateDataModel ...] |
| Root reference | Separate `root` field | Component in the array with `id: "root"` |
| catalogId | Not modeled | Required on createSurface |
| Data model | Not separated | Distinct channel via `updateDataModel` with JSON-pointer paths |

### Per-component shape

| Component | Discriminator field | Key fields | Children model |
|---|---|---|---|
| All | `component` (not `type`) | `id` required on all | n/a |
| `Text` | `component: "Text"` | `text` (DynamicString), `variant` h1-h5/caption/body | leaf |
| `Image` | | `url` (not `src`), `description`, `fit`, `variant` (icon/avatar/...) | leaf |
| `Icon` | | `name` from fixed enum OR `{svgPath}` OR DataBinding | leaf |
| `Video` | | `url` | leaf |
| `AudioPlayer` | | `url`, `description` | leaf |
| `Row` | | `justify`, `align` | `children`: ChildList |
| `Column` | | `justify`, `align` | `children`: ChildList |
| `List` | | `direction` v/h, `align` | `children`: ChildList |
| `Card` | | (no extra fields) | `child`: single ComponentId — must wrap multiple in Column/Row |
| `Tabs` | | `tabs: [{title, child}]` | per-tab single child |
| `Modal` | | `trigger`: ComponentId, `content`: ComponentId | trigger + content (not "children") |
| `Divider` | | `axis` horizontal/vertical | leaf |
| `Button` | | `child`: ComponentId (typically Text), `variant` default/primary/borderless, `action` REQUIRED | single child |
| `TextField` | | `label`, `value`, `variant` shortText/longText/number/obscured, `validationRegexp` | leaf |
| `CheckBox` | | `label`, `value` (DynamicBoolean, required) | leaf |
| `ChoicePicker` | | `options: [{label, value}]`, `value: string[]`, `variant` multipleSelection/mutuallyExclusive, `displayStyle` checkbox/chips, `filterable` | leaf |
| `Slider` | | `min` default 0, `max` required, `value` required | leaf |
| `DateTimeInput` | | `value` (ISO), `enableDate`, `enableTime`, `min`, `max`, `label` | leaf |

### Data binding

The initial renderer conflated three distinct things:

1. **DataBinding** in v0.9 is `{path: "/jsonpointer/into/dataModel"}` — a path to a value in the surface's separate `dataModel`, resolved against the data model the server sends via `updateDataModel` messages.
2. **DynamicString/Number/Boolean** = literal | DataBinding | FunctionCall. Renderer must resolve at render time.
3. **chash:// URIs** are a *nexus-specific* extension, not part of stock a2ui v0.9. They belong in custom actions (`openChash` payloads), not in DataBinding.path. The initial demo used `{path: "chash:..."}` which is a category error.

### ChildList

Children references are either:
- Array of ComponentId strings (static)
- Template object `{componentId, path}` (dynamic — generate one instance per element at the data-model path)

The initial renderer only handled the static array form. Template form deferred — useful for List rendering over data.

### Actions

a2ui v0.9 Actions follow a separate shape (in `common_types.json`) — name + args. The renderer's `{name, payload}` shape was close but should match the spec exactly:
- `action`: object with `call` (name) + `args`
- Or short-hand `action: <ActionName>` per catalog

Worth checking `common_types.json` and `basic_catalog.json#/functions` in detail when writing the producer.

### Accessibility

`accessibility: {label, description}` is on every component via `ComponentCommon` mixin. Initial renderer ignored. Adding ARIA attributes at render time is a small change but a correctness/a11y win.

## What was correct

- Single-file discipline, lit-html, CDN pinned ESM — all kosher.
- Discriminator-dispatch pattern (`renderers[c.type]`) — right shape, wrong field.
- postMessage RPC for host bridge — clean, generalizes well.
- Markdown sidecar — pattern is right, mapping needs updates per new shape.

## Fix plan

1. Switch discriminator `type` → `component`.
2. Switch root resolution: `id === "root"` in component array.
3. Add `dataModel` state + `resolveDynamic(value)` that handles literal | `{path}` (JSON pointer) | FunctionCall (stub).
4. Update component renderers to match v0.9 field names and shapes.
5. Drop chash from DataBinding paths; keep as a custom action only.
6. Add `axis`, `variant`, `justify`, `align`, `direction` styling support.
7. Add accessibility attributes pass-through.
8. Accept full message-envelope payloads (createSurface/updateComponents/updateDataModel) and a "flat" convenience shape that just provides `components` + optional `dataModel`.
9. Add Tabs, DateTimeInput, Video, AudioPlayer for full Basic Catalog coverage.
10. Update demo payload to v0.9-conformant shape.

Producer-side (task #4) must emit exactly this shape with schema validation against `server_to_client.json`.
