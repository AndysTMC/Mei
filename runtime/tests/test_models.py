"""Model discovery; endpoint expectations are the ones tests/modelList.test.ts used."""

import json

import httpx
import pytest

from mei.providers.base import ProviderError
from mei.providers.models import (credential_allowed, endpoint, list_models, model_list_url, next_page_url,
                                  parse_models)

EXPECTED = {
    "ollama": "http://127.0.0.1:11434/api/tags",
    "llamacpp": "http://127.0.0.1:8080/v1/models",
    "lmstudio": "http://127.0.0.1:1234/v1/models",
    "openai": "https://api.openai.com/v1/models",
    "anthropic": "https://api.anthropic.com/v1/models?limit=1000",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
    "groq": "https://api.groq.com/openai/v1/models",
    "mistral": "https://api.mistral.ai/v1/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
    "deepseek": "https://api.deepseek.com/models",
    "fireworks": "https://api.fireworks.ai/inference/v1/models",
    "nvidia": "https://integrate.api.nvidia.com/v1/models",
}


@pytest.mark.parametrize("pid,url", EXPECTED.items())
def test_every_provider_maps_to_its_documented_catalog(pid, url):
    assert endpoint(pid).url == url


def test_custom_needs_a_url_and_derives_the_catalog_from_it():
    with pytest.raises(ProviderError):
        endpoint("custom")
    assert endpoint("custom", url="https://custom.test/v1/chat/completions").url == "https://custom.test/v1/models"


def test_auth_headers_and_overrides():
    assert endpoint("ollama", url="https://host.test/prefix/api/chat?ignored=1", api_key="t").url == \
        "https://host.test/prefix/api/tags"
    gem = endpoint("gemini", url="https://proxy.test/v1beta/", api_key="g")
    assert gem.url == "https://proxy.test/v1beta/models?pageSize=1000" and gem.headers == {"x-goog-api-key": "g"}
    assert endpoint("anthropic", api_key="a").headers["x-api-key"] == "a"
    assert endpoint("groq", api_key="b").headers["Authorization"] == "Bearer b"
    assert endpoint("openrouter").requires_key is False and endpoint("groq").requires_key is True


@pytest.mark.parametrize("chat,path,expected", [
    ("http://h:1/v1/chat/completions", "/v1/models", "http://h:1/v1/models"),
    ("http://h:1/base", "/v1/models", "http://h:1/base/v1/models"),
    ("http://h:1/base/v1", "/v1/models", "http://h:1/base/v1/models"),
    ("http://h:1", "/api/tags", "http://h:1/api/tags"),
])
def test_model_list_url(chat, path, expected):
    assert model_list_url(chat, path) == expected


def test_parse_each_catalog_shape():
    assert parse_models(json.dumps({"data": [{"id": "a"}, {"id": "a"}, {"display_name": "b"}, 3]}), "openai") == ["a", "b"]
    gem = {"models": [{"name": "models/g1", "supportedGenerationMethods": ["generateContent"]},
                      {"name": "models/embed", "supportedGenerationMethods": ["embedContent"]}]}
    assert parse_models(json.dumps(gem), "gemini") == ["g1"]
    assert parse_models(json.dumps({"models": [{"name": "qwen3"}, {"model": "llama"}]}), "ollama") == ["qwen3", "llama"]
    assert parse_models(json.dumps([{"id": "x"}]), "openai") == []


def test_pagination_stays_on_the_same_origin():
    cur = "https://api.test/v1/models?limit=10&page_token=old"
    assert next_page_url(cur, json.dumps({"next": "https://evil.test/steal"}), "openai") is None
    assert next_page_url(cur, json.dumps({"next": "https://api.test/v1/models?p=2"}), "openai") == "https://api.test/v1/models?p=2"
    replaced = next_page_url(cur, json.dumps({"next_page_token": "new"}), "openai")
    assert replaced == "https://api.test/v1/models?limit=10&page_token=new"
    assert "pageToken=t" in next_page_url("https://g.test/m?pageSize=1", json.dumps({"nextPageToken": "t"}), "gemini")
    assert next_page_url(cur, json.dumps({"has_more": True, "data": [{"id": "z"}]}), "openai").endswith("after_id=z")


async def test_list_models_pages_and_sends_the_key_only_to_the_catalog():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        if "after_id" in str(request.url):
            return httpx.Response(200, json={"data": [{"id": "m2"}], "has_more": False})
        return httpx.Response(200, json={"data": [{"id": "m1"}], "has_more": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await list_models(client, "anthropic", api_key="sk-ant")
    assert result.models == ["m1", "m2"] and not result.from_fallback
    assert all(r.url.host == "api.anthropic.com" and r.headers["x-api-key"] == "sk-ant" for r in seen)


async def test_missing_key_returns_suggestions_without_a_request():
    def handler(request):
        raise AssertionError("must not call the network without a key")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await list_models(client, "gemini")
    assert result.requires_key and result.from_fallback and result.models


async def test_http_errors_surface_the_providers_message():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"error": {"message": "bad key"}})))
    with pytest.raises(ProviderError, match="bad key"):
        await list_models(client, "groq", api_key="k")


async def test_a_page_that_is_not_json_is_a_clear_error():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>login</html>")))
    with pytest.raises(ProviderError, match="isn't JSON"):
        await list_models(client, "custom", url="http://127.0.0.1:9/v1/chat/completions")


def test_a_stored_key_only_goes_to_the_providers_own_or_configured_endpoint():
    assert credential_allowed("openai", "", "")
    assert credential_allowed("openai", "https://api.openai.com/v1/chat/completions", "")
    assert credential_allowed("openai", "https://API.openai.com/other/path", "")
    assert not credential_allowed("openai", "https://evil.test/v1/chat/completions", "")
    assert credential_allowed("openai", "https://proxy.test/v1/chat/completions", "https://proxy.test/v1")
    assert not credential_allowed("openai", "http://proxy.test/v1", "https://proxy.test/v1")  # scheme matters
    assert not credential_allowed("custom", "https://evil.test/v1", "")
    assert credential_allowed("custom", "http://127.0.0.1:8080/v1/chat/completions", "")  # custom's default
    assert not credential_allowed("openai", "ftp://api.openai.com", "")
