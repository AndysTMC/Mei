"""Typed criterion checks the runtime runs itself at finish time (§8.5).

Each looks at the world as it is now; none trusts what an action reported. A check that can't run
(no Shell attached for windows, no GSettings) is `unverifiable`, never `passed`.
"""

import fnmatch
import os

from .base import CheckResult, Env
from .meta import CheckSpec
from .settings_values import same_value


async def run_check(spec: CheckSpec, env: Env) -> CheckResult:
    try:
        if spec.type in ("file_exists", "file_absent", "dir_contains"):
            return _path_check(spec, env)
        if spec.type == "setting_equals":
            return await _setting(spec, env)
        if spec.type == "window_present":
            return await _window(spec, env)
    except ValueError as e:
        return CheckResult(status="unverifiable", detail=str(e))
    return CheckResult(status="unverifiable", detail=f"unknown check {spec.type or '(none)'}")


def _path_check(spec: CheckSpec, env: Env) -> CheckResult:
    if not spec.path:
        raise ValueError(f"{spec.type} needs a path")
    path = env.path(spec.path)
    shown = env.show(path)
    if spec.type == "file_absent":
        gone = not path.exists() and not path.is_symlink()
        return CheckResult(status="passed" if gone else "failed", detail=f"{shown} {'is gone' if gone else 'still exists'}")
    if spec.type == "file_exists":
        if not path.exists():
            return CheckResult(status="failed", detail=f"{shown} doesn't exist")
        size = path.stat().st_size if path.is_file() else 0
        if spec.min_size and size < spec.min_size:
            return CheckResult(status="failed", detail=f"{shown} is {size} bytes, under {spec.min_size}")
        return CheckResult(status="passed", detail=f"{shown} exists")
    if not path.is_dir():
        return CheckResult(status="failed", detail=f"{shown} isn't a folder")
    pattern = (spec.glob or "*").lower()
    matches = sum(1 for name in os.listdir(path) if fnmatch.fnmatch(name.lower(), pattern))
    ok = matches >= 1 if spec.count < 0 else matches == spec.count
    want = "at least 1" if spec.count < 0 else str(spec.count)
    return CheckResult(status="passed" if ok else "failed",
                       detail=f"{shown} has {matches} matching {pattern} (wanted {want})")


async def _setting(spec: CheckSpec, env: Env) -> CheckResult:
    if env.gsettings is None:
        return CheckResult(status="unverifiable", detail="settings can't be read here")
    if not (spec.schema and spec.key and spec.value):
        raise ValueError("setting_equals needs schema, key, and value")
    current = await env.gsettings.get(spec.schema, spec.key)
    ok = same_value(current, spec.value)
    return CheckResult(status="passed" if ok else "failed", detail=f"{spec.schema} {spec.key} is {current}")


async def _window(spec: CheckSpec, env: Env) -> CheckResult:
    bridge = env.bridge()
    if bridge is None:
        return CheckResult(status="unverifiable", detail="the Shell isn't connected, so windows can't be seen")
    if not (spec.app_id or spec.title):
        raise ValueError("window_present needs app_id or title")
    windows = await bridge.list_windows()
    for w in windows:
        if spec.app_id and w.app_id.removesuffix(".desktop").lower() != spec.app_id.removesuffix(".desktop").lower():
            continue
        if spec.title and spec.title.lower() not in w.title.lower():
            continue
        return CheckResult(status="passed", detail=f"window “{w.title}” is open")
    return CheckResult(status="failed", detail="no such window is open")
