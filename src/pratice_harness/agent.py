from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Protocol

from .harness import Actor, SecurityHarness
from .schemas import TOOL_DEFINITIONS

MAX_ITERATIONS = 5
SYSTEM_PROMPT = (
    "You assist with one restaurant, River Table in Phnom Penh. Use tools to answer questions about cuisines, menus, "
    "and reservations. Ask for missing reservation details instead of guessing. "
    "Use list_reservations when a customer or owner needs to find a reservation ID. "
    "For previous or past reservations use time_scope=past; for future or upcoming reservations use time_scope=upcoming. "
    "Only call reservations previous if their reservation time has passed. "
    "Menu edits are for owners. Reservation edits and cancellations require an allowed session. "
    "Observe every tool result before responding. If a tool call is denied, explain the restriction. "
    "Never claim an action succeeded unless its tool result confirms success."
)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ModelTurn:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class Model(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> ModelTurn: ...


@dataclass
class AgentResult:
    response: str
    messages: list[dict]
    iterations: int
    status: str


class AgentLoop:
    def __init__(self, model: Model, harness: SecurityHarness, max_iterations: int = MAX_ITERATIONS) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        self.model = model
        self.harness = harness
        self.max_iterations = max_iterations

    def run(
        self,
        prompt: str,
        actor: Actor,
        history: list[dict] | None = None,
        on_delta: Callable[[str], None] | None = None,
        on_tool_event: Callable[[str, str], None] | None = None,
    ) -> AgentResult:
        messages: list[dict] = list(history) if history is not None else [
            {
                "role": "system",
                "content": f"{SYSTEM_PROMPT} Current local date and time: "
                           f"{datetime.now().astimezone().isoformat(timespec='minutes')}.",
            }
        ]
        messages.append({"role": "user", "content": prompt})
        current_iteration = 0
        while True:
            if current_iteration >= self.max_iterations:
                return AgentResult(
                    f"Stopped after {current_iteration} model iterations without a final response.",
                    messages,
                    current_iteration,
                    "iteration_limit",
                )
            current_iteration += 1
            if on_delta is not None and hasattr(self.model, "stream"):
                turn = self.model.stream(messages, TOOL_DEFINITIONS, on_delta)
            else:
                turn = self.model.complete(messages, TOOL_DEFINITIONS)

            if turn.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": turn.content,
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {"name": call.name, "arguments": call.arguments},
                            }
                            for call in turn.tool_calls
                        ],
                    }
                )
                for call in turn.tool_calls:
                    if on_tool_event is not None:
                        on_tool_event(call.name, "running")
                    result = self.harness.validate_and_run(call.name, call.arguments, actor)
                    messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name, "content": result})
                    if on_tool_event is not None:
                        observation = json.loads(result)
                        status = (
                            "done" if observation["status"] == "success"
                            else "blocked" if observation.get("error_type") == "PermissionDenied"
                            else "failed"
                        )
                        on_tool_event(call.name, status)
                continue

            if turn.content:
                messages.append({"role": "assistant", "content": turn.content})
                return AgentResult(turn.content, messages, current_iteration, "complete")

            return AgentResult(
                "The model returned neither a response nor a tool call.",
                messages,
                current_iteration,
                "empty_response",
            )


class LMStudioModel:
    def __init__(self, base_url: str, model_id: str) -> None:
        from openai import OpenAI

        self.client = OpenAI(base_url=base_url, api_key="lm-studio", timeout=120.0)
        self.model_id = model_id

    def complete(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        return self.stream(messages, tools, lambda _delta: None)

    def stream(
        self, messages: list[dict], tools: list[dict], on_delta: Callable[[str], None]
    ) -> ModelTurn:
        from openai import APIConnectionError, APIStatusError, APITimeoutError

        try:
            chunks = self.client.chat.completions.create(
                model=self.model_id, messages=messages, tools=tools, tool_choice="auto", stream=True
            )
            content: list[str] = []
            calls: dict[int, dict[str, str]] = {}
            for chunk in chunks:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                for call in delta.tool_calls or []:
                    item = calls.setdefault(call.index, {"id": "", "name": "", "arguments": ""})
                    if call.id:
                        item["id"] += call.id
                    if call.function:
                        if call.function.name:
                            item["name"] += call.function.name
                        if call.function.arguments:
                            item["arguments"] += call.function.arguments
                if delta.content:
                    content.append(delta.content)
                    if not calls:
                        on_delta(delta.content)
        except APIStatusError as exc:
            try:
                detail = exc.response.json()["error"]["message"]
            except (KeyError, TypeError, ValueError):
                detail = exc.message
            raise ConnectionError(f"LM Studio returned HTTP {exc.status_code}: {detail}") from exc
        except APITimeoutError as exc:
            raise ConnectionError(f"Model request timed out at {self.client.base_url}.") from exc
        except APIConnectionError as exc:
            reason = str(exc.__cause__ or exc)
            raise ConnectionError(f"Could not connect to model server at {self.client.base_url}: {reason}") from exc
        except Exception as exc:
            raise ConnectionError(f"Model request failed: {exc}") from exc
        return ModelTurn(
            content="".join(content) or None,
            tool_calls=[
                ToolCall(call["id"], call["name"], call["arguments"])
                for _, call in sorted(calls.items())
            ],
        )
