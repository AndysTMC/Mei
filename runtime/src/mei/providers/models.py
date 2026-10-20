"""Model discovery (port of src/providers/modelList.ts).

Lists a provider's models with the user's key, follows pagination only on the same origin (a
catalog must not be able to send our key elsewhere), and falls back to the profile's suggested
models when a key is required but missing.
"""

import json
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from .base import ProviderError
from .http_stream import TIMEOUT, error_message
from .profiles import PROFILES

MAX_PAGES = 10
MAX_PAGE_BYTES = 4 * 1024 * 1024
_URL_RE = re.compile(r"^(https?://[^/?#]+)([^?#]*)", re.IGNORECASE)


@dataclass
class ModelList:
    models: list[str]
    requires_key: bool
    from_fallback: bool = False


@dataclass
class Endpoint:
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    requires_key: bool = False
    kind: str = "openai"


def model_list_url(chat_url: str, model_path: str) -> str:
    """Derive a catalog URL from a chat URL (e.g. …/v1/chat/completions → …/v1/models)."""
    m = _URL_RE.match(chat_url.strip())
    if not m:
        return chat_url
    origin, path = m.group(1), (m.group(2) or "").rstrip("/")
    chat_suffix = "/api/chat" if model_path == "/api/tags" else "/v1/chat/completions"
    if path.endswith(chat_suffix):
        return f"{origin}{path[: -len(chat_suffix)]}{model_path}"
    if not path:
        return f"{origin}{model_path}"
    base = path if path.endswith("/v1") else f"{path}/v1"
    return f"{origin}{base}{model_path.replace('/v1', '')}"


def endpoint(provider_id: str, *, url: str = "", api_key: str = "") -> Endpoint:
    profile = PROFILES[provider_id]
    headers = dict(profile.headers)
    if api_key:
        if profile.auth == "api_key":
            headers["x-goog-api-key" if provider_id == "gemini" else "x-api-key"] = api_key
        else:
            headers["Authorization"] = f"Bearer {api_key}"
    if provider_id == "custom" and not url.strip():
        raise ProviderError("Enter an endpoint URL to fetch models.")
    path = "/api/tags" if provider_id == "ollama" else "/v1/models"
    if provider_id == "gemini" and url.strip():
        target = f"{url.strip().rstrip('/')}/models?pageSize=1000"
    elif url.strip():
        target = model_list_url(url, path)
    else:
        target = profile.models_url or model_list_url(profile.chat_url, path)
    return Endpoint(target, headers, requires_key=profile.auth != "none" and provider_id != "openrouter",
                    kind=profile.model_kind)


def parse_models(text: str, kind: str) -> list[str]:
    data = json.loads(text)
    if isinstance(data, list) and kind != "github":
        return []
    root = data if isinstance(data, dict) else {}
    items = (data if isinstance(data, list) else root.get("models") or root.get("data")) if kind == "github" else \
        root.get("models") if kind in ("gemini", "ollama") else root.get("data")
    out: list[str] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        if kind == "gemini" and isinstance(item.get("supportedGenerationMethods"), list) \
                and "generateContent" not in item["supportedGenerationMethods"]:
            continue
        value = item.get("name") if kind == "gemini" else \
            (item.get("name") or item.get("model")) if kind == "ollama" else (item.get("id") or item.get("display_name"))
        if isinstance(value, str) and value:
            value = value.removeprefix("models/") if kind == "gemini" else value
            if value not in out:
                out.append(value)
    return out


def next_page_url(current: str, text: str, kind: str) -> str | None:
    try:
        root = json.loads(text)
    except ValueError:
        return None
    if not isinstance(root, dict):
        return None
    nxt = root.get("next")
    if isinstance(nxt, str) and _same_origin(current, nxt):
        return nxt
    token = root.get("nextPageToken") or root.get("next_page_token")
    if isinstance(token, str) and token:
        return _with_param(current, "pageToken" if kind == "gemini" else "page_token", token)
    if root.get("has_more") is True and isinstance(root.get("data"), list) and root["data"]:
        last = root["data"][-1]
        if isinstance(last, dict) and isinstance(last.get("id"), str) and last["id"]:
            return _with_param(current, "after_id", last["id"])
    return None


async def list_models(client: httpx.AsyncClient, provider_id: str, *, url: str = "", api_key: str = "") -> ModelList:
    profile = PROFILES[provider_id]
    ep = endpoint(provider_id, url=url, api_key=api_key)
    fallback = list(profile.fallback_models)
    if ep.requires_key and not api_key:
        return ModelList(fallback, requires_key=True, from_fallback=True)
    models: list[str] = []
    page: str | None = ep.url
    for _ in range(MAX_PAGES):
        if not page:
            break
        text = await _get(client, page, ep.headers, profile.label)
        models += [m for m in parse_models(text, ep.kind) if m not in models]
        page = next_page_url(page, text, ep.kind)
    if models:
        return ModelList(models, requires_key=ep.requires_key)
    return ModelList(fallback, requires_key=ep.requires_key, from_fallback=bool(fallback))


async def _get(client: httpx.AsyncClient, url: str, headers: dict[str, str], label: str) -> str:
    try:
        async with client.stream("GET", url, headers=headers, timeout=TIMEOUT) as response:
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > MAX_PAGE_BYTES:
                    raise ProviderError(f"{label}: model list is larger than {MAX_PAGE_BYTES} bytes")
            if response.status_code >= 400:
                detail = error_message(body)
                raise ProviderError(f"{label}: HTTP {response.status_code}" + (f": {detail}" if detail else ""),
                                    status=response.status_code)
            return body.decode("utf-8", "replace")
    except httpx.TimeoutException:
        raise ProviderError(f"{label}: timed out listing models", retryable=True) from None
    except httpx.TransportError as e:
        raise ProviderError(f"{label}: connection failed ({type(e).__name__})", retryable=True) from None


def _same_origin(a: str, b: str) -> bool:
    pa, pb = urlsplit(a), urlsplit(b)
    return pa.scheme in ("http", "https") and (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc)


def _with_param(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != key] + [(key, value)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
