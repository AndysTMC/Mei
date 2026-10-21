"""Desktop settings (§9.3): read and change an allow-listed set of GSettings keys.

Only these keys are reachable, so a tool can't change keyboard shortcuts, privacy switches, or
Mei's own settings. Every change records the old value (its undo) and is checked by reading back.
"""

from typing import Annotated

import msgspec

from mei.core.states import Disposition

from . import settings_values as values
from .base import (LOCAL_UNDOABLE, ActionContext, ActionResult, Availability, AVAILABLE, Capability, CapabilityError,
                   CheckResult, Effects, Env, Resource)

_DARK = ("dark mode", "light mode", "dark theme", "light theme", "dark style", "light style", "color scheme",
         "colour scheme", "appearance")
_WALLPAPER = ("wallpaper", "background", "desktop background")
_NIGHT = ("night light", "blue light")
# (schema, key) → the words that name it, so "switch to dark mode" names color-scheme.
ALLOWED: dict[tuple[str, str], tuple[str, ...]] = {
    ("org.gnome.desktop.interface", "color-scheme"): _DARK,
    ("org.gnome.desktop.interface", "accent-color"): ("accent color", "accent colour", "accent"),
    ("org.gnome.desktop.interface", "text-scaling-factor"): ("text size", "font size", "larger text", "bigger text",
                                                             "smaller text", "text scaling"),
    ("org.gnome.desktop.interface", "clock-format"): ("clock format", "24-hour", "12-hour", "24 hour", "12 hour"),
    ("org.gnome.desktop.interface", "show-battery-percentage"): ("battery percentage",),
    ("org.gnome.desktop.interface", "enable-animations"): ("animations",),
    ("org.gnome.desktop.background", "picture-uri"): _WALLPAPER,
    ("org.gnome.desktop.background", "picture-uri-dark"): _WALLPAPER,
    ("org.gnome.desktop.background", "picture-options"): _WALLPAPER,
    ("org.gnome.desktop.background", "primary-color"): ("background color", "background colour"),
    ("org.gnome.settings-daemon.plugins.color", "night-light-enabled"): _NIGHT,
    ("org.gnome.settings-daemon.plugins.color", "night-light-temperature"): (*_NIGHT, "color temperature", "warmer"),
    ("org.gnome.settings-daemon.plugins.color", "night-light-schedule-automatic"): (*_NIGHT, "sunset"),
}
KEYS_TEXT = "; ".join(f"{s} {k}" for s, k in ALLOWED)


def _allowed(schema: str, key: str) -> tuple[str, ...]:
    words = ALLOWED.get((schema.strip(), key.strip()))
    if words is None:
        raise CapabilityError("invalid", f"Mei can't change {schema} {key}. It can change: {KEYS_TEXT}")
    return words


def _resource(schema: str, key: str, access: str) -> list[Resource]:
    return [Resource(kind="setting", value=f"{schema} {key}", access=access, role="setting",
                     aliases=_allowed(schema, key))]


async def coerce(env: Env, schema: str, key: str, value: str) -> str:
    """The value as GVariant text for this key's type, or an error that says what would fit."""
    spec = (await env.gsettings.range(schema, key)).splitlines()
    kind = spec[0].split() if spec else []
    wanted = values.loose(value)
    if kind == ["enum"]:
        options = [values.parse(o) for o in spec[1:]]
        if wanted not in options:
            raise CapabilityError("invalid", f"{key} must be one of {', '.join(str(o) for o in options)}")
        return values.to_text(wanted)
    if kind[:1] == ["type"] and kind[1:] == ["b"]:
        if not isinstance(wanted, bool):
            raise CapabilityError("invalid", f"{key} is true or false")
        return values.to_text(wanted)
    if kind[:1] in (["type"], ["range"]) and kind[1:2] and kind[1] in ("i", "u", "d", "x", "t", "n", "q", "y"):
        if isinstance(wanted, bool) or not isinstance(wanted, (int, float)):
            raise CapabilityError("invalid", f"{key} is a number")
        if kind[0] == "range" and not float(kind[2]) <= wanted <= float(kind[3]):
            raise CapabilityError("invalid", f"{key} must be between {kind[2]} and {kind[3]}")
        return str(float(wanted)) if kind[1] == "d" else str(int(wanted))
    if kind == ["type", "s"]:
        return values.to_text(str(wanted))
    raise CapabilityError("invalid", f"Mei can't set {key} (its type is {' '.join(kind) or 'unknown'})")


