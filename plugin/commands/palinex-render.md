---
description: Render an a2ui v0.9 surface payload inline in chat via palinex.render_surface
argument-hint: <JSON payload | path to .json file | inline payload>
---

Render an a2ui v0.9 surface payload as an inline MCP UI resource in this chat.

**Input from user:** `$ARGUMENTS`

## What to do

1. Parse `$ARGUMENTS`:
   - If it looks like JSON (starts with `{` or `[`), treat as the payload directly
   - If it's a file path ending in `.json`, read the file content
   - Otherwise: ask the user what they want rendered, or default to the palinex demo payload at `https://raw.githubusercontent.com/Hellblazer/palinex/main/web/index.html#demo` (don't fetch — just explain how to construct one)

2. Validate the payload looks like a2ui v0.9 — should be a dict with either:
   - `{version: "v0.9", messages: [...]}` (envelope shape)
   - `{components: [...], dataModel?, surfaceId?, catalogId?}` (flat shape)
   If neither, tell the user the expected shape and stop.

3. Call `mcp__plugin_palinex_palinex__render_surface` with the payload. Pass the dict directly.

4. The tool returns an MCP UI resource (`{type: "resource", resource: {...}}`). Claude Code renders the HTML inline as a sandboxed iframe.

5. If the payload had chash references and palinex's `[nexus]` extra is installed, those got auto-resolved at wrap time. If not, the buttons fall through to the "no host bridge" modal — explain that to the user if they ask.

## When to use this

Direct user invocation. Useful for:

- Testing a payload while iterating
- Showing a known-good demo
- Debugging "why is my payload not rendering"

For everyday work where the agent decides to render a surface (e.g., dressing up an `nx_answer` response with citation cards), don't wait for the user to invoke `/palinex-render` — call the tool directly.
