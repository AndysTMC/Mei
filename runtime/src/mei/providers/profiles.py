"""Provider profiles: where each provider lives and how to talk to it.

Port of src/providers/profiles.ts. The runtime resolves a user's provider settings (id, model,
optional URL override) into a concrete endpoint, wire format, auth style and headers, so the
extension only ever sends non-secret preferences.
"""

from dataclasses import dataclass, field
from typing import Literal

Transport = Literal["openai", "anthropic", "gemini", "ollama", "llamacpp"]
ApiMode = Literal["chat_completions", "anthropic_messages"]
Auth = Literal["none", "bearer", "api_key"]

ATTRIBUTION = {"HTTP-Referer": "https://github.com/AndysTMC/Mei", "X-Title": "Mei"}


@dataclass(frozen=True)
class Profile:
    id: str
    label: str
    type: Literal["local", "cloud", "custom"]
    transport: Transport
    auth: Auth
    chat_url: str
    models_url: str = ""
    model_kind: Literal["openai", "gemini", "ollama", "github"] = "openai"
    headers: dict[str, str] = field(default_factory=dict)
    selectable: bool = True
    unavailable: str = ""  # why a retired provider can't be used, shown to the user
    aliases: tuple[str, ...] = ()
    fallback_models: tuple[str, ...] = ()

    @property
    def api_mode(self) -> ApiMode:
        return "anthropic_messages" if self.transport == "anthropic" else "chat_completions"


PROFILES: dict[str, Profile] = {p.id: p for p in [
    Profile("ollama", "Ollama", "local", "ollama", "none", "http://127.0.0.1:11434/api/chat",
            models_url="http://127.0.0.1:11434/api/tags", model_kind="ollama", aliases=("local",)),
    Profile("llamacpp", "llama.cpp", "local", "llamacpp", "none", "http://127.0.0.1:8080/v1/chat/completions",
            models_url="http://127.0.0.1:8080/v1/models", aliases=("llama.cpp", "llama-cpp")),
    Profile("lmstudio", "LM Studio", "local", "openai", "none", "http://127.0.0.1:1234/v1/chat/completions",
            models_url="http://127.0.0.1:1234/v1/models", aliases=("lm-studio",)),
    Profile("openai", "OpenAI", "cloud", "openai", "bearer", "https://api.openai.com/v1/chat/completions",
            models_url="https://api.openai.com/v1/models", fallback_models=("gpt-5.4", "gpt-5.4-mini")),
    Profile("anthropic", "Anthropic", "cloud", "anthropic", "api_key", "https://api.anthropic.com/v1/messages",
            models_url="https://api.anthropic.com/v1/models?limit=1000", headers={"anthropic-version": "2023-06-01"},
            fallback_models=("claude-sonnet-4-6", "claude-opus-4-6")),
    Profile("gemini", "Gemini", "cloud", "gemini", "api_key", "https://generativelanguage.googleapis.com/v1beta",
            models_url="https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000", model_kind="gemini",
            fallback_models=("gemini-3-flash", "gemini-3-pro")),
    Profile("groq", "Groq", "cloud", "openai", "bearer", "https://api.groq.com/openai/v1/chat/completions",
            models_url="https://api.groq.com/openai/v1/models"),
    Profile("mistral", "Mistral", "cloud", "openai", "bearer", "https://api.mistral.ai/v1/chat/completions",
            models_url="https://api.mistral.ai/v1/models"),
    Profile("openrouter", "OpenRouter", "cloud", "openai", "bearer", "https://openrouter.ai/api/v1/chat/completions",
            models_url="https://openrouter.ai/api/v1/models", headers=ATTRIBUTION, aliases=("or",),
            fallback_models=("anthropic/claude-sonnet-4.6", "openai/gpt-5.4", "deepseek/deepseek-chat")),
    Profile("deepseek", "DeepSeek", "cloud", "openai", "bearer", "https://api.deepseek.com/chat/completions",
            models_url="https://api.deepseek.com/models"),
    Profile("fireworks", "Fireworks AI", "cloud", "openai", "bearer", "https://api.fireworks.ai/inference/v1/chat/completions",
            models_url="https://api.fireworks.ai/inference/v1/models", headers=ATTRIBUTION),
    Profile("nvidia", "NVIDIA NIM", "cloud", "openai", "bearer", "https://integrate.api.nvidia.com/v1/chat/completions",
            models_url="https://integrate.api.nvidia.com/v1/models", headers={"X-BILLING-INVOKE-ORIGIN": "Mei"},
            aliases=("nim",)),
    Profile("opencode", "OpenCode (unavailable)", "cloud", "openai", "bearer",
            "https://opencode.ai/zen/go/v1/chat/completions", headers=ATTRIBUTION, selectable=False,
            unavailable="OpenCode no longer serves Mei: Zen's free tier only works inside OpenCode, and Go is "
                        "meant for coding agents. Choose another provider in Mei's settings.",
            aliases=("opencode-go", "opencode-zen", "go", "zen")),
    Profile("githubcopilot", "GitHub Models (retired)", "cloud", "openai", "bearer",
            "https://models.github.ai/inference/chat/completions", model_kind="github", selectable=False,
            unavailable="GitHub Models was retired. Choose another provider in Mei's settings.",
            aliases=("github", "github-models")),
    Profile("custom", "Custom", "custom", "openai", "none", "http://127.0.0.1:8080/v1/chat/completions",
            aliases=("vllm",)),
]}


def credential_headers(profile: Profile, key: str) -> dict[str, str]:
    """The header that carries `key` for this provider. Providers without auth still get a Bearer
    header if the user set a key (local servers and custom endpoints may want one)."""
    if not key:
        return {}
    if profile.auth == "api_key":
        return {"x-goog-api-key": key} if profile.transport == "gemini" else {"x-api-key": key}
    return {"Authorization": f"Bearer {key}"}


def resolve_id(value: str) -> str | None:
    v = value.strip().lower()
    for p in PROFILES.values():
        if v == p.id or v in p.aliases:
            return p.id
    return None


@dataclass(frozen=True)
class Resolved:
    profile: Profile
    api_mode: ApiMode
    url: str
    model: str


def resolve(provider_id: str, *, model: str, url: str = "") -> Resolved:
    profile = PROFILES[provider_id]
    return Resolved(profile, profile.api_mode, url.strip() or profile.chat_url, model.strip())
