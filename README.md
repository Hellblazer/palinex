# palinex

**palin-** (Greek, "again") **+ nexus** (Latin, "bond") — surfaces get rewritten.

A small library + reference renderer for [a2ui v0.9](https://a2ui.org/) surfaces. Each `updateComponents` and `updateDataModel` rewrites what came before; the rendering surface is the bond that the agent revises in place.

## What's in here

- **`src/palinex/`** — Python package. Typed builders that emit v0.9-conformant payloads from native Python; structural validation built in, optional jsonschema deep validation via `pip install palinex[validate]`. Also ships an MCP server (`python -m palinex.mcp`) and an HTTP sidecar (`palinex serve`).
- **`web/index.html`** — single-file HTML renderer. Open in a browser. Accepts v0.9 message envelopes via URL param, file picker, or postMessage. lit-html from CDN, no build step.
- **`web/host-bridge.html`** — reference wrapper that embeds the renderer in an iframe and implements the `a2ui.request` / `a2ui.response` postMessage protocol. For hosts (Claude Code MCP UI resources, custom web shells) that bridge agent-side data sources to the renderer.
- **`web/inspector.html`** — single-file Pyodide-loaded surface validator. Paste/drop/URL-load a payload; get structural validation, component table with role inference (root / child of X / template / orphan), data-path walker, and (opt-in) deep schema validation + markdown sidecar via `palinex[validate]` running in-browser.
- **`plugin/`** — Claude Code plugin (manifest + MCP server registration + skills + commands). Installable directly from the GitHub URL; auto-starts the palinex MCP server at Claude Code session boot.
- **`A2UI-V09-DIVERGENCE.md`** — audit notes against the v0.9 spec; documents the structural choices the renderer and producer make.

## Install

```bash
pip install palinex                  # builders only
pip install palinex[validate]        # + jsonschema for deep validation
```

Or clone for the renderer + host bridge:

```bash
git clone https://github.com/Hellblazer/palinex
```

## Quick start

Renderer with the built-in demo:

```bash
open web/index.html?demo=1
```

Generate a payload from Python and pipe it in:

```python
from palinex import Surface, DataPath

s = Surface(surface_id="demo", catalog_id="a2ui.basic.v0_9")
s.data["greeting"] = "Hello, surface."
body = s.column([
    s.text(path="/greeting", variant="h2"),
    s.divider(),
    s.button(s.text("Click me"), action=s.open_url("https://example.com")),
])
s.set_root(body)
print(s.to_json())               # v0.9 message-envelope payload
print(s.to_markdown())           # lossless markdown sidecar
s.validate()                     # structural pass
```

The hosted renderer at <https://hellblazer.github.io/palinex/> accepts payloads via:

| Param | Effect |
|---|---|
| `?surface=<url>` | Fetch payload JSON from URL |
| `?payload=<base64>` | Decode inline payload (good for sharing) |
| `?demo=1` | Render the built-in demo |

## Component coverage

All 18 a2ui v0.9 Basic Catalog components: Text · Image · Icon · Video · AudioPlayer · Row · Column · List · Card · Tabs · Modal · Divider · Button · TextField · CheckBox · ChoicePicker · Slider · DateTimeInput.

## License

Apache 2.0 — see [LICENSE](./LICENSE).
