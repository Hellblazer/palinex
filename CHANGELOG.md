# Changelog

All notable changes to palinex are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project adheres to [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`.github/workflows/release.yml` now builds and attaches the `.mcpb` Claude Desktop extension bundle** on every `v*` tag push, closing the gap RDR-003 §Item 3a flagged (`mcpb pack mcpb /tmp/palinex-<version>.mcpb` via `@anthropic-ai/mcpb`, plus an `mcpb/manifest.json` version-vs-tag parity check that fails loud on drift). Inlined into the existing release workflow rather than a separate `release-mcpb.yml` — single release job prevents two workflows racing on the GitHub Release creation step. Future tags will see `palinex-<version>.mcpb` as a downloadable asset alongside the wheel and sdist. (palinex-hg3)

### Fixed
- **`_pre_resolve_payload` now recognises `updateDataModel.patch`** (`src/palinex/__init__.py`). a2ui v0.9 `updateDataModel` may carry either `value` (full state at path) or `patch` (sparse update). The pre-fix `_data_model_locations` walker only yielded `value` locations, so payloads using `patch` were silently passed through with no chash resolution. Fix extends the walker to yield both shapes for `messages[].updateDataModel` and for the top-level `updateDataModel` variant. Three new tests in `tests/test_builders.py` cover envelope-shape patch, top-level patch, and mixed value+patch in the same payload. (palinex-e7z)

## [0.4.1] — 2026-05-23

Patch release. Live browser shake-out of v0.4.0 surfaced a single bug: the renderer dispatched extension functionCalls (anything other than the three first-class actions) as `method: "functionCall"` instead of using the actual action name, which broke RDR-001 §Item 7 and made the v0.4.0 RDR-004 trust-gate + extension-method end-to-end button-click path unreachable. One-line fix in `web/index.html`. No API changes. Tests now 224.

### Fixed (post-v0.4.0 live shake-out)

- **Renderer dispatch wrapped extension methods as `method: "functionCall"`** (`web/index.html` `handleFunctionCall`), buryıng the actual method name in `params.call`. This broke RDR-001 §Item 7 ("All other actions go through the same postMessage path with method set to the action name") and meant the RDR-004 trust gate could not enforce per-method allowlisting against `trust.actions`. Side effect: MOCK_BACKEND.runSkill / openFile shipped in 0.4.0 were unreachable via renderer button-clicks (the bridge dispatched on `m.method = "functionCall"` and no `functionCall` handler existed). Reproduced live in a `python3 -m http.server` shake-out against `web/host-bridge.html`. One-line fix: `default` branch now dispatches with `hostBridge(fn.call, { ...args, sourceId })`. `tests/test_renderer_dispatch.py` (4 source-regex checks) guards against regression. (palinex-lc9)

## [0.4.0] — 2026-05-23

Trust-gate signature release. RDR-001 Phase 3 (action-registry hardening) closes completely in this cut: the postMessage RPC protocol gets a stable v1.0 spec, the host-bridge example gets `runSkill` and `openFile` reference handlers, and producer-signed action authorisation lands as RDR-004 (Ed25519 + RFC 8785 JCS) with Python producer + JS reference verifier + bridge integration. Plus 13 follow-up fixes from a code-review pass on the trust-gate work — no production-critical residual issues. New public API behind `pip install palinex[sign]`; the base install footprint is unchanged.

### Added
- **`docs/protocols/postmessage-rpc.md`** — normative specification of the postMessage RPC protocol used between the a2ui surface renderer and host bridges. Stabilises the wire contract previously described only in RDR-001 §Item 6 prose so a third-party host bridge (Tauri shell, custom MCP UI host, HTTP sidecar) can be implemented from the spec alone. Covers envelope shapes (`a2ui.ready` / `a2ui.load` / `a2ui.message` / `a2ui.config` / `a2ui.request` / `a2ui.response` / `a2ui.action`), method dispatch + allowlist semantics, the 10 s renderer-side timeout, retry-until-ack handshake (150 ms × 40 attempts ≈ 6 s budget), configuration push via `localStorage`, and a versioning policy (handshake-driven, MAJOR.MINOR, absence == 1.0 inference rule, MAJOR-mismatch normative behaviour). Protocol declared at v1.0; the v0.2.x→0.3.0 wire shape is unchanged. RDR-001 Phase 3 Item 1.
- **`tests/test_protocol_spec.py`** (26 conformance checks) — asserts that `web/index.html` and `web/host-bridge.html` continue to match the wire shape, method names, timeout constant, and retry budget declared by the spec. Catches silent drift between spec and reference implementations on every CI run.
- **`docs/rdr/rdr-004-trust-gate-signature.md`** (draft, status pending substantive-critic gate completion) — Phase 4a design for the producer-action trust gate. Defines: producer identity = Ed25519 public-key fingerprint (RFC 8032); signature scope = whole payload minus signature field via RFC 8785 JCS canonicalization; inline top-level `trust` block carrying `producerId` / `publicKey` / `algorithm` / `actions` / `issuedAt` / `expiresAt` / `nonce` / `signature`; host bridge as authoritative verifier; renderer-side MUST-verify rule for renderer-local actions when pubkey is available; trust store keyed by `producerId` (not name); replay protection via in-memory `(producerId, nonce)` cache for the freshness window; `effective_expiry = min(expiresAt, issuedAt + max_age_seconds)`; default policy `log-only` for backward compatibility. Three concrete scenarios: nexus signing `runSkill`, unknown-producer fallback, key rotation. Substantive-critic pass surfaced six issues (two critical, four significant) — all addressed in the same draft; recorded in §Revision History. Phase 4b implementation tracked under bead `palinex-4ae`; Gap 5 (param-level confused-deputy) under `palinex-rjm`; Gap 6 (operator-UX migration tooling) under `palinex-ciy`. RDR-001 Phase 3 Item 4.
- **`tests/test_rdr_004_structure.py`** (35 structural checks) — asserts RDR-004 retains its frontmatter, canonical RDR sections, all nine `trust`-block field references, the Ed25519 / RFC 8785 algorithm choices, the replay/nonce mechanism, both Gap 5 and Gap 6 follow-up-bead references, the `effective_expiry` precedence rule, the renderer-MUST-verify rule, the producerId-keyed trust store, and the substantive-critic paper trail. Catches design-doc drift until Phase 4b lands behavioural tests.

### Changed
- **RDR-001 Phase 3** — Item 1 ("Document the postMessage RPC protocol as a stable contract") and Item 4 ("Define trust-gate signature") checked off, with the spec doc, RDR-004 design, and Phase 4b implementation as deliverables.
- **RDR-001 §Item 7** amended to reference RDR-004 as the formal mechanism. Trust posture moves from "producer-side discipline" prose to a host-enforced gate: bridge intersects producer's self-declared `trust.actions` with the host's per-producer `allowed_actions` from a `localStorage`-backed trust store; unsigned payloads fall through to `default_policy` (default `log-only`, preserving 0.0.x–0.3.x backward compatibility).
- **`docs/protocols/postmessage-rpc.md` §5.4 (Trust gate hook)** rewritten — previously "a future trust-gate specification will define…", now points at RDR-004 with normative MUST/SHOULD/MAY semantics for bridges that implement the gate. Bridges that don't implement the gate remain conforming under protocol v1.0 (`default_policy: "allow"` is the pre-RDR-004 behaviour).

### Trust-gate (RDR-004 Phase 4b)

Producer side (Python, behind `pip install palinex[sign]`):
- **`palinex.signing` module** — Ed25519 (`cryptography` package) + RFC 8785 JCS canonicalisation (`rfc8785` package), 40 behavioural tests in `tests/test_signing.py`.
- **`SigningKey`** wraps Ed25519 private key, exposes `producer_id` (`k_<base64url-sha256-of-pubkey>`), `public_key_b64u`, `to_bytes`, `sign_bytes`. Construct via `generate()` or `from_seed(32-bytes)`.
- **`sign_payload(payload, key, actions, …)`** attaches the normative `trust` block and signs the JCS canonical form of `payload + trust-block-minus-signature`. Rejects NaN/Infinity floats before canonicalisation; caps `ttl_seconds` at 3600; requires non-empty `actions`; refuses payloads with an existing `trust` block.
- **`verify_payload(payload, now=…)`** — Python reference verifier; verification order matches RDR-004 §Item 4 (structural → identity cross-check → Ed25519 → freshness). Raises one of four `TrustError` subclasses (`SignatureError`, `IdentityError`, `FreshnessError`, `MalformedTrustError`) mapping 1:1 to RDR-004 §Item 6 failure modes.
- **`ReplayCache`** — in-memory `(producerId, nonce)` cache for the freshness window per RDR-004 §Item 4 step 5. Lazy eviction once entries' `expires_at` passes.
- **`Surface.sign(...)`** convenience shim on the builder; lazy-imports `palinex.signing` so base `import palinex` doesn't pull crypto deps.

Host bridge side (JavaScript, single-file):
- **`web/trust-gate.html`** (~325 LOC) — standalone reference verifier; interactive demo for pasting a signed payload and seeing verify-or-reject. JCS in JS, Web Crypto API Ed25519 with `@noble/ed25519@2.1.0` ESM fallback for older browsers, SHA-256 fingerprint computation, `ReplayCache` mirror.
- **`web/host-bridge.html`** (~480 LOC, under the 600 warn / 900 hard ceiling) — integrates `trustGateCheck()` into `loadSurface()` so every payload is verified before delivery; gates `handleRequest()` on `trust.actions ∩ trustStore[producerId].allowed_actions`; loads the trust store from `localStorage` key `a2ui-trust-store.v1`; honours `default_policy = log-only | deny | allow`. Operator helpers `setTrustStore/getTrustStore` exposed via `window.a2uiHostBridge` for console-driven trust-store editing.

Tests:
- **`tests/test_signing.py`** (40 tests) — see producer-side bullet above.
- **`tests/test_trust_gate.py`** (24 tests) — three RDR-004 scenarios (nexus signs runSkill, untrusted producer + default-policy fallback, key rotation with `valid_until` and hard revocation); replay attack within freshness window; JS-source conformance assertions ensuring `web/trust-gate.html` and `web/host-bridge.html` continue to declare the same primitives, required-fields set, and algorithm strings as the Python reference; LOC-ceiling guards on both JS files.

Deferred to follow-up bead (palinex-rl0): renderer-side MUST-verify rule from RDR-004 §Item 4. `web/index.html` is at 857 LOC against a 900 hard ceiling; adding Web Crypto Ed25519 + JCS inline would push past it. The bridge-side check is the security-critical path; renderer-side is defense-in-depth for renderer-local actions.

### Fixed (post-merge code-review findings on RDR-004 Phase 4b)

A code-review-expert pass on the just-merged trust-gate work surfaced two critical bugs and three important issues. All addressed in one follow-up commit (palinex-fjh):

- **Critical: `handleRequest` logic gap for signed-but-unknown-producer payloads.** Previous code only checked `verifiedTrust && verifiedActions !== null` (known producer) and `verifiedTrust === null && policy === 'deny'` (unsigned + deny). When `verifiedTrust` was non-null AND `verifiedActions` was null (valid signature, producer not in trust store), neither branch fired and the backend ran unfiltered — defeating RDR-004 §Item 5's commitment that unknown-producer bridge-routed methods are denied under `log-only`. Added the missing branches: signed-unknown-producer denies under any policy except `'allow'`; unsigned + log-only denies bridge-routed methods explicitly.
- **Critical: trust-store `valid_until` field was never enforced.** `trustStoreAllowedActions` ignored `entry.valid_until` entirely. A rotated-out key remained trusted indefinitely, breaking RDR-004 §Item 6's "Producer key rotated out" failure mode. Added a `Date.parse(entry.valid_until) < Date.now()` check that returns `null` (treated as unknown producer) when the key has expired.
- **Important: `b64uEncode` used `btoa(String.fromCharCode(...bytes))`.** The spread operator on a `Uint8Array` of 64+ KB crashes V8/SpiderMonkey with `RangeError: Maximum call stack size exceeded`. Current callers pass 32/64 bytes (safe), but `b64uEncode` is exported on `window.a2uiTrustGate` as a reusable primitive. Replaced with a loop in both `web/trust-gate.html` and `web/host-bridge.html`.
- **Important: `_reject_non_finite_floats` didn't check dict keys.** Python `dict` accepts non-string hashables (including `float("nan")`) as keys, but JSON / JCS require string keys. A NaN key would silently pass the producer-side guard and surface as a `TypeError` deep inside `rfc8785.dumps` rather than a friendly `MalformedTrustError`. Added an `isinstance(k, str)` check and a `bool`-isn't-float early-return for clarity (Python's `True == 1.0` quirk).
- **Minor: dead expression `logLine('warn' in {} ? 'err' : 'req', ...)`.** Always evaluated to `'req'`. Replaced with `'err'` for unknown-producer warnings.

13 new tests in `tests/test_signing.py` and `tests/test_trust_gate.py` cover: nested non-finite floats at depth > 1, list-of-dict non-finite, non-string dict keys, `bool` round-trip, three `valid_until` cases (future/past/absent), source-regex assertions on both new bridge gate branches, byte-level JCS canonicalization stability (number formatting `1.0 → "1"`, key sort order), and Unicode NFC/NFD preservation (no normalization).

### Phase 3 closeout (RDR-001 Items 2 + 3)

The two remaining RDR-001 Phase 3 items shipped together (palinex-i10, palinex-xwr), formally closing out the action-registry-hardening epic:

- **`runSkill` formalised in `web/host-bridge.html`** — handler was already present in both `MOCK_BACKEND` and `HTTP_BACKEND` (it shipped alongside the trust-gate work because the gate's scenarios exercise it). Now formally tested via `tests/test_host_bridge.py` — regex asserts the handler exists in both backends, that `HTTP_BACKEND.runSkill` POSTs to `{baseUrl}/skill/{name}`, and that the param shape stays `{name, args}`. Catches silent rename or removal.
- **`openFile` added to `web/host-bridge.html`** — new `MOCK_BACKEND.openFile` and `HTTP_BACKEND.openFile` handlers. Param shape `{path: string, line?: number, column?: number}`. Mock returns `{opened: false, reason: 'mock-backend', message: …}` so callers can branch on the no-op signal. HTTP backend POSTs to `{baseUrl}/file/open`. The handler is documented for editor-host integrations (VS Code webview, Cursor, JetBrains remote) that route through their native `openTextDocument` / `revealRange` APIs.
- **Reference-backend documentation block** — comment at the top of `MOCK_BACKEND` enumerates the three resolver paths a host can plug into: `MOCK_BACKEND` (demo / local development), `HTTP_BACKEND(baseUrl)` (sidecar service like a nexus daemon), `window.hostBridgeResolver` (embedder-injected object for Tauri / custom WebSocket / MCP). `getBackend()` picks the first available in that order. Future method additions follow the same pattern: add to both `MOCK_BACKEND` and `HTTP_BACKEND` so the demo works out-of-the-box AND a real sidecar can serve it.
- **`tests/test_host_bridge.py`** (11 conformance checks) — backend registry shape, both methods declared in both backends with the documented param shapes, mock openFile returns the documented signal shape, resolver-path documentation present, LOC budget guard (warn at 600 / hard at 900 per `html-tool-patterns`).

With these landings, **RDR-001 Phase 3 is complete**: all four Items checked off (protocol doc + `runSkill` + `openFile` + trust-gate). The epic `palinex-7n1` is closeable.

## [0.3.0] — 2026-05-23

Hardening release. Sweeps up the host-bridge and bundle work that shipped on main between 0.2.0 and now, plus the marketplace conversion to a pinned-source release model so future main commits don't surprise installed users. RDR-001 and RDR-003 both formally accepted in this cycle.

### Added
- **Renderer `a2ui.ready` handshake** (`web/index.html`): the v0.9 renderer now posts `{type: "a2ui.ready"}` to `window.parent` after attaching its `message` listener. Wrappers use this to stop their retry loops as soon as the renderer is observably ready, keeping the common-case delivery at one round-trip while still tolerating warm-cache loads.
- **`web/host-bridge.html` retry-until-ack delivery** matching the contract introduced for the MCP-UI wrapper in 0.2.0. The reference bridge now actually demonstrates the discipline RDR-001 §Item 6 requires of all wrappers — previously it called bare `postMessage` and would have silently re-introduced the warm-cache race for any downstream that copied it.
- **DEMO surface uses real 32-char chashes** (`web/index.html`): `cfbd937e6addd5674fb6cde5b04a9fe1` (RDR-127 Substrate-Decoupled Surface Rendering) and `e3458aa9ce0efa7a148302d4f98c50e2` (RDR-016 AST Chunk Line Range Bug). `?demo=wrapped` inlines matching real-content fallbacks so the demo is meaningful with or without a nexus host wired up.
- **`.claude-plugin/marketplace.json` pinned-source release model**: `plugins[0].source` converted from the relative-path string `"./plugin"` to the `git-subdir` object form with `ref: "v0.3.0"`. Main can advance freely (including edits to marketplace.json itself); installed plugins only update when a release tag is cut. See `global_directives/marketplace-pinned-source-release-model` in nexus T2 for the directive.
- **`tests/test_plugin_structure.py`** (12 parity checks): enforces that every version-bearing manifest agrees with `pyproject.toml`, and that `marketplace.json` source stays in the `git-subdir` object form (reverting to relative-path would defeat the pinned-source model). Mirrors the pattern from `Hellblazer/nexus`.

### Changed
- **`mcpb/pyproject.toml`** dep tightened from `palinex[mcp]>=0.2.0` to `palinex[mcp,nexus]>=0.2.0`. The previous spec omitted the `[nexus]` extra, so the Claude Desktop `.mcpb` bundle's `.venv` never installed `conexus` and server-side chash resolution silently degraded to pass-through. With the extra in place, `render_surface` resolves real chashes against nexus T3 before the wrapper HTML is returned.
- **`mcpb/manifest.json`** description corrected to remove the false claim that Claude Desktop renders `ui://` HTML resources inline. The new text qualifies which hosts mount them inline (claude.ai web, custom MCP UI hosts) and points readers at RDR-001 §Item 4 for Desktop delivery paths. The bundle provides the MCP server only; inline visible surfaces require a host that mounts the resource type.
- **RDR-001** flipped to `status: accepted` after a two-pass substantive-critic gate. Item 6 amended with the "Delivery robustness — retry-until-ack handshake" subsection; Item 4 corrected to reflect that only `wrap_as_mcp_ui_resource` is a producer-side helper; §Context A1 qualified with the Claude Code Desktop v2.1.149 inline-rendering limitation; Phase 2 checked off (shipped 0.2.0); Alt 6 added covering `srcdoc` / `blob:` iframe alternatives; test count corrected (19 → 53), CI matrix (3.10-3.13 → 3.12-3.13), renderer LOC (708 → 845).
- **RDR-003** flipped to `status: accepted` and amended to cover the `.mcpb` bundle as a fourth distribution channel (Item 3a). Item 5 versioning policy rewritten with explicit `0.0.x → 0.1.0 → 0.2.0` bump history and forward-looking 0.3.0 pointer.
- **`docs/rdr/README.md`** gains a per-RDR index table and an honest description of the file↔T2 lifecycle relationship.

### Fixed
- Wrapper bootstrap shipped in 0.1.0 had two delivery races (about:blank early-fire and warm-cache late-attach). 0.2.0 fixed the wrapper; 0.3.0 fixes the reference bridge (`host-bridge.html`) to match. Documented as RDR-001 §Item 6 "Delivery robustness."

### Tracked but not yet shipped
- `palinex-hg3` (P2) — add `release-mcpb.yml` workflow that builds the `.mcpb` archive on `v*` tag push and attaches it as a GitHub release asset. Currently the bundle is built locally and distributed out-of-band.
- `palinex-e7z` (P3) — `_pre_resolve_payload` doesn't recognize `updateDataModel.patch` shape; only the canonical `path + value` shape that `Surface.emit()` produces. Hand-crafted payloads using `patch` silently pass through unresolved.
- RDR-001 Phase 3 beads (`palinex-7n1`, `-ytv`, `-i10`, `-xwr`, `-pr1`) — action registry hardening (protocol doc, runSkill, openFile, trust-gate signature).

## [0.2.0] — 2026-05-23

Substantive correctness fix for the MCP-UI wrapper plus completion of the v0.9 Basic Catalog.

### Added
- **Phase 2 Basic Catalog components** (`web/index.html` + `src/palinex/__init__.py`): Tabs (titled tabs + children), DateTimeInput (ISO 8601 value + optional min/max), Video (URL + minimal controls), AudioPlayer (URL + description). `BASIC_COMPONENTS` now lists all 18 v0.9 catalog components.
- **`a2ui.ready` handshake**: renderer side added in this version (wrapper side started using it in 0.2.0; the matching renderer ping landed alongside).
- **Claude Desktop `.mcpb` extension** scaffold (`mcpb/`): manifest v0.4, uv-managed `.venv` wrapper, thin `src/server.py` entry point that delegates to `palinex.mcp.server.main()`. Initially merged from develop as part of the release.

### Fixed
- **About:blank race in the `render_surface` wrapper** (`src/palinex/__init__.py`): replaced the readyState-gated single-shot `postMessage` delivery with a load-listener + 150ms × 40-attempt retry loop bounded at ~6s. Two failure modes addressed: (a) early fire to the iframe's initial about:blank document before the cross-origin nav commits, and (b) late attach when the renderer's load event has already fired. `setSurface` is idempotent so repeated delivery is safe. See PR #1 and RDR-001 §Item 6 amendment.

### Architecture
- The wrapper bootstrap is now described as a stable contract (retry-until-ack) in RDR-001 §Item 6. Any new wrapper (Tauri host, custom web shell, an HTTP sidecar's index page) must implement the same pattern.

## [0.1.0] — 2026-05-22

Major restructure: palinex is now the **UI front-end for nexus** — library + Claude Code plugin + Pyodide-loaded inspector. Builds on the 0.0.6 wrapped-demo variant by superseding the inline JS workaround with the proper Pyodide-driven live-render panel in the inspector.

### Added
- **Claude Code plugin** (`plugin/` directory): manifest, MCP server registration, two skills (`palinex-overview`, `surface-emission`), and a `/palinex-render` command. Installable via `/plugin install` from this repo. Auto-starts the palinex MCP server at Claude Code session boot.
- **MCP server** (`src/palinex/mcp/`): FastMCP server exposing one tool, `render_surface(payload, title, collection, renderer_url)`. Console script `palinex-mcp` declared via `[project.scripts]`.
- **nexus integration shim** (`src/palinex/nexus_bridge.py`): lazy import of nexus internals; `chash_resolver(chash)` validates RDR-108 32-char hex shape, looks up via T3, returns chunk text or None. Cached import outcome (success or ImportError) for O(1) repeat calls. Behind the `[nexus]` extra.
- **`[nexus]` and `[mcp]` and `[all]` optional dependency extras** in `pyproject.toml`. Library install (`pip install palinex`) stays nexus-free; full integration is `pip install palinex[all]`.
- **Inspector live-render tab** (`web/inspector.html`): tabbed right column (Markdown / Paths / Live render). Live tab has editable textarea + Re-render button + iframe pointing at `./index.html`. postMessage delivers payload to the iframe; edits and re-renders work without leaving the page. Subsumes any need for a separate playground page.
- **RDR-003** (`docs/rdr/rdr-003-plugin-and-source-layout.md`): codifies the packaging decisions — Claude Code plugin, nexus-front-end role, src/ + web/ + plugin/ layout, no HTTP sidecar (per RDR-002 Pyodide-as-default).
- 24 new tests bring total to 59 (13 for nexus_bridge, 11 for the MCP server) — all green across the Python 3.10–3.13 matrix.

### Changed
- **`requires-python = ">=3.12"`** (was `>=3.10`). The `[nexus]` extra pulls `conexus>=4.34` which requires Python 3.12+; uv's dependency resolver fails the whole `[all]` extra when palinex declares broader support than nexus does. Honest fix: track nexus's support window. Library-only users on 3.10/3.11 can stay on palinex 0.0.x. CI + release matrices dropped to `["3.12", "3.13"]` accordingly.
- **Source layout**: `palinex/` → `src/palinex/` (standard src-layout). Tests find the package via `[tool.pytest.ini_options] pythonpath = ["src"]` — no PYTHONPATH=. needed.
- **Static frontend**: `index.html`, `host-bridge.html`, `inspector.html` → `web/`. GitHub Pages deploys from `web/` via a new `.github/workflows/pages.yml` workflow (switched from legacy `main/` to GitHub Actions deployment).
- **AGENTS.md** + README updated for the new layout and install paths.
- **html-tool-patterns skill** LOC threshold raised: warn 600, stop 1100 (was 900). Empirical-observations table added to document realistic ceilings for tool variants (renderer ~770, host-bridge ~190, inspector ~1010).
- 0.0.6's wrapped-demo `?demo=wrapped` JS path stays in `web/index.html` — the inspector's Pyodide-driven live render is the production path; the inline-JS wrap is the lightweight no-deps fallback for users who don't want the inspector's 10MB Pyodide download.

### Architecture
- nexus does **not** depend on palinex. The dependency direction is strictly palinex → nexus (and only via the `[nexus]` extra).
- The HTTP sidecar that was briefly scoped is dropped per RDR-002. Pyodide-based pages (inspector.html) cover the non-Claude-Code use cases.
- A separate playground page is NOT shipped — inspector.html serves both debugging and live-render.

### Companion in nexus
- nexus RDR-127 v2 (in PR #926) records the corresponding non-decision: nexus ships no surface-rendering code. RDR-123 and RDR-124 remain superseded by RDR-127, with tombstones refreshed to point at the palinex plugin layer.

## [0.0.6] — 2026-05-22

Wrapped-demo variant in the standalone renderer.

### Added
- Renderer `?demo=wrapped` URL parameter renders the same demo payload as `?demo=1` but with palinex 0.0.5's `wrap_as_mcp_ui_resource` pre-resolution logic applied in JS — chash references in the data model are substituted with text, and `openChash` Button actions are rewritten to `copyToClipboard`. Demonstrates the wrap end-state without a real producer or chash store; click "Open chunk" → resolved text in clipboard, no host bridge dead-end modal.
- Empty-state link "try the wrapped variant" alongside the existing "render demo" button.

### Why
Previously the hosted standalone demo showed the host-bridge dead-end modal when users clicked "Open chunk" — accurate documentation of standalone behavior but confusing as a first experience. The wrapped variant shows the alternative path (palinex pre-resolution) inline, so users can see both architectural modes from the same hosted page.

## [0.0.5] — 2026-05-22

MCP UI resource helper for embedding palinex surfaces inside Claude Code (or any host that consumes MCP UI Apps).

### Added
- `palinex.wrap_as_mcp_ui_resource(payload, *, chash_resolver=None, renderer_url=..., title=...)` — wraps an a2ui v0.9 surface payload as a self-contained HTML page suitable for the `text` field of an MCP UI resource. Hosts the canonical renderer in an iframe, posts the payload on load, no live host bridge required for static snapshots.
- When `chash_resolver` is provided, pre-resolves: any string value in the data model that the resolver returns text for is replaced; any `Button` with `openChash` action is rewritten to `copyToClipboard` carrying the same path reference. Click → resolved text copied to clipboard. No round-trip to the host needed.
- 7 new tests covering shape envelope + flat shape, resolver substitution, action rewrite, non-`openChash` actions left alone, payload immutability (deep-copied internally), HTML escaping of renderer URL, and `</script>` injection protection.
- Exported as `palinex.wrap_as_mcp_ui_resource` (top-level).

### Notes
- This is the simple-path Claude Code integration (palinex RDR-001 §Item 4 "MCP UI resource" delivery). Static snapshots only; interactive flows (live data fetch on click) require the bidirectional `a2ui.request` / `a2ui.response` protocol which palinex's `host-bridge.html` reference still demonstrates.

## [0.0.4] — 2026-05-22

Action-context bug fix + clearer empty-backend UX. No new features.

### Fixed
- Renderer (`index.html`) `Button` now preserves render-time data-model context (including `@item` template alias) across the gap between render and click. Previously, `Surface` actions inside a template iteration emitted unresolved `{path: "/@item/..."}` payloads because `state.dataModel` was restored to the parent context before the click handler fired. New `withDataModel(model, fn)` helper installs the captured context temporarily during dispatch. Visible symptom: `openChash` action payload contained the raw DataPath instead of the resolved chash string when fired from a List-template Button.

### Changed
- Host-bridge (`host-bridge.html`) shows a prominent banner when no backend is configured, explaining the consequence (surface actions return errors) and offering two explicit affordances: "Try mock (stub responses)" and "Enter sidecar URL…". Previous behavior was silent — backend was just "none" in the status pill, and surface actions failed with no UI feedback. The mock backend is now opt-in via the banner button, not a hidden default.

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
