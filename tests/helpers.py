from __future__ import annotations

from mini_agent.llm.base import LLMError
from mini_agent.protocol import ModelResponse, ToolCall


class FakeLLM:
    model = "fake"

    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, system, messages, tools):
        self.calls.append({"system": system, "messages": messages, "tools": tools})
        if not self.responses:
            raise AssertionError("FakeLLM ran out of scripted responses")
        return self.responses.pop(0)


class FailingLLM:
    model = "fake"

    def complete(self, system, messages, tools):
        raise LLMError("simulated transport failure")


def text_response(text: str) -> ModelResponse:
    return ModelResponse(
        text=text,
        raw_content=[{"type": "text", "text": text}],
        stop_reason="end_turn",
        usage={"input_tokens": 10, "output_tokens": 5},
    )


def tool_response(calls: list[ToolCall]) -> ModelResponse:
    return ModelResponse(
        text=None,
        tool_calls=calls,
        raw_content=[
            {
                "type": "tool_use",
                "id": call.id,
                "name": call.name,
                "input": call.arguments,
            }
            for call in calls
        ],
        stop_reason="tool_use",
        usage={"input_tokens": 10, "output_tokens": 5},
    )
