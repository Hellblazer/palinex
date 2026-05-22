# surface-render

Single-file HTML renderer for [a2ui v0.9](https://a2ui.org/) surfaces, plus a Python producer-side helper and a host-bridge wrapper.

## Files

- **`index.html`** — the renderer. Open in a browser. Accepts a2ui v0.9 message envelopes via URL param, file picker, or postMessage. lit-html from CDN, no build step.
- **`host-bridge.html`** — reference wrapper that embeds the renderer in an iframe and implements the `a2ui.request`/`a2ui.response` postMessage protocol. For environments (web hosts, MCP UI resources) that need to relay chash resolution back to a data source.
- **`producer.py`** — Python builders that emit v0.9-conformant payloads from typed inputs. Structural validation built in; optional jsonschema deep validation.
- **`A2UI-V09-DIVERGENCE.md`** — audit notes from validating the initial sketch against the v0.9 spec.

## Quick start

Open the renderer with the built-in demo:

```bash
open index.html?demo=1
```

Generate a payload from Python and pipe it in:

```bash
python3 producer.py > demo.json
open "index.html?payload=$(python3 -c 'import base64,sys;print(base64.b64encode(sys.stdin.buffer.read()).decode())' < demo.json)"
```

Run the host-bridge wrapper (mock backend by default):

```bash
open host-bridge.html
```

## URL params

| Param | Effect |
|---|---|
| `?surface=<url>` | Fetch payload JSON from URL |
| `?payload=<base64>` | Decode payload from URL (good for sharing) |
| `?demo=1` | Render built-in demo |

## Component coverage

14 of 18 a2ui Basic Catalog components: Text, Image, Icon, Row, Column, List, Card, Modal, Divider, Button, TextField, CheckBox, ChoicePicker, Slider. The remaining four (Tabs, DateTimeInput, Video, AudioPlayer) follow the same dispatch pattern and are straightforward to add.

## License

Apache 2.0 — see [LICENSE](./LICENSE).
