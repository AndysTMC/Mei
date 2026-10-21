"""Showing the person a desktop notification (§9.3)."""

from typing import Annotated

import msgspec

from .base import ActionContext, ActionResult, Availability, AVAILABLE, Capability, Env


class NotifyParams(msgspec.Struct, kw_only=True):
    title: Annotated[str, msgspec.Meta(min_length=1, max_length=120)]
    body: Annotated[str, msgspec.Meta(max_length=1000)] = ""


class NotifySend(Capability):
    """Read-only for policy: it shows text to the person already using Mei, and changes nothing."""

    name = "notify.send"
    summary = "Show the person a desktop notification, e.g. when something they asked for is ready."
    Params = NotifyParams

    def available(self, env: Env) -> Availability:
        return AVAILABLE if env.notifier is not None else Availability.unavailable("notifications aren't available")

    def describe(self, p: NotifyParams, env: Env) -> str:
        return f"Show a notification: {p.title}"

    async def run(self, p: NotifyParams, ctx: ActionContext) -> ActionResult:
        await ctx.env.notifier.notify(p.title, p.body)
        return ActionResult(ok=True, observation="Notification shown.", summary=f"Notified: {p.title}")
