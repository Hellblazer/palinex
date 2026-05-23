---
name: surface-emission
description: Use when the user asks to render structured data as a card, inline UI, citation list, dashboard, or comparison in Claude Code chat; when building an nx_answer-shaped response with citations; when a tool result has list/table structure that would lose value as plain prose. Triggers for "render this as a card", "show inline", "as a surface", "make this interactive". Walks the construction → render_surface call.
---

# Surface emission

How to actually build and emit a surface in Claude Code via the `render_surface` MCP tool.

## The one-shot pattern

```
1. Decide the payload structure (Card list / Tabs / Column / etc.)
2. Build the a2ui v0.9 JSON payload
3. Call render_surface(payload)
4. Claude Code renders inline; you continue
```

## Minimal payload — synthesis + two citation cards

```json
{
  "version": "v0.9",
  "messages": [
    {
      "version": "v0.9",
      "createSurface": { "surfaceId": "answer", "catalogId": "a2ui.basic.v0_9" }
    },
    {
      "version": "v0.9",
      "updateDataModel": {
        "surfaceId": "answer",
        "path": "/",
        "value": {
          "synthesis": "The agent's summary text goes here.",
          "citations": [
            { "title": "First source", "excerpt": "Excerpt from first chunk.", "chash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" },
            { "title": "Second source", "excerpt": "Excerpt from second chunk.", "chash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" }
          ]
        }
      }
    },
    {
      "version": "v0.9",
      "updateComponents": {
        "surfaceId": "answer",
        "components": [
          { "id": "root", "component": "Column", "children": ["synth", "div", "h", "cites"] },
          { "id": "synth", "component": "Text", "text": { "path": "/synthesis" } },
          { "id": "div", "component": "Divider" },
          { "id": "h", "component": "Text", "text": "Citations", "variant": "h5" },
          { "id": "cites", "component": "List", "children": { "componentId": "card", "path": "/citations" } },
          { "id": "card", "component": "Card", "child": "cardcol" },
          { "id": "cardcol", "component": "Column", "children": ["ctitle", "cexc", "copen"] },
          { "id": "ctitle", "component": "Text", "text": { "path": "/@item/title" }, "variant": "h4" },
          { "id": "cexc", "component": "Text", "text": { "path": "/@item/excerpt" } },
          { "id": "copen", "component": "Button", "child": "copenlbl",
            "action": { "functionCall": { "call": "openChash", "args": { "chash": { "path": "/@item/chash" } } } } },
          { "id": "copenlbl", "component": "Text", "text": "Open chunk" }
        ]
      }
    }
  ]
}
```

Then call:

```
render_surface(<the payload above>)
```

The tool returns an MCP UI resource Claude Code embeds inline. The "Open chunk" buttons get rewritten to copy-to-clipboard (when palinex `[nexus]` extra is installed and the chashes resolve in T3) or pop a "no host bridge" modal (without it — see palinex-overview).

## Composing with nexus tools

If you have chash IDs and want chunk text inline (instead of letting `render_surface` resolve at wrap time):

```
1. Call mcp__plugin_nx_nexus__store_get_many(ids=["aaa…", "bbb…"], collections="knowledge")
2. Take the returned texts; build the payload's data model with the actual text in /citations/N/excerpt
3. Call render_surface(payload)
```

This gives you more control over what gets shown vs what gets resolved. Use this when chashes might point at chunks you want truncated, summarized, or styled before display.

## Common shapes

| What | Container | Notes |
|---|---|---|
| Vertical list of cards | `Column` containing a `List` with template `ChildList` | Use `/@item/...` paths inside the template |
| Tabs across categories | `Tabs` with `tabs: [{title, child}]` per tab | Each child is a Column/List of items |
| Side-by-side comparison | `Row` containing two `Card`s | Each Card with single `child` Column |
| Single button → URL | `Button` with `action.functionCall.call = openUrl` | No chash needed |
| Confirmation dialog | `Modal` with `trigger` + `content` | Modal closes on backdrop click |

## v0.9 envelope vs flat shape

`render_surface` accepts either:

- **Envelope** (`{version, messages: [createSurface, updateDataModel, updateComponents]}`) — what the spec defines; preferred when you want lifecycle clarity
- **Flat** (`{surfaceId, catalogId, components: [...], dataModel: {...}}`) — a convenience for one-shot rendering; the renderer accepts both

## Anti-patterns

| Don't | Do |
|---|---|
| Emit a single paragraph as a surface | Use plain markdown |
| Put HTML strings in `Text.text` | Use Markdown-style emphasis (the renderer respects `**bold**`); for richer content, use multiple `Text` components |
| Nest components inline | Always reference by `id`; declare components flat in the components array |
| Hand-craft action payloads | Use `openUrl`, `copyToClipboard`, `openChash` — the three first-class actions |
| Forget the `root` id | Exactly one component must have `id: "root"` — otherwise render_surface validates structurally and errors |

## See also

- `palinex-overview` — context for what palinex is and when surfaces fit
- `/palinex-render` — explicit command for rendering a pasted JSON payload
- palinex `inspector.html` (hosted at https://hellblazer.github.io/palinex/inspector.html) — paste any payload and see structural validation + live render
