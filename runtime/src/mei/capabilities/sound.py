"""The output volume (§9.3, "sound volume" in the Stage 3 settings allow-list).

Volume isn't a GSettings key on GNOME; it belongs to PipeWire, reached through `wpctl`.
"""

from typing import Annotated

import msgspec

from mei.core.states import Disposition

from .base import (LOCAL_UNDOABLE, ActionContext, ActionResult, Availability, AVAILABLE, Capability, CheckResult,
                   Effects, Env, Resource)

VOLUME = Resource(kind="setting", value="sound volume", access="write", role="setting",
                  aliases=("volume", "sound", "mute", "unmute", "louder", "quieter", "audio"))


def _needs_volume(env: Env) -> Availability:
    return AVAILABLE if env.volume is not None else Availability.unavailable("the volume can't be reached here")


def _text(percent: int, muted: bool) -> str:
    return f"{percent}%" + (" (muted)" if muted else "")


class GetVolumeParams(msgspec.Struct, kw_only=True):
    pass


class SoundGetVolume(Capability):
    name = "sound.get_volume"
    summary = "Read the output volume (0–100) and whether it's muted."
    Params = GetVolumeParams
    idempotent = True

    def available(self, env: Env) -> Availability:
        return _needs_volume(env)

    def resources(self, p: GetVolumeParams, env: Env) -> list[Resource]:
        return [Resource(kind="setting", value=VOLUME.value, access="read", role="setting", aliases=VOLUME.aliases)]

    def describe(self, p: GetVolumeParams, env: Env) -> str:
        return "Read the volume"

    async def run(self, p: GetVolumeParams, ctx: ActionContext) -> ActionResult:
        percent, muted = await ctx.env.volume.get()
        return ActionResult(ok=True, observation=f"Volume {_text(percent, muted)}", summary="Read the volume",
                            data_class="settings")


class SetVolumeParams(msgspec.Struct, kw_only=True):
    percent: Annotated[int, msgspec.Meta(ge=0, le=100)]
    muted: bool = False


class SoundSetVolume(Capability):
    name = "sound.set_volume"
    summary = "Set the output volume (0–100), and mute or unmute it."
    Params = SetVolumeParams
    idempotent = True

    def available(self, env: Env) -> Availability:
        return _needs_volume(env)

    def effects(self, p: SetVolumeParams, env: Env) -> Effects:
        return LOCAL_UNDOABLE

    def resources(self, p: SetVolumeParams, env: Env) -> list[Resource]:
        return [VOLUME]

    def describe(self, p: SetVolumeParams, env: Env) -> str:
        return f"Set the volume to {_text(p.percent, p.muted)}"

    async def run(self, p: SetVolumeParams, ctx: ActionContext) -> ActionResult:
        old = await ctx.env.volume.get()
        await ctx.env.volume.set(p.percent, p.muted)
        return ActionResult(ok=True, observation=f"Volume set to {_text(p.percent, p.muted)} (it was {_text(*old)})",
                            summary=f"Set the volume to {_text(p.percent, p.muted)}", data_class="settings",
                            undo={"kind": "volume", "old": list(old)})

    async def verify(self, p: SetVolumeParams, result: ActionResult, ctx: ActionContext) -> CheckResult:
        percent, muted = await ctx.env.volume.get()
        ok = abs(percent - p.percent) <= 1 and muted == p.muted
        return CheckResult(status="passed" if ok else "failed", detail=f"volume is {_text(percent, muted)}")

    async def probe(self, p: SetVolumeParams, ctx: ActionContext) -> Disposition:
        percent, muted = await ctx.env.volume.get()
        return Disposition.CONFIRMED if abs(percent - p.percent) <= 1 and muted == p.muted else Disposition.NONE
