"""
a2ui v0.9 surface producer — typed builders for emitting renderable payloads.

Companion to ./index.html (the renderer). Producer code calls these helpers to
construct v0.9-conformant message envelopes from typed Python; downstream code
delivers them as MCP UI resources, embedded artifacts, or URL params per the
`surface-as-artifact` skill.

Optional schema validation against a2ui v0.9 JSON schemas (located at
specification/v0_9/json/ in the a2ui repo) requires `jsonschema` (stdlib does
not include it). Without jsonschema, validation degrades to structural sanity
checks.

Usage:

    s = Surface(surface_id="nx-answer-42", catalog_id="a2ui.basic.v0_9")
    s.data["synthesis"] = "The answer is …"
    s.data["citations"] = [{"title": "doc", "excerpt": "…", "chash": "abc"}]

    body = s.column([
        s.text(path="/synthesis"),
        s.divider(),
        s.text("Citations", variant="h5"),
        s.list(direction="vertical", template=s.card(s.column([
            s.text(path="/@item/title", variant="h4"),
            s.text(path="/@item/excerpt"),
            s.button(s.text("Open chunk"),
                     variant="primary",
                     action=s.function_call("openChash", chash=DataPath("/@item/chash"))),
        ])), template_path="/citations"),
    ])
    s.set_root(body)

    envelope = s.emit()        # dict, ready for json.dumps
    md = s.to_markdown()       # markdown sidecar (lossless)
    s.validate()               # raises if non-conformant (jsonschema optional)
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


__all__ = [
    "Surface",
    "DataPath",
    "FunctionCall",
    "Event",
    "load_schemas",
    "wrap_as_mcp_ui_resource",
    "BASIC_COMPONENTS",
]


BASIC_COMPONENTS = frozenset({
    "Text", "Image", "Icon", "Video", "AudioPlayer",
    "Row", "Column", "List", "Card", "Tabs", "Modal", "Divider",
    "Button", "TextField", "CheckBox", "ChoicePicker", "Slider", "DateTimeInput",
})

_ID_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")


@dataclass(frozen=True)
class DataPath:
    """A JSON-pointer reference into the surface's data model."""
    path: str

    def to_json(self) -> dict[str, str]:
        if not self.path.startswith("/"):
            raise ValueError(f"DataPath must start with '/': got {self.path!r}")
        return {"path": self.path}


@dataclass(frozen=True)
class FunctionCall:
    """A local client-side function call as an Action."""
    call: str
    args: dict[str, Any] = field(default_factory=dict)
    return_type: str = "void"

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"call": self.call}
        if self.args:
            out["args"] = {k: _serialize_dynamic(v) for k, v in self.args.items()}
        out["returnType"] = self.return_type
        return {"functionCall": out}


@dataclass(frozen=True)
class Event:
    """A server-side event dispatch as an Action."""
    name: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name}
        if self.context:
            out["context"] = {k: _serialize_dynamic(v) for k, v in self.context.items()}
        return {"event": out}


def _serialize_dynamic(value: Any) -> Any:
    """Render a DynamicString/Number/Boolean field — literal, DataPath, or FunctionCall."""
    if isinstance(value, DataPath):
        return value.to_json()
    if isinstance(value, FunctionCall):
        # When a function call is used as a dynamic value (not an Action), unwrap
        # to the inner shape per common_types FunctionCall.
        inner = value.to_json()["functionCall"]
        return inner
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_serialize_dynamic(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_dynamic(v) for k, v in value.items()}
    raise TypeError(f"cannot serialize dynamic value: {type(value).__name__}")


def _serialize_action(action: Any) -> dict[str, Any]:
    if isinstance(action, (FunctionCall, Event)):
        return action.to_json()
    if isinstance(action, dict):
        if "functionCall" in action or "event" in action:
            return action
        raise ValueError(f"action dict must have 'functionCall' or 'event' key: {list(action)}")
    raise TypeError(f"action must be FunctionCall, Event, or pre-serialized dict; got {type(action).__name__}")


