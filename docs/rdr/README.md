# palinex RDRs

Architectural decisions for the palinex project. Each RDR captures one durable decision with enough context that a future reader can judge whether the decision still holds.

## Index

| ID | Title | Status | Type | Priority |
|---|---|---|---|---|
| [001](rdr-001-architecture.md) | palinex Architecture: a2ui v0.9 IR, SurfaceBroker Port, Three Delivery Shapes, postMessage Host Bridge | accepted (2026-05-23) | Architecture | high |
| [002](rdr-002-pyodide-as-runtime-augmentation.md) | Pyodide as Preferred Runtime Augmentation: Producer + Validator + Inspector In-Browser, No Daemon | draft | Architecture | medium |
| [003](rdr-003-plugin-and-source-layout.md) | Packaging: Claude Code Plugin + Claude Desktop .mcpb Bundle + nexus-front-end Role + src/ Layout | accepted (2026-05-23) | Architecture | high |
| [004](rdr-004-trust-gate-signature.md) | Trust-Gate Signature: Producer-Identity Claims and Host-Enforced Action Allowlists for a2ui Surfaces | draft | Security | high |

## Conventions

Numbering: `rdr-NNN-kebab-title.md`, sequential. Frontmatter mirrors the nexus RDR convention (title, id, type, status, priority, author, created, accepted_date, related_rdrs).

Status values: `draft`, `accepted`, `superseded`, `withdrawn`.

Lifecycle: T2 records under project `palinex_rdr` mirror file status for accepted RDRs (title `<NNN>`); gate results under title `<NNN>-gate-latest`. T2 is process-authority; file frontmatter is the canonical content. Self-healing logic in `/nx:rdr-accept` reconciles drift in either direction.

When updating an RDR: never rewrite history. Append a `## Revision History` entry, or mark status and write a successor.
