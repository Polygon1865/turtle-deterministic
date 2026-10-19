import json

import pytest

from turtlefw.agent import AgentError, OpenAICompatibleLLM


class _Transport:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def post(self, url, headers, payload):
        self.calls.append((url, headers, payload))
        return {"choices": [{"message": {"content": self.content}}]}


def test_openai_compatible_parses_json_content():
    transport = _Transport(json.dumps({"claims": []}))
    llm = OpenAICompatibleLLM(
        base_url="https://llm.test/v1",
        model="test-model",
        api_key="secret",
        transport=transport,
    )
    assert llm.complete("system", {"code": "600887"}) == {"claims": []}
    assert transport.calls[0][0] == "https://llm.test/v1/chat/completions"
    assert transport.calls[0][1]["Authorization"] == "Bearer secret"


def test_openai_compatible_rejects_bad_content():
    llm = OpenAICompatibleLLM(
        base_url="https://llm.test/v1",
        model="test-model",
        api_key="secret",
        transport=_Transport("not json"),
    )
    with pytest.raises(AgentError):
        llm.complete("system", {})