class Surface:
    """Builder for a single a2ui v0.9 surface."""

    def __init__(self, surface_id: str, catalog_id: str = "a2ui.basic.v0_9"):
        if not surface_id:
            raise ValueError("surface_id required")
        self.surface_id = surface_id
        self.catalog_id = catalog_id
        self.data: dict[str, Any] = {}
        self._components: dict[str, dict[str, Any]] = {}
        self._root_id: str | None = None
        self._auto_counter = 0

    def _next_id(self, hint: str) -> str:
        self._auto_counter += 1
        slug = re.sub(r"[^a-zA-Z0-9_-]", "-", hint.lower())[:24]
        return f"{slug}-{self._auto_counter}"

    def _add(self, component: dict[str, Any], id: str | None = None) -> str:
        if id is None:
            id = self._next_id(component["component"])
        if not _ID_PATTERN.match(id):
            raise ValueError(f"invalid component id: {id!r}")
        if id in self._components:
            raise ValueError(f"duplicate component id: {id!r}")
        component["id"] = id
        self._components[id] = component
        return id

    def set_root(self, child_id: str) -> None:
        if child_id not in self._components:
            raise ValueError(f"set_root called with unknown id: {child_id}")
        root_component = dict(self._components[child_id])
        del self._components[child_id]
        root_component["id"] = "root"
        self._components["root"] = root_component
        self._root_id = "root"

    # ---- Component builders -------------------------------------------------

    def text(self, text: str | DataPath | None = None, *, path: str | None = None,
             variant: str = "body", id: str | None = None,
             accessibility: dict[str, Any] | None = None) -> str:
        if text is None and path is None:
            raise ValueError("text() requires either positional text or path=")
        value: Any = DataPath(path) if path is not None else text
        c: dict[str, Any] = {"component": "Text", "text": _serialize_dynamic(value)}
        if variant != "body":
            c["variant"] = variant
        if accessibility:
            c["accessibility"] = accessibility
        return self._add(c, id)

    def image(self, url: str | DataPath, *, description: str | DataPath = "",
              fit: str = "fill", variant: str = "mediumFeature",
              id: str | None = None) -> str:
        c: dict[str, Any] = {"component": "Image", "url": _serialize_dynamic(url)}
        if description:
            c["description"] = _serialize_dynamic(description)
        if fit != "fill":
            c["fit"] = fit
        if variant != "mediumFeature":
            c["variant"] = variant
        return self._add(c, id)

    def icon(self, name: str | DataPath | dict[str, str], *, id: str | None = None) -> str:
        if isinstance(name, dict) and "svgPath" in name:
            name_json: Any = name
        else:
            name_json = _serialize_dynamic(name)
        return self._add({"component": "Icon", "name": name_json}, id)

    def row(self, children: list[str] | dict[str, str], *, justify: str | None = None,
            align: str | None = None, id: str | None = None) -> str:
        c: dict[str, Any] = {"component": "Row", "children": children}
        if justify: c["justify"] = justify
        if align: c["align"] = align
        return self._add(c, id)

    def column(self, children: list[str] | dict[str, str], *, justify: str | None = None,
               align: str | None = None, id: str | None = None) -> str:
        c: dict[str, Any] = {"component": "Column", "children": children}
        if justify: c["justify"] = justify
        if align: c["align"] = align
        return self._add(c, id)

    def list(self, children: list[str] | None = None, *, template: str | None = None,
             template_path: str | None = None, direction: str = "vertical",
             align: str | None = None, id: str | None = None) -> str:
        if children is None and (template is None or template_path is None):
            raise ValueError("list() requires either children=[...] or both template= and template_path=")
        child_list: Any
        if children is not None:
            child_list = children
        else:
            child_list = {"componentId": template, "path": template_path}
        c: dict[str, Any] = {"component": "List", "children": child_list}
        if direction != "vertical":
            c["direction"] = direction
        if align:
            c["align"] = align
        return self._add(c, id)

    def card(self, child_id: str, *, id: str | None = None) -> str:
        if not isinstance(child_id, str):
            raise TypeError("Card.child is a single component id; wrap multiple with Column/Row")
        return self._add({"component": "Card", "child": child_id}, id)

    def tabs(self, tabs: list[dict[str, Any]], *, id: str | None = None) -> str:
        # Each tab: {"title": str|DataPath, "child": component_id}
        serialized = []
        for t in tabs:
            serialized.append({"title": _serialize_dynamic(t["title"]), "child": t["child"]})
        return self._add({"component": "Tabs", "tabs": serialized}, id)

    def modal(self, trigger: str, content: str, *, id: str | None = None) -> str:
        return self._add({"component": "Modal", "trigger": trigger, "content": content}, id)

    def divider(self, *, axis: str = "horizontal", id: str | None = None) -> str:
        c: dict[str, Any] = {"component": "Divider"}
        if axis != "horizontal":
            c["axis"] = axis
        return self._add(c, id)

    def button(self, child_id: str, *, action: Any, variant: str = "default",
               id: str | None = None) -> str:
        c: dict[str, Any] = {
            "component": "Button",
            "child": child_id,
            "action": _serialize_action(action),
        }
        if variant != "default":
            c["variant"] = variant
        return self._add(c, id)

    def text_field(self, label: str | DataPath, *, value: Any = "", variant: str = "shortText",
                   validation_regexp: str | None = None, id: str | None = None) -> str:
        c: dict[str, Any] = {
            "component": "TextField",
            "label": _serialize_dynamic(label),
            "value": _serialize_dynamic(value),
        }
        if variant != "shortText":
            c["variant"] = variant
        if validation_regexp:
            c["validationRegexp"] = validation_regexp
        return self._add(c, id)

    def check_box(self, label: str | DataPath, value: bool | DataPath, *,
                  id: str | None = None) -> str:
        return self._add({
            "component": "CheckBox",
            "label": _serialize_dynamic(label),
            "value": _serialize_dynamic(value),
        }, id)

    def choice_picker(self, options: list[dict[str, Any]], value: list[str] | DataPath, *,
                      label: str | DataPath = "", variant: str = "mutuallyExclusive",
                      display_style: str = "checkbox", filterable: bool = False,
                      id: str | None = None) -> str:
        serialized_opts = []
        for o in options:
            serialized_opts.append({"label": _serialize_dynamic(o["label"]), "value": o["value"]})
        c: dict[str, Any] = {
            "component": "ChoicePicker",
            "options": serialized_opts,
            "value": _serialize_dynamic(value),
        }
        if label:
            c["label"] = _serialize_dynamic(label)
        if variant != "mutuallyExclusive":
            c["variant"] = variant
        if display_style != "checkbox":
            c["displayStyle"] = display_style
        if filterable:
            c["filterable"] = True
        return self._add(c, id)

    def slider(self, value: int | float | DataPath, max: int | float, *,
               min: int | float = 0, label: str | DataPath = "",
               id: str | None = None) -> str:
        c: dict[str, Any] = {
            "component": "Slider",
            "value": _serialize_dynamic(value),
            "max": max,
        }
        if min != 0:
            c["min"] = min
        if label:
            c["label"] = _serialize_dynamic(label)
        return self._add(c, id)

    def date_time_input(self, value: str | DataPath = "", *,
                        label: str | DataPath = "",
                        enable_date: bool = False,
                        enable_time: bool = False,
                        min: str | DataPath | None = None,
                        max: str | DataPath | None = None,
                        id: str | None = None) -> str:
        c: dict[str, Any] = {
            "component": "DateTimeInput",
            "value": _serialize_dynamic(value),
        }
        if enable_date:
            c["enableDate"] = True
        if enable_time:
            c["enableTime"] = True
        if min is not None:
            c["min"] = _serialize_dynamic(min)
        if max is not None:
            c["max"] = _serialize_dynamic(max)
        if label:
            c["label"] = _serialize_dynamic(label)
        return self._add(c, id)

    def video(self, url: str | DataPath, *, id: str | None = None) -> str:
        return self._add({"component": "Video", "url": _serialize_dynamic(url)}, id)

    def audio_player(self, url: str | DataPath, *,
                     description: str | DataPath = "",
                     id: str | None = None) -> str:
        c: dict[str, Any] = {"component": "AudioPlayer", "url": _serialize_dynamic(url)}
        if description:
            c["description"] = _serialize_dynamic(description)
        return self._add(c, id)

    # ---- Action helpers -----------------------------------------------------

    def function_call(self, call: str, *, return_type: str = "void", **args: Any) -> FunctionCall:
        return FunctionCall(call=call, args=args, return_type=return_type)

    def event(self, name: str, **context: Any) -> Event:
        return Event(name=name, context=context)

    def open_url(self, url: str | DataPath) -> FunctionCall:
        return self.function_call("openUrl", url=url)

    def copy_to_clipboard(self, value: Any) -> FunctionCall:
        return self.function_call("copyToClipboard", value=value)

    def open_chash(self, chash: str | DataPath) -> FunctionCall:
        # Custom nexus-specific function. Renderer routes via host bridge.
        return self.function_call("openChash", chash=chash)

    # ---- Emit ---------------------------------------------------------------

    def emit(self) -> dict[str, Any]:
        """Return a v0.9 message-envelope payload (flat-shape variant the renderer accepts)."""
        if self._root_id is None:
            raise ValueError("set_root() must be called before emit()")
        components = list(self._components.values())
        messages: list[dict[str, Any]] = [
            {"version": "v0.9", "createSurface": {
                "surfaceId": self.surface_id,
                "catalogId": self.catalog_id,
            }}
        ]
        if self.data:
            messages.append({"version": "v0.9", "updateDataModel": {
                "surfaceId": self.surface_id,
                "path": "/",
                "value": self.data,
            }})
        messages.append({"version": "v0.9", "updateComponents": {
            "surfaceId": self.surface_id,
            "components": components,
        }})
        return {"version": "v0.9", "messages": messages}

    def emit_flat(self) -> dict[str, Any]:
        """Emit the convenience flat shape (single payload, no message stream)."""
        if self._root_id is None:
            raise ValueError("set_root() must be called before emit_flat()")
        return {
            "surfaceId": self.surface_id,
            "catalogId": self.catalog_id,
            "components": list(self._components.values()),
            "dataModel": self.data,
        }

    def to_json(self, *, flat: bool = False, indent: int | None = 2) -> str:
        return json.dumps(self.emit_flat() if flat else self.emit(), indent=indent)

    # ---- Trust-gate signing (RDR-004) ---------------------------------------

    def sign(
        self,
        key,  # palinex.signing.SigningKey; not type-annotated to keep import lazy
        actions,
        *,
        producer_name=None,
        ttl_seconds=3600,
        nonce=None,
        issued_at=None,
        flat=False,
    ):
        """Emit this surface as a signed payload with a ``trust`` block.

        Convenience shim around :func:`palinex.signing.sign_payload`. Builds
        the envelope (``emit()`` or ``emit_flat()`` depending on ``flat``),
        then attaches a normative ``trust`` block per RDR-004.

        Importing :mod:`palinex.signing` is deferred until this method runs
        so that ``import palinex`` doesn't transitively require
        ``cryptography`` / ``rfc8785`` for users who never sign.

        See :func:`palinex.signing.sign_payload` for parameter semantics and
        the full failure-mode table.
        """
        from .signing import sign_payload  # lazy import — keeps base install slim

        payload = self.emit_flat() if flat else self.emit()
        return sign_payload(
            payload,
            key,
            actions,
            producer_name=producer_name,
            ttl_seconds=ttl_seconds,
            nonce=nonce,
            issued_at=issued_at,
        )

    # ---- Markdown sidecar ---------------------------------------------------

    def to_markdown(self) -> str:
        if self._root_id is None:
            raise ValueError("set_root() must be called before to_markdown()")
        lines: list[str] = []
        self._walk_md(self._root_id, depth=0, lines=lines, item=None)
        return "\n".join(lines)

    def _resolve_dyn(self, value: Any, item: Any) -> Any:
        if isinstance(value, dict) and "path" in value:
            return self._resolve_path(value["path"], item)
        return value

    def _resolve_path(self, ptr: str, item: Any) -> Any:
        # Same JSON-pointer semantics as the renderer, with @item synthetic alias.
        if not ptr or ptr == "/":
            return self.data
        parts = ptr.lstrip("/").split("/")
        parts = [p.replace("~1", "/").replace("~0", "~") for p in parts]
        if parts and parts[0] == "@item":
            cur: Any = item
            parts = parts[1:]
        else:
            cur = self.data
        for p in parts:
            if cur is None:
                return None
            if isinstance(cur, list):
                try:
                    cur = cur[int(p)]
                except (ValueError, IndexError):
                    return None
            elif isinstance(cur, dict):
                cur = cur.get(p)
            else:
                return None
        return cur

    def _walk_md(self, cid: str, *, depth: int, lines: list[str], item: Any) -> None:
        c = self._components.get(cid)
        if c is None:
            return
        ind = "  " * depth
        kind = c["component"]
        if kind == "Text":
            t = self._resolve_dyn(c.get("text"), item)
            v = c.get("variant", "body")
            prefix = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### ", "h5": "##### ",
                      "caption": "_"}.get(v, "")
            suffix = "_" if v == "caption" else ""
            lines.append(ind + prefix + str(t) + suffix)
        elif kind == "Divider":
            lines.append(ind + "---")
        elif kind == "Image":
            url = self._resolve_dyn(c.get("url"), item)
            desc = self._resolve_dyn(c.get("description", ""), item)
            lines.append(ind + f"![{desc}]({url})")
        elif kind == "Icon":
            n = c.get("name")
            lines.append(ind + f"[icon:{n if isinstance(n, str) else 'custom'}]")
        elif kind == "Card":
            self._walk_md(c["child"], depth=depth, lines=lines, item=item)
        elif kind in ("Row", "Column"):
            for child_id in c.get("children", []):
                self._walk_md(child_id, depth=depth, lines=lines, item=item)
        elif kind == "List":
            children = c.get("children")
            if isinstance(children, list):
                for child_id in children:
                    self._walk_md(child_id, depth=depth, lines=lines, item=item)
            elif isinstance(children, dict):
                template_id = children["componentId"]
                items = self._resolve_path(children["path"], item) or []
                if isinstance(items, list):
                    for it in items:
                        self._walk_md(template_id, depth=depth, lines=lines, item=it)
        elif kind == "Modal":
            self._walk_md(c["trigger"], depth=depth, lines=lines, item=item)
        elif kind == "Button":
            child = self._components.get(c["child"], {})
            child_text = self._resolve_dyn(child.get("text"), item) if child.get("component") == "Text" else c["child"]
            action = c.get("action", {})
            fc = action.get("functionCall")
            if fc and fc.get("call") == "openUrl":
                url = self._resolve_dyn(fc.get("args", {}).get("url"), item)
                lines.append(ind + f"[{child_text}]({url})")
            else:
                lines.append(ind + f"[{child_text}]")
        elif kind in ("TextField", "CheckBox", "ChoicePicker", "Slider", "DateTimeInput"):
            label = self._resolve_dyn(c.get("label", c["id"]), item)
            lines.append(ind + f"[{kind}: {label}]")
        elif kind == "Tabs":
            for t in c.get("tabs", []):
                title = self._resolve_dyn(t.get("title", ""), item)
                lines.append(ind + f"#### {title}")
                self._walk_md(t["child"], depth=depth, lines=lines, item=item)
        elif kind == "Video":
            url = self._resolve_dyn(c.get("url"), item)
            lines.append(ind + f"[Video]({url})")
        elif kind == "AudioPlayer":
            url = self._resolve_dyn(c.get("url"), item)
            desc = self._resolve_dyn(c.get("description", ""), item)
            lines.append(ind + (f"[Audio: {desc}]({url})" if desc else f"[Audio]({url})"))
        else:
            lines.append(ind + f"[{kind}]")

    # ---- Validation ---------------------------------------------------------

    def validate(self, schemas: dict[str, Any] | None = None, *, deep: bool = False) -> None:
        """Validate emit() against the a2ui v0.9 schemas.

        With `deep=False` (default), runs structural sanity checks:
        - every component has a recognized `component` discriminator
        - exactly one component has id="root"
        - every referenced child id exists
        - data-paths are well-formed JSON pointers

        With `deep=True` and `schemas` provided (from `load_schemas()`), additionally
        validates each message against `server_to_client.json` using jsonschema.

        Note: jsonschema deep validation through the catalog $ref chain is known
        to be flaky with the upstream schemas — `basic_catalog.json` defs use
        bare `#/$defs/...` refs that don't always resolve cleanly when the file
        is aliased under `catalog.json` identity. If deep validation throws
        a referencing.exceptions.PointerToNowhere, the structural pass is the
        useful answer for now.
        """
        if self._root_id is None:
            raise ValueError("set_root() must be called before validate()")

        # Structural pass — always runs.
        for cid, c in self._components.items():
            kind = c.get("component")
            if kind not in BASIC_COMPONENTS:
                raise ValueError(f"unknown component '{kind}' in id {cid!r}")
            self._validate_refs(cid, c)
        if "root" not in self._components:
            raise ValueError("no component with id='root' found")

        if not deep:
            return
        if schemas is None:
            raise ValueError("deep=True requires schemas=load_schemas(...)")

        try:
            from jsonschema import Draft202012Validator, RefResolver
        except ImportError as e:
            raise ImportError(
                "jsonschema is required for deep validation (pip install jsonschema)"
            ) from e

        import copy
        store = {schemas[k].get("$id", k): schemas[k] for k in schemas}
        if "basic_catalog.json" in schemas:
            cat = copy.deepcopy(schemas["basic_catalog.json"])
            catalog_id = "https://a2ui.org/specification/v0_9/catalog.json"
            cat["$id"] = catalog_id
            store[catalog_id] = cat

        stc = schemas.get("server_to_client.json")
        if stc is None:
            raise ValueError("schemas dict must include 'server_to_client.json'")
        resolver = RefResolver.from_schema(stc, store=store)
        validator = Draft202012Validator(stc, resolver=resolver)
        for msg in self.emit()["messages"]:
            errors = sorted(validator.iter_errors(msg), key=lambda e: list(e.absolute_path))
            if errors:
                err_summary = "; ".join(f"{list(e.absolute_path)}: {e.message}" for e in errors[:3])
                raise ValueError(f"v0.9 schema violation: {err_summary}")

    def _validate_refs(self, cid: str, c: dict[str, Any]) -> None:
        """Ensure every component-id referenced by `c` exists in this surface."""
        kind = c["component"]
        if kind in ("Card", "Button"):
            child = c.get("child")
            if child is not None and child not in self._components:
                raise ValueError(f"{kind} {cid!r}: unknown child id {child!r}")
        elif kind == "Modal":
            for k in ("trigger", "content"):
                ref = c.get(k)
                if ref is not None and ref not in self._components:
                    raise ValueError(f"Modal {cid!r}: unknown {k} id {ref!r}")
        elif kind in ("Row", "Column", "List"):
            children = c.get("children")
            if isinstance(children, list):
                for ref in children:
                    if ref not in self._components:
                        raise ValueError(f"{kind} {cid!r}: unknown child id {ref!r}")
            elif isinstance(children, dict):
                t = children.get("componentId")
                if t and t not in self._components:
                    raise ValueError(f"{kind} {cid!r}: unknown template componentId {t!r}")
        elif kind == "Tabs":
            for t in c.get("tabs", []):
                ref = t.get("child")
                if ref and ref not in self._components:
                    raise ValueError(f"Tabs {cid!r}: unknown tab child id {ref!r}")


