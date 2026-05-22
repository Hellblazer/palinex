# palinex × nexus × Claude Code — sequence diagram

End-to-end sequence for the static-snapshot path: user types a prompt → Claude decides to render a surface → nexus MCP tool produces an MCP UI resource → Claude Code renders it as a sandboxed iframe → user sees the surface inline.

Documents process boundaries (the load-bearing detail) so each hop is explicit. Implements RDR-127 (nexus integration) on top of palinex RDR-001 (architecture).

## Diagram

```mermaid
sequenceDiagram
    autonumber

    actor User

    box rgba(200,220,255,0.15) Process A — Claude Code (Electron)
        participant Main as Node main<br/>process
        participant ChatUI as Chromium renderer<br/>(chat UI)
        participant OuterFrame as Outer iframe<br/>(UI resource)
    end

    box rgba(220,200,255,0.15) Process A''' — Chromium site-isolation
        participant InnerFrame as Inner iframe<br/>(palinex renderer<br/>from github.io)
    end

    box rgba(255,220,200,0.15) Process B — nexus MCP server (Python subprocess)
        participant NexusMCP as FastMCP("nexus")<br/>render_surface tool
        participant Palinex as palinex<br/>(library, in-process)
    end

    box rgba(220,255,220,0.15) Process C / network
        participant T3 as T3 ChromaDB<br/>(local or cloud)
        participant CDN as jsDelivr + GitHub Pages
    end

    %% — prompt → tool call —
    User->>ChatUI: 1. types prompt<br/>"show me chunks X, Y as a surface"
    ChatUI->>Main: 2. Electron IPC (prompt event)
    Main->>Main: 3. Claude (agent) chooses<br/>render_surface(payload)
    Note over Main,NexusMCP: process boundary: stdio JSON-RPC<br/>(Claude Code → MCP subprocess)
    Main->>NexusMCP: 4. tools/call render_surface(payload, collection)

    %% — chash resolution loop (inside Process B) —
    NexusMCP->>Palinex: 5. wrap_as_mcp_ui_resource(<br/>payload, chash_resolver)
    loop for each string in data model
        Palinex->>NexusMCP: 6. chash_resolver(candidate)<br/>(callable, in-process)
        alt 32-char lowercase hex
            NexusMCP->>T3: 7. t3.get_by_id(collection, chash)
            T3-->>NexusMCP: 8. chunk content or None
        else not chash-shaped
            NexusMCP-->>Palinex: (skip; return None)
        end
        NexusMCP-->>Palinex: 9. resolved text or None
    end
    Palinex->>Palinex: 10. substitute resolved text<br/>+ rewrite Button.openChash<br/>→ Button.copyToClipboard
    Palinex-->>NexusMCP: 11. HTML wrapper string

    %% — return path —
    NexusMCP-->>Main: 12. tools/call response<br/>{type:"resource", resource:<br/>{uri, mimeType:"text/html", text}}
    Note over Main,ChatUI: process boundary: Electron IPC<br/>(Node main → Chromium renderer)
    Main->>ChatUI: 13. render UI resource inline
    ChatUI->>OuterFrame: 14. create iframe with wrapper HTML

    %% — outer iframe loads —
    OuterFrame->>CDN: 15. GET hellblazer.github.io/palinex/index.html
    CDN-->>OuterFrame: 16. index.html

    Note over OuterFrame,InnerFrame: process boundary: Chromium site-isolation<br/>(cross-origin iframe → separate renderer process)
    OuterFrame->>InnerFrame: 17. instantiate cross-origin child frame

    %% — inner iframe (palinex renderer) loads —
    InnerFrame->>CDN: 18. GET cdn.jsdelivr.net/.../lit-html@3.2.1
    CDN-->>InnerFrame: 19. lit-html ESM module
    InnerFrame->>InnerFrame: 20. attach postMessage listener

    %% — payload delivery —
    OuterFrame->>InnerFrame: 21. postMessage({type:"a2ui.load", payload})
    InnerFrame->>InnerFrame: 22. render surface<br/>(lit-html → DOM)
    InnerFrame-->>User: 23. citations visible inline<br/>(resolved chunk text already in DOM)

    %% — interaction (static-snapshot path) —
    User->>InnerFrame: 24. clicks "Open chunk"
    InnerFrame->>InnerFrame: 25. copyToClipboard(text)<br/>(pure browser API)
    Note right of InnerFrame: text on clipboard;<br/>NO additional boundary crossings.<br/>nexus is never re-contacted.
```

