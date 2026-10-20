"""Build the right adapter for a user's provider settings (port of src/providers/runtime.ts)."""

import logging
from collections.abc import Awaitable, Callable

import httpx

from mei.protocol import ProviderConfig

from .anthropic import AnthropicProvider
from .base import Provider, ProviderError
from .fake import FakeProvider
from .gemini import GeminiProvider
from .ollama import OllamaProvider
from .openai_chat import OpenAIChatProvider
from .profiles import PROFILES, resolve
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
        raise ProviderError(f"{profile.label} is no longer available. Choose another provider in Mei's settings.")
    r = resolve(cfg.id, model=cfg.model, url=cfg.url, mode=cfg.mode)
    if r.api_mode == "bedrock_converse":
        raise ProviderError(f"{profile.label} needs AWS authentication, which Mei doesn't support.")
    key = await key_for(cfg.id)
    if profile.auth != "none" and not key:
        log.warning("no API key in the keyring for %s", cfg.id)
    label = profile.label
    if r.api_mode == "responses":
        return ResponsesProvider(client, label=label, url=r.url, model=r.model, api_key=key, headers=profile.headers)
    if r.api_mode == "anthropic_messages":
        return AnthropicProvider(client, label=label, url=r.url, model=r.model, api_key=key,
                                 bearer_auth=cfg.id != "anthropic", headers=_without_version(profile.headers))
    if profile.transport == "gemini":
        return GeminiProvider(client, label=label, base_url=r.url, model=r.model, api_key=key)
    if profile.transport == "ollama":
        return OllamaProvider(client, label=label, url=r.url, model=r.model, api_key=key)
    extra = deepseek_body(r.model, cfg.thinking, cfg.reasoning_effort) if cfg.id == "deepseek" else {}
    return OpenAIChatProvider(client, label=label, url=r.url, model=r.model, api_key=key,
                              headers=profile.headers, extra_body=extra)


def _without_version(headers: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() != "anthropic-version"}  # the adapter sets it