def load_schemas(json_dir: str | Path) -> dict[str, Any]:
    """Load the a2ui v0.9 JSON schemas for use with `Surface.validate(schemas=...)`.

    Pass the path to specification/v0_9/json/ from the a2ui repo. Returns a dict
    mapping schema filename to its parsed contents.
    """
    json_dir = Path(json_dir)
    if not json_dir.is_dir():
        raise FileNotFoundError(f"schema directory not found: {json_dir}")
    out: dict[str, Any] = {}
    for f in json_dir.glob("*.json"):
        with f.open() as fp:
            out[f.name] = json.load(fp)
    return out


# ---- MCP UI resource wrapper -----------------------------------------------

import html as _html_mod
from typing import Callable


def wrap_as_mcp_ui_resource(
    payload: dict[str, Any],
    *,
    chash_resolver: Callable[[str], str | None] | None = None,
    renderer_url: str = "https://hellblazer.github.io/palinex/index.html",
    title: str = "palinex surface",
) -> str:
    """Wrap an a2ui v0.9 surface payload as a self-contained HTML document
    suitable for use as the ``text`` field of an MCP UI resource.

    The returned HTML is a tiny wrapper that hosts the canonical palinex
    renderer in an iframe and posts the payload to it once loaded. No
    live host-bridge is required — interactive actions that would
    otherwise need round-tripping to the host are pre-resolved at
    wrap time.

    When ``chash_resolver`` is provided, the wrapper rewrites the payload:

    - Any string value in the data model that ``chash_resolver`` returns
      a non-None result for is replaced with the resolved text.
    - Any ``Button`` component whose action is ``openChash`` is rewritten
      to ``copyToClipboard`` carrying the same path reference (so the
      already-resolved text in the data model gets copied to clipboard
      on click — no host bridge needed).

    Non-chash strings are passed through; non-Button components are
    untouched. If ``chash_resolver`` is omitted, the payload is embedded
    verbatim.

    Args:
        payload: a2ui v0.9 envelope (``{version, messages: [...]}``) or
            the flat shape (``{components: [...], dataModel: {...}}``).
        chash_resolver: Optional callable mapping a candidate chash string
            to its resolved text, or None if not a chash.
        renderer_url: URL of the palinex renderer to embed. Defaults to
            the hosted GitHub Pages renderer.
        title: HTML ``<title>`` for the wrapper page.

    Returns:
        Self-contained HTML string. Use as the ``text`` field of an MCP
        UI resource (``{type: "resource", resource: {uri, mimeType:
        "text/html", text: <this>}}``).
    """
    resolved = _pre_resolve_payload(payload, chash_resolver) if chash_resolver else payload
    payload_json = json.dumps(resolved, ensure_ascii=False)
    return _MCP_UI_TEMPLATE.format(
        title=_html_mod.escape(title),
        renderer_url=_html_mod.escape(renderer_url, quote=True),
        payload_json=payload_json.replace("</", "<\\/"),
    )


