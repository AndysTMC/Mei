"""Live check of the runtime's adapters against real providers, using keys from the repo's .env.

Not collected by pytest. Run:  npm run smoke:providers  (or  uv run python tests/live_smoke.py)
Lists each provider's models (read-only); with MEI_LIVE_CHAT=1 also sends one short chat.
Providers without a key or model in .env are skipped. Keys are never printed.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import httpx

from mei.obs import redact
from mei.protocol import ProviderConfig
from mei.providers import factory, models
from mei.providers.base import ChatTurn, ModelRequest, ProviderError, TextDelta, ThinkingDelta

ENV = Path(__file__).resolve().parents[2] / ".env"
PROMPT = ModelRequest([ChatTurn("user", "Reply with exactly the word OK and nothing else.")])

# (label, provider id, key variable, model variable, extra config)
CASES = [
    ("OpenAI", "openai", "OPENAI_API_KEY", "OPENAI_MODEL", {}),
    ("Anthropic", "anthropic", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", {}),
    ("Gemini", "gemini", "GEMINI_API_KEY", "GEMINI_MODEL", {}),
    ("Groq", "groq", "GROQ_API_KEY", "GROQ_MODEL", {}),
    ("Mistral", "mistral", "MISTRAL_API_KEY", "MISTRAL_MODEL", {}),
    ("OpenRouter", "openrouter", "OPENROUTER_API_KEY", "OPENROUTER_MODEL", {}),
    ("DeepSeek", "deepseek", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", {"base": "DEEPSEEK_BASE_URL"}),
    ("Fireworks AI", "fireworks", "FIREWORKS_API_KEY", "FIREWORKS_MODEL", {"base": "FIREWORKS_BASE_URL"}),
    ("NVIDIA NIM", "nvidia", "NVIDIA_API_KEY", "NVIDIA_MODEL", {"base": "NVIDIA_BASE_URL"}),
    ("Ollama", "ollama", None, "OLLAMA_MODEL", {"needs": "OLLAMA_LIVE"}),
    ("llama.cpp", "llamacpp", None, "LLAMACPP_MODEL", {"base": "LLAMACPP_BASE_URL"}),
    ("LM Studio", "lmstudio", None, "LMSTUDIO_MODEL", {"base": "LMSTUDIO_BASE_URL"}),
    ("Custom", "custom", None, "CUSTOM_MODEL", {"base": "CUSTOM_BASE_URL", "needs": "CUSTOM_BASE_URL"}),
]


def load_env() -> dict[str, str]:
    env = dict(os.environ)
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


async def one(client, env, label, pid, key_var, model_var, extra) -> tuple[str, str]:
    model = env.get(model_var, "")
    key = env.get(key_var, "") if key_var else ""
    needs = env.get(extra["needs"], "") if extra.get("needs") else "1"
    if not model or (key_var and not key) or not needs or needs == "0":
        return "skip", "no key/model in .env"
    if pid == "custom":
        key = env.get("CUSTOM_API_KEY", "")
    base = env.get(extra.get("base", ""), "").rstrip("/")
    url = base if not base or base.endswith("/chat/completions") else base + "/chat/completions"

    async def key_for(_pid):
        return key

    def failure(e: Exception) -> tuple[str, str]:
        msg = redact(str(e) or type(e).__name__)
        if key:
            msg = msg.replace(key, "[redacted]")
        local = pid in ("ollama", "llamacpp", "lmstudio") and "connection failed" in msg
        return ("skip" if local else "FAIL"), msg[:160]

    t0 = time.monotonic()
    try:
        listed = await models.list_models(client, pid, url=url, api_key=key)
    except (ProviderError, httpx.HTTPError) as e:
        return failure(e)
    found = f"{len(listed.models)} models{' (fallback list)' if listed.from_fallback else ''}"
    if env.get("MEI_LIVE_CHAT") != "1":
        return "pass", f"{found} ({int((time.monotonic() - t0) * 1000)} ms)"

    cfg = ProviderConfig(id=pid, model=model, url=url, mode=extra.get("mode", ""))
    t0 = time.monotonic()
    try:
        provider = await factory.build(cfg, client, key_for)
        text, thinking = "", ""
        async with asyncio.timeout(60):
            async for event in provider.stream(PROMPT):
                if isinstance(event, TextDelta):
                    text += event.text
                elif isinstance(event, ThinkingDelta):
                    thinking += event.text
    except (ProviderError, TimeoutError, httpx.HTTPError) as e:
        return failure(e)
    ms = int((time.monotonic() - t0) * 1000)
    status = "pass" if text.strip() else "FAIL"
    return status, f"{found}; {model}: {text.strip()[:40]!r}{' +thinking' if thinking else ''} ({ms} ms)"

async def main() -> int:
    env = load_env()
    failed = 0
    from mei.app import USER_AGENT
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        for label, pid, key_var, model_var, extra in CASES:
            status, detail = await one(client, env, label, pid, key_var, model_var, extra)
            failed += status == "FAIL"
            print(f"{status:5} {label:13} {detail}")
    return 1 if failed else 0


sys.exit(asyncio.run(main()))
