"""Provider-agnostic OpenAI-compatible chat adapter.

The adapter is deliberately transport-injectable: tests must never make a
network call. Credentials come from the environment, never from a prompt or a
report artifact.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .research_agent import AgentError


class Transport(Protocol):
    def post(
        self, url: str, headers: Mapping[str, str], payload: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


class UrllibTransport:
    def post(
        self, url: str, headers: Mapping[str, str], payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=dict(headers),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                parsed = json.loads(response.read().decode("utf-8"))
            if not isinstance(parsed, dict):
                raise AgentError("LLM response must be a JSON object")
            return parsed
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AgentError(f"LLM request failed: {exc}") from exc


@dataclass(slots=True)
class OpenAICompatibleLLM:
    base_url: str
    model: str
    api_key: str
    transport: Transport | None = None

    def complete(self, system: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if not self.api_key:
            raise AgentError("LLM API key is not configured")
        transport = self.transport or UrllibTransport()
        request = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False, default=str),
                },
            ],
        }
        response = transport.post(
            self.base_url.rstrip("/") + "/chat/completions",
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            request,
        )
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AgentError("LLM response missing choices[0].message.content") from exc
        if isinstance(content, Mapping):
            return dict(content)
        try:
            parsed = json.loads(str(content))
        except json.JSONDecodeError as exc:
            raise AgentError("LLM response is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise AgentError("LLM response must be a JSON object")
        return parsed