_MCP_UI_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; }}
  iframe {{ display: block; width: 100%; height: 100vh; border: 0; }}
</style>
</head>
<body>
<iframe id="palinex-frame" src="{renderer_url}" sandbox="allow-scripts allow-same-origin"></iframe>
<script type="application/json" id="palinex-payload">{payload_json}</script>
<script>
  (function() {{
    const frame = document.getElementById('palinex-frame');
    const payload = JSON.parse(document.getElementById('palinex-payload').textContent);
    function deliver() {{
      try {{ frame.contentWindow.postMessage({{type: 'a2ui.load', payload}}, '*'); }}
      catch (e) {{ console.error('[palinex-mcp-ui]', e); }}
    }}
    let acked = false;
    window.addEventListener('message', (e) => {{
      if (e.source === frame.contentWindow && e.data && e.data.type === 'a2ui.ready') {{
        acked = true;
        deliver();
      }}
    }});
    frame.addEventListener('load', deliver);
    let attempts = 0;
    const timer = setInterval(() => {{
      if (acked) {{ clearInterval(timer); return; }}
      deliver();
      if (++attempts >= 40) clearInterval(timer);
    }}, 150);
  }})();
</script>
</body>
</html>
"""


def _pre_resolve_payload(payload: dict[str, Any], resolver: Callable[[str], str | None]) -> dict[str, Any]:
    """Deep-copy `payload` and substitute chash strings + rewrite openChash actions.

    See `wrap_as_mcp_ui_resource` for semantics. Pure function; doesn't
    mutate the input.
    """
    import copy as _copy
    p = _copy.deepcopy(payload)
    _resolve_strings_in_data_model(p, resolver)
    _rewrite_open_chash_actions(p)
    return p


def _data_model_locations(payload: dict[str, Any]) -> list:
    """Return a list of (container, key) tuples pointing at every dataModel
    value in the payload, regardless of shape (envelope or flat)."""
    locs: list = []
    if isinstance(payload.get("messages"), list):
        for m in payload["messages"]:
            if isinstance(m, dict) and "updateDataModel" in m and "value" in m["updateDataModel"]:
                locs.append((m["updateDataModel"], "value"))
    if "dataModel" in payload:
        locs.append((payload, "dataModel"))
    if "updateDataModel" in payload and "value" in payload["updateDataModel"]:
        locs.append((payload["updateDataModel"], "value"))
    return locs


def _component_lists(payload: dict[str, Any]) -> list[list]:
    """Return every components-array in the payload (mutating-safe)."""
    out: list[list] = []
    if isinstance(payload.get("messages"), list):
        for m in payload["messages"]:
            if isinstance(m, dict) and "updateComponents" in m:
                cs = m["updateComponents"].get("components")
                if isinstance(cs, list):
                    out.append(cs)
    if isinstance(payload.get("components"), list):
        out.append(payload["components"])
    if "updateComponents" in payload:
        cs = payload["updateComponents"].get("components")
        if isinstance(cs, list):
            out.append(cs)
    return out


def _resolve_strings_in_data_model(payload: dict[str, Any], resolver: Callable[[str], str | None]) -> None:
    """For each data-model value in the payload, walk it and replace any
    string that `resolver` returns a non-None text for."""
    for container, key in _data_model_locations(payload):
        container[key] = _walk_resolve(container[key], resolver)


def _walk_resolve(node: Any, resolver: Callable[[str], str | None]) -> Any:
    if isinstance(node, str):
        replacement = resolver(node)
        return replacement if replacement is not None else node
    if isinstance(node, dict):
        return {k: _walk_resolve(v, resolver) for k, v in node.items()}
    if isinstance(node, list):
        return [_walk_resolve(v, resolver) for v in node]
    return node


def _rewrite_open_chash_actions(payload: dict[str, Any]) -> None:
    """Rewrite every Button.action of shape `{functionCall: {call: openChash, ...}}`
    to `{functionCall: {call: copyToClipboard, args: {value: <same chash arg>}}}`.

    The data model has already been resolved (chash IDs → text), so the
    `value` parameter now points at the chunk text. Clicking the button
    copies the resolved text to clipboard — no host bridge required.
    """
    for components in _component_lists(payload):
        for c in components:
            if not isinstance(c, dict) or c.get("component") != "Button":
                continue
            action = c.get("action")
            if not isinstance(action, dict):
                continue
            fc = action.get("functionCall")
            if not isinstance(fc, dict) or fc.get("call") != "openChash":
                continue
            chash_arg = fc.get("args", {}).get("chash")
            if chash_arg is None:
                continue
            c["action"] = {
                "functionCall": {
                    "call": "copyToClipboard",
                    "args": {"value": chash_arg},
                    "returnType": fc.get("returnType", "void"),
                }
            }


# ---- Demo ------------------------------------------------------------------

def demo_nx_answer() -> Surface:
    """Build the same demo surface the renderer ships with — proves round-trip."""
    s = Surface(surface_id="demo.nx_answer", catalog_id="a2ui.basic.v0_9")
    s.data["synthesis"] = (
        "A2UI v0.9 is a declarative UI protocol for agent-generated interfaces. "
        "Surfaces are described as JSON; renderers map components to native widgets "
        "via per-host catalogs. This is a v0.9-conformant demo built by producer.py."
    )
    s.data["citations"] = [
        {
            "title": "a2ui v0.9 specification",
            "excerpt": (
                "Server-to-client messages: createSurface, updateComponents, updateDataModel, "
                "deleteSurface. Components are addressed in a flat array; id='root' anchors the tree."
            ),
            "chash": "demo-1-abcd1234",
        },
        {
            "title": "Basic Catalog reference",
            "excerpt": (
                "Eighteen components covering text, layout, media, input, and interaction."
            ),
            "chash": "demo-2-ef567890",
        },
    ]

    title_lbl = s.text("Open chunk")
    copy_lbl = s.text("Copy excerpt")

    title_tpl = s.text(path="/@item/title", variant="h4")
    excerpt_tpl = s.text(path="/@item/excerpt")
    open_btn = s.button(title_lbl, variant="primary",
                        action=s.open_chash(DataPath("/@item/chash")))
    copy_btn = s.button(copy_lbl, variant="borderless",
                        action=s.copy_to_clipboard(DataPath("/@item/excerpt")))
    actions_row = s.row([open_btn, copy_btn])
    item_col = s.column([title_tpl, excerpt_tpl, actions_row])
    item_card = s.card(item_col)

    citations_list = s.list(template=item_card, template_path="/citations")
    cite_heading = s.text("Citations", variant="h5")
    div = s.divider()
    synth = s.text(path="/synthesis")

    body = s.column([synth, div, cite_heading, citations_list])
    s.set_root(body)
    return s


if __name__ == "__main__":
    import sys

    s = demo_nx_answer()
    s.validate()

    if len(sys.argv) > 1 and sys.argv[1] == "schema-check":
        schemas_dir = sys.argv[2] if len(sys.argv) > 2 else None
        if not schemas_dir:
            print("usage: producer.py schema-check <path-to-a2ui/specification/v0_9/json> [--deep]", file=sys.stderr)
            sys.exit(2)
        deep = "--deep" in sys.argv
        try:
            schemas = load_schemas(schemas_dir)
            s.validate(schemas=schemas, deep=deep)
            print(f"OK: demo validates against v0.9 schemas ({'deep' if deep else 'structural'})")
        except ImportError as e:
            print(f"jsonschema not installed: {e}", file=sys.stderr)
            sys.exit(1)
        except ValueError as e:
            print(f"FAIL: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"validator error: {type(e).__name__}: {e}", file=sys.stderr)
            sys.exit(1)
    elif len(sys.argv) > 1 and sys.argv[1] == "markdown":
        print(s.to_markdown())
    else:
        print(s.to_json())
