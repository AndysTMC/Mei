"""OpenAI Responses API adapter (streaming), used for OpenCode's GPT/Grok routes.

Requests are sent with `store: false`. Failed responses raise; incomplete ones keep what was
written and append the reason, or raise if nothing was written.
"""

from collections.abc import AsyncIterator

import httpx

from .base import Done, ModelEvent, ModelRequest, ProviderError, TextDelta, ThinkingDelta, Usage
from .http_stream import error_message, first_int, loads, stream_post


class ResponsesProvider:
    def __init__(self, client: httpx.AsyncClient, *, label: str, url: str, model: str, api_key: str = "",
                 headers: dict[str, str] | None = None) -> None:
        if not model:
            raise ProviderError(f"{label}: no model selected")
        self.label = label
        self.model = model
        self._client = client
        self._url = url
        self._headers = {**(headers or {}), **({"Authorization": f"Bearer {api_key}"} if api_key else {})}

    def body(self, request: ModelRequest) -> dict:
        return {"model": self.model, "store": False, "stream": True,
                "input": [{"role": "developer" if t.role == "system" else t.role, "content": t.content}
                          for t in request.messages]}

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        wrote_text = False
        async for data in stream_post(self._client, self._url, self.body(request), self._headers, label=self.label):
            event = loads(data)
            if event is None:
                continue
            kind = event.get("type", "")
            if kind in ("response.output_text.delta", "response.refusal.delta") and event.get("delta"):
                wrote_text = True
                yield TextDelta(event["delta"])
            elif kind == "response.reasoning_summary_text.delta" and event.get("delta"):
                yield ThinkingDelta(event["delta"])
            elif kind in ("response.failed", "error"):
                raise ProviderError(f"{self.label}: {_failure(event)}")
            elif kind in ("response.completed", "response.incomplete"):
                usage = (event.get("response") or {}).get("usage") or {}
                yield Usage(first_int(usage, "input_tokens"), first_int(usage, "output_tokens"))
                if kind == "response.incomplete":
                    reason = _incomplete_reason(event)
                    if not wrote_text:
                        raise ProviderError(f"{self.label}: {reason}")
                    yield TextDelta(f"\n\n[{reason}]")
                break
        yield Done("stop")


def _failure(event: dict) -> str:
    response = event.get("response") if isinstance(event.get("response"), dict) else event
    return error_message(response) or error_message(event) or "Response generation failed."


def _incomplete_reason(event: dict) -> str:
    details = (event.get("response") or {}).get("incomplete_details") or {}
    reason = details.get("reason") if isinstance(details, dict) else None
    return f"Response incomplete: {reason}." if reason else "Response generation was incomplete."
