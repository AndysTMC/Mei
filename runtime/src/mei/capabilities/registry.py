"""The capabilities a task may use, and how they look to the model (§9.1).

Tool names on the wire use `_` for `.` (OpenAI and Anthropic allow only letters, digits, `_`, `-`).
Parameter schemas are exported in the subset every provider accepts: no `$ref`, no `title`, no
`additionalProperties`, optional fields as plain types without a null default, and enums with their
type (Gemini also rejects an empty string as an enum value).
"""

import hashlib
from collections.abc import Iterable

import msgspec

from mei.providers.base import ToolSpec

from .base import Capability, Env

_DROP = frozenset({"title", "additionalProperties", "$schema"})


class InvalidArguments(ValueError):
    pass


def wire_name(name: str) -> str:
    return name.replace(".", "_")


class Registry:
    def __init__(self, capabilities: Iterable[Capability]) -> None:
        self._by_name: dict[str, Capability] = {}
        self._by_wire: dict[str, Capability] = {}
        for cap in capabilities:
            if cap.name in self._by_name or wire_name(cap.name) in self._by_wire:
                raise ValueError(f"capability {cap.name} is registered twice")
            self._by_name[cap.name] = cap
            self._by_wire[wire_name(cap.name)] = cap
        self._schemas = {name: portable_schema(cap.Params) for name, cap in self._by_name.items()}

    def get(self, name: str) -> Capability | None:
        return self._by_name.get(name)

    def by_wire(self, wire: str) -> Capability | None:
        return self._by_wire.get(wire)

    def names(self) -> list[str]:
        return list(self._by_name)

    def specs(self, env: Env) -> tuple[ToolSpec, ...]:
        """Tools for the model: every capability that is available in this environment."""
        return tuple(ToolSpec(wire_name(cap.name), cap.summary, self._schemas[cap.name])
                     for cap in self._by_name.values() if cap.available(env).ok)

    @staticmethod
    def decode(cap: Capability, arguments: str):
        try:
            return msgspec.json.decode((arguments or "{}").encode(), type=cap.Params, strict=False)
        except (msgspec.ValidationError, msgspec.DecodeError) as e:
            raise InvalidArguments(f"invalid arguments for {wire_name(cap.name)}: {e}") from None

    @staticmethod
    def canonical(cap: Capability, params) -> tuple[str, str]:
        """The params as canonical JSON and their hash; an approval is bound to the hash (§13.3)."""
        text = msgspec.json.encode(params).decode()
        digest = hashlib.sha256(f"{cap.name}@{cap.version}:{text}".encode()).hexdigest()
        return text, digest


def portable_schema(kind: type) -> dict:
    schema = msgspec.json.schema(kind)
    defs = schema.get("$defs", {})
    root = _resolve(schema, defs)
    return _portable(root, defs)


def _resolve(node: dict, defs: dict) -> dict:
    ref = node.get("$ref")
    return defs[ref.rsplit("/", 1)[-1]] if isinstance(ref, str) else node


def _portable(node: dict, defs: dict) -> dict:
    node = _resolve(node, defs)
    if "anyOf" in node:
        options = [o for o in node["anyOf"] if o.get("type") != "null"]
        if len(options) == 1:  # Optional[X]: the field is simply not required (and has no null default)
            rest = {k: v for k, v in node.items() if k not in ("anyOf", *_DROP) and not (k == "default" and v is None)}
            return {**_portable(options[0], defs), **rest}
    out: dict = {}
    for key, value in node.items():
        if key in _DROP or key == "$defs":
            continue
        if key == "properties":
            out[key] = {name: _portable(prop, defs) for name, prop in value.items()}
        elif key == "items" and isinstance(value, dict):
            out[key] = _portable(value, defs)
        elif key == "anyOf":
            out[key] = [_portable(o, defs) for o in value]
        else:
            out[key] = value
    if "enum" in out and "type" not in out:
        kinds = {type(v) for v in out["enum"]}
        out["type"] = "string" if kinds == {str} else "integer" if kinds == {int} else "number"
    return out
