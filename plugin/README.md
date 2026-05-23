# palinex Claude Code plugin

Renders [a2ui v0.9](https://a2ui.org/) surfaces inline in Claude Code as sandboxed iframes. One MCP tool, two skills, one slash command.

## Install

### 1. Install the palinex Python package with the MCP + nexus extras

```bash
pip install 'palinex[mcp,nexus]'   # or palinex[all] for validate too
```

This puts the `palinex-mcp` console script on your `PATH` — that's what this plugin's `.mcp.json` invokes.

### 2. Add the plugin to Claude Code

Pick one:

**From this repo's `plugin/` directory (live install):**

```bash
# In a Claude Code session
/plugin install ~/path/to/palinex/plugin
```

**From a GitHub-hosted snapshot (if/when you publish the plugin as a release artifact):**

```bash
/plugin install Hellblazer/palinex
```

Claude Code reads `.claude-plugin/plugin.json` for metadata, `.mcp.json` for MCP server startup, and auto-discovers skills + commands in `skills/` and `commands/`.

### 3. Restart your Claude Code session

The palinex MCP server starts at session boot. After restart, the `render_surface` tool appears as `mcp__plugin_palinex_palinex__render_surface`.

## What's in the plugin

```
plugin/
├── .claude-plugin/plugin.json     # Manifest (name, version, repo, license)
├── .mcp.json                      # Declares the palinex MCP server (palinex-mcp)
├── skills/
│   ├── palinex-overview/SKILL.md  # When palinex applies; static-snapshot guarantee
│   └── surface-emission/SKILL.md  # How to build & emit; worked example
├── commands/
│   └── palinex-render.md          # /palinex-render <payload>
└── README.md                       # this file
```

## What it does

Exposes one MCP tool, `render_surface(payload)`:

- Takes an a2ui v0.9 surface payload (dict or JSON string)
- Wraps it via `palinex.wrap_as_mcp_ui_resource` — a self-contained HTML page with the payload embedded + the canonical renderer in an iframe
- When `[nexus]` extra is installed AND nexus is importable: resolves chash references in the data model via T3 lookup, rewrites `openChash` Button actions to `copyToClipboard`. Static-snapshot semantics — no live host bridge required.
- Returns the resource; Claude Code renders inline.

## Verify it works

After install + restart, ask Claude:

> Use render_surface to display this demo:
>
> `{"version":"v0.9","messages":[{"version":"v0.9","createSurface":{"surfaceId":"hello","catalogId":"a2ui.basic.v0_9"}},{"version":"v0.9","updateComponents":{"surfaceId":"hello","components":[{"id":"root","component":"Text","text":"hello from palinex","variant":"h1"}]}}]}`

You should see an iframe rendered inline with "hello from palinex" as an H1.

## See also

- palinex repo: https://github.com/Hellblazer/palinex
- palinex on PyPI: https://pypi.org/project/palinex/
- Hosted renderer: https://hellblazer.github.io/palinex/
- Inspector (Pyodide-loaded debugging UI): https://hellblazer.github.io/palinex/inspector.html
- a2ui v0.9 spec: https://a2ui.org/specification/v0.9-a2ui/

## License

Apache-2.0 — same as the parent palinex project.