def _needs_gsettings(env: Env) -> Availability:
    return AVAILABLE if env.gsettings is not None else Availability.unavailable("settings can't be reached here")


class GetParams(msgspec.Struct, kw_only=True):
    schema: Annotated[str, msgspec.Meta(description="e.g. org.gnome.desktop.interface")]
    key: Annotated[str, msgspec.Meta(description="e.g. color-scheme")]


class SettingsGet(Capability):
    name = "settings.get"
    summary = "Read a desktop setting; the same keys settings_set can change."
    Params = GetParams
    idempotent = True

    def available(self, env: Env) -> Availability:
        return _needs_gsettings(env)

    def resources(self, p: GetParams, env: Env) -> list[Resource]:
        return _resource(p.schema, p.key, "read")

    def describe(self, p: GetParams, env: Env) -> str:
        return f"Read the setting {p.key}"

    async def run(self, p: GetParams, ctx: ActionContext) -> ActionResult:
        _allowed(p.schema, p.key)
        current = await ctx.env.gsettings.get(p.schema, p.key)
        return ActionResult(ok=True, observation=f"{p.schema} {p.key} = {current}", summary=f"Read {p.key}",
                            data_class="settings")


class SetParams(msgspec.Struct, kw_only=True):
    schema: str
    key: str
    value: Annotated[str, msgspec.Meta(description="The new value, e.g. prefer-dark, true, 4000")]


class SettingsSet(Capability):
    name = "settings.set"
    summary = (f"Change a desktop setting (the old value is kept so it can be undone). Available: {KEYS_TEXT}. "
               "Dark mode is org.gnome.desktop.interface color-scheme prefer-dark (light: default).")
    Params = SetParams
    idempotent = True  # setting the same value twice changes nothing more

    def available(self, env: Env) -> Availability:
        return _needs_gsettings(env)

    def effects(self, p: SetParams, env: Env) -> Effects:
        return LOCAL_UNDOABLE

    def resources(self, p: SetParams, env: Env) -> list[Resource]:
        return _resource(p.schema, p.key, "write")

    def describe(self, p: SetParams, env: Env) -> str:
        return f"Set {p.key} to {p.value}"

    async def run(self, p: SetParams, ctx: ActionContext) -> ActionResult:
        _allowed(p.schema, p.key)
        gs = ctx.env.gsettings
        old = await gs.get(p.schema, p.key)
        new = await coerce(ctx.env, p.schema, p.key, p.value)
        await gs.set(p.schema, p.key, new)
        return ActionResult(ok=True, observation=f"Set {p.schema} {p.key} to {new} (it was {old})",
                            summary=f"Set {p.key} to {values.loose(new)}", data_class="settings",
                            undo={"kind": "setting", "schema": p.schema, "key": p.key, "old": old, "new": new})

    async def verify(self, p: SetParams, result: ActionResult, ctx: ActionContext) -> CheckResult:
        now = await ctx.env.gsettings.get(p.schema, p.key)
        ok = values.same_value(now, result.undo["new"])
        return CheckResult(status="passed" if ok else "failed", detail=f"{p.key} is {now}")

    async def probe(self, p: SetParams, ctx: ActionContext) -> Disposition:
        now = await ctx.env.gsettings.get(p.schema, p.key)
        return Disposition.CONFIRMED if values.same_value(now, p.value) else Disposition.NONE
