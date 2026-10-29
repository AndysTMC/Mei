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
from .http_stream import TIMEOUT, check_key_transport, error_message, key_error, key_rejected, scrub
from .profiles import PROFILES, credential_headers

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
    headers = {**profile.headers, **credential_headers(profile, api_key)}
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


def credential_allowed(provider_id: str, requested_url: str, configured_url: str) -> bool:
    """Whether a stored key may be sent to `requested_url`: only to the provider's own endpoint or
    the one saved in the user's settings. Any local process can call ListModels with a URL, and
    Mei must not hand it the user's key (a confused deputy, §13.7)."""
    if not requested_url.strip():
        return True  # the provider's default endpoint
    profile = PROFILES[provider_id]
    allowed = {_origin(profile.chat_url), _origin(profile.models_url), _origin(configured_url)} - {""}
    return _origin(requested_url) in allowed


def _origin(url: str) -> str:
    parts = urlsplit(url.strip())
    return f"{parts.scheme}://{parts.netloc}".lower() if parts.scheme in ("http", "https") and parts.netloc else ""


def parse_models(text: str, kind: str) -> list[str]:
    """Model ids from one catalog page. Raises ValueError if the page isn't JSON."""
    data = json.loads(text)
    out: list[str] = []
    for item in _catalog_items(data, kind):
        if not isinstance(item, dict):
            continue
        methods = item.get("supportedGenerationMethods")
        if kind == "gemini" and isinstance(methods, list) and "generateContent" not in methods:
            continue  # embedding-only and similar models can't chat
        value = _model_id(item, kind)
        if value and value not in out:
            out.append(value)
    return out


def _catalog_items(data: object, kind: str) -> list:
    if kind == "github":
        items = data if isinstance(data, list) else _field(data, "models") or _field(data, "data")
    elif kind in ("gemini", "ollama"):
        items = _field(data, "models")
    else:
        items = _field(data, "data")
    return items if isinstance(items, list) else []


def _field(data: object, name: str) -> object:
    return data.get(name) if isinstance(data, dict) else None


def _model_id(item: dict, kind: str) -> str:
    if kind == "gemini":
        value = item.get("name")
        return value.removeprefix("models/") if isinstance(value, str) else ""
    value = item.get("name") or item.get("model") if kind == "ollama" else item.get("id") or item.get("display_name")
    return value if isinstance(value, str) else ""


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
    if api_key:
        check_key_transport(ep.url, profile.label)
    models: list[str] = []
    page: str | None = ep.url
    for _ in range(MAX_PAGES):
        if not page:
            break
        text = await _get(client, page, ep.headers, profile.label)
        try:
            found = parse_models(text, ep.kind)
        except ValueError:
            raise ProviderError(f"{profile.label}: the model list from {page} isn't JSON (check the endpoint URL)") \
                from None
        models += [m for m in found if m not in models]
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
                detail = scrub(error_message(body), headers)
                if key_rejected(response.status_code, body):
                    raise key_error(label, response.status_code, detail)
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