## Process / boundary key

| Layer | Boundary kind | Transport | Notes |
|---|---|---|---|
| **A** Node main process | OS process | — | Claude Code Electron main; owns the MCP client and spawns MCP server subprocesses |
| **A'** Chromium renderer process | OS process (Electron IPC to A) | Electron contextBridge / IPC channels | Hosts the chat UI; renders messages including MCP UI resources |
| **A''** Outer iframe | Browsing context inside A' (may stay same OS process or go cross-process under site-isolation) | DOM + postMessage to parent | Loaded with the wrapper HTML returned by `render_surface` |
| **A'''** Inner iframe | Browsing context, cross-origin to A' (almost certainly a separate OS process under Chromium site-isolation, since it loads from `hellblazer.github.io` ≠ Claude Code's origin) | postMessage to A''; cannot read A'' DOM | The actual palinex renderer (`index.html` + lit-html) |
| **B** nexus MCP server | OS process (Python subprocess of A) | stdio JSON-RPC | Spawned by A at session start; lives for the session |
| **C** T3 ChromaDB | In-process with B (local mode) OR separate machine (cloud mode) | direct calls / HTTPS | Configurable; nexus picks based on env |
| **CDN** | Network | HTTPS | jsDelivr for lit-html ESM, GitHub Pages for `index.html` |

## What crosses each boundary in this sequence

| Step | Boundary | Payload |
|---|---|---|
| 4 | A → B (stdio) | `tools/call render_surface` request with full payload JSON |
| 7 | B → T3 | doc_id lookup query (one per candidate string in data model) |
| 8 | T3 → B | chunk content (≤ ~4 KB) or None |
| 12 | B → A (stdio) | tools/call response containing the HTML wrapper |
| 13 | A → A' (Electron IPC) | UI resource for inline rendering |
| 15, 18 | A''' → CDN | HTTPS GET for index.html and lit-html (cacheable; one-time per session) |
| 17 | A'' → A''' (site-isolation) | iframe instantiation |
| 21 | A'' → A''' (postMessage) | payload JSON (the surface data) |
| 25 | A''' → OS clipboard | resolved chunk text |

## What does NOT cross any boundary

- The chash resolver callable is injected into palinex **inside process B**. The callable itself never crosses A↔B; only the resolved strings do. (Steps 5–11 all happen inside B.)
- Once the inner iframe receives its payload (step 22), it has everything it needs. No further round-trips to nexus, no further T3 lookups, no further Claude turns. That's the **static-snapshot** guarantee — and the reason this is much cheaper than interactive flows.

## What interactive flows would add

If we later ship the bidirectional protocol (the shape `host-bridge.html` demonstrates), each user click would round-trip:

```
A''' (click)
  → postMessage to A'' (cross-process)
  → Electron IPC A' → A
  → stdio A → B (tool call)
  → in-process call B → T3
  → return path: 5 hops back
```

**Six process boundaries per click** vs zero in the static-snapshot path. That's the architectural cost of "live" UIs and why static comes first.

## Where each repo's code participates

| Repo | What runs where |
|---|---|
| `palinex` (this repo) | Steps 5, 10, 11 (the `wrap_as_mcp_ui_resource` helper) run in B as an imported library. Steps 20, 22, 25 (the renderer) run in A''' as the loaded HTML. |
| `nexus` | Steps 4, 6, 9, 12 (the MCP tool registration + chash resolver) run in B. Plus the entry-point handshake to spawn B as a subprocess at A's startup. |
| `Claude Code` (upstream Anthropic) | Steps 2, 3, 13, 14, 23 (the host) — agent decision, MCP client, UI resource rendering. |
| Upstream open source | a2ui v0.9 spec (Google) shapes the payload format. lit-html (Google) is the renderer's only runtime dep. |

## See also

- `docs/rdr/rdr-001-architecture.md` — palinex architecture decisions
- `docs/rdr/rdr-002-pyodide-as-runtime-augmentation.md` — Pyodide-as-default policy
- nexus `docs/rdr/rdr-127-substrate-decoupled-surface-rendering.md` — integration RDR
- `host-bridge.html` — reference implementation of the bidirectional protocol (for interactive flows)
