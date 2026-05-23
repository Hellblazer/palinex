---
name: palinex-overview
description: Use when the user mentions palinex, a2ui surfaces, render_surface MCP tool, MCP UI resources, surface rendering in chat, or asks how to display structured data inline in Claude Code. Establishes core context — palinex is a Python library + this MCP plugin + a renderer hosted on GitHub Pages, all wrapping the open a2ui v0.9 spec.
---

# palinex Overview

**palinex** (palin- "again" + nexus "bond") is a Python library + Claude Code plugin + hosted single-file HTML renderer for [a2ui v0.9](https://a2ui.org/) surfaces. Each `updateComponents` and `updateDataModel` message rewrites the surface in place — the parchment gets revised.

## What this plugin gives Claude Code

A single MCP tool, `render_surface`, that takes an a2ui v0.9 surface payload (dict or JSON string) and returns an embedded UI resource Claude Code renders inline as a sandboxed iframe in chat. The renderer is a single-file HTML page hosted at `https://hellblazer.github.io/palinex/index.html`.

## When to reach for it

| Use case | Right fit? |
|---|---|
| Citation cards (synthesis + N chunks, each clickable) | Yes |
| RDR audit dashboards | Yes |
| Plan / bead inspectors with structured fields | Yes |
| Subagent findings as cards instead of bulk prose | Yes |
| Comparison tables across N items | Yes |
| Single paragraph of text | No — markdown is right |
| Code blocks | No — fenced markdown |
| Long-form prose | No |

## The static-snapshot guarantee

`render_surface` produces a **static snapshot**, not a live interactive UI. The surface is pre-resolved at wrap time: chash references in the data model get substituted with chunk text via nexus T3 (when palinex's `[nexus]` extra is installed); `openChash` Button actions get rewritten to `copyToClipboard`. Click handlers work as pure browser actions — no round-trip to nexus, no agent loop required.

Interactive flows (button → fetch fresh data → update surface) are a separate, more complex path (the postMessage RPC protocol palinex's `host-bridge.html` demonstrates). Not what this plugin ships.

## Two ways to compose with nexus tools

When palinex's `[nexus]` extra is installed:

**Option A — auto-resolve in the tool.** Construct a payload with chash references in the data model; `render_surface` looks them up and substitutes inline.

**Option B — agent-composed.** Call `mcp__plugin_nx_nexus__store_get_many` (or similar) to fetch chunks, build the payload with the actual text inline (no chash references), pass to `render_surface`. More control; works without `[nexus]`.

Either is fine. (A) is shorter; (B) lets the agent be selective.

## See also

- `surface-emission` — companion skill with concrete usage patterns and a worked example
- `/palinex-render` — explicit command for rendering a pasted JSON payload
- palinex repo: https://github.com/Hellblazer/palinex
- a2ui v0.9 spec: https://a2ui.org/specification/v0.9-a2ui/
