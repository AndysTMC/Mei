"""Build the right adapter for a user's provider settings (port of src/providers/runtime.ts)."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing

import httpx

from mei.obs import scrub
from mei.protocol import ProviderConfig

from .anthropic import AnthropicProvider
from .base import ModelEvent, ModelRequest, Provider, ProviderError
from .fake import FakeProvider
from .gemini import GeminiProvider
from .ollama import OllamaProvider
from .openai_chat import OpenAIChatProvider
from .profiles import PROFILES, credential_headers, resolve
from .responses import ResponsesProvider

log = logging.getLogger("mei.providers")

KeyLookup = Callable[[str], Awaitable[str]]


def label_of(cfg: ProviderConfig) -> str:
    if cfg.id == "fake":
        return "Fake"
    profile = PROFILES.get(cfg.id)
    return profile.label if profile else (cfg.id or "none")


def deepseek_body(model: str, thinking: str, effort: str) -> dict:
    """DeepSeek V4+ accept top-level `thinking` and `reasoning_effort` (port of openaiPayload.ts)."""
    m = model.strip().lower()
    if not m.startswith("deepseek-v") or m.startswith("deepseek-v3") or thinking not in ("enabled", "disabled"):
        return {}
    body: dict = {"thinking": {"type": thinking}}
    if thinking == "enabled":
        body["reasoning_effort"] = effort if effort in ("low", "max") else "high"
    return body


async def build(cfg: ProviderConfig, client: httpx.AsyncClient, key_for: KeyLookup) -> Provider:
    if cfg.id == "fake":
        return FakeProvider({**cfg.options, "model": cfg.model or "fake-1"})
    profile = PROFILES.get(cfg.id)
    if profile is None:
        raise ProviderError("No model provider is configured.")
    if not profile.selectable:
        raise ProviderError(profile.unavailable or f"{profile.label} is no longer available.")
    r = resolve(cfg.id, model=cfg.model, url=cfg.url, mode=cfg.mode)
    if r.api_mode == "bedrock_converse":
        raise ProviderError(f"{profile.label} needs AWS authentication, which Mei doesn't support.")
    key = await key_for(cfg.id)
    if profile.auth != "none" and not key:
        log.warning("no API key in the keyring for %s", cfg.id)
    label = profile.label
    headers = {**profile.headers, **credential_headers(profile, key)}
    if r.api_mode == "responses":
        adapter: Provider = ResponsesProvider(client, label=label, url=r.url, model=r.model, headers=headers)
    elif r.api_mode == "anthropic_messages":
        adapter = AnthropicProvider(client, label=label, url=r.url, model=r.model, headers=_without_version(headers))
    elif profile.transport == "gemini":
        adapter = GeminiProvider(client, label=label, base_url=r.url, model=r.model, headers=headers)
    elif profile.transport == "ollama":
        adapter = OllamaProvider(client, label=label, url=r.url, model=r.model, headers=headers)
    else:
        extra = deepseek_body(r.model, cfg.thinking, cfg.reasoning_effort) if cfg.id == "deepseek" else {}
        adapter = OpenAIChatProvider(client, label=label, url=r.url, model=r.model, headers=headers, extra_body=extra)
    return KeyScrubbing(adapter, key) if key else adapter


class KeyScrubbing:
    """Wraps an adapter so no error it raises can carry the key it was given.

    Some upstreams repeat the key back, in an HTTP error body or in an error frame inside a
    successful stream; either would otherwise become the task's error, stored and shown in the UI.
    """

    def __init__(self, inner: Provider, key: str) -> None:
        self.inner = inner
        self._key = key
        self.label = inner.label
        self.model = inner.model

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        try:
            async with aclosing(self.inner.stream(request)) as events:
                async for event in events:
                    yield event
        except ProviderError as e:
            e.message = scrub(e.message, [self._key])  # in place: keeps the error's type and retry flags
            raise


def _without_version(headers: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() != "anthropic-version"}  # the adapter sets it
