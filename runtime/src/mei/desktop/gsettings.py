"""GSettings through the system `gsettings` tool (§5.2: the core's Python has no GIO).

`env` overrides the backend for tests (GSETTINGS_BACKEND=keyfile with a private XDG_CONFIG_HOME).
"""

from .run import checked

GSETTINGS = "/usr/bin/gsettings"


class GSettingsCli:
    def __init__(self, env: dict[str, str] | None = None, tool: str = GSETTINGS) -> None:
        self._env = env
        self._tool = tool

    async def get(self, schema: str, key: str) -> str:
        return (await checked([self._tool, "get", schema, key], env=self._env)).strip()

    async def set(self, schema: str, key: str, value: str) -> None:
        await checked([self._tool, "set", schema, key, value], env=self._env)

    async def range(self, schema: str, key: str) -> str:
        return (await checked([self._tool, "range", schema, key], env=self._env)).strip()
