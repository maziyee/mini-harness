"""The agent loop: model -> tools -> model -> final answer."""

from __future__ import annotations

from typing import Any, Callable

from . import config, prompt
from .context import ContextManager
from .llm.base import LLMClient, LLMError
from .memory import MemoryBackend
from .protocol import (
    ModelResponse,
    assistant_message,
    message_text,
    strip_thinking_blocks,
    tool_result_message,
    user_message,
)
from .session import Session, SessionStore
from .tools import ToolContext, ToolExecutor
from .trace import TraceLogger


class AgentLoop:
    def __init__(
        self,
        llm: LLMClient,
        tool_executor: ToolExecutor,
        session_store: SessionStore,
        memory_store: MemoryBackend,
        context: ContextManager | None = None,
        trace_factory: Callable[[str, str], TraceLogger] | None = None,
        on_thought: Callable[[str], None] | None = None,
        keep_thinking_in_memory: bool = False,
        max_steps: int = 8,
        max_turns: int = 20,
    ) -> None:
        self.llm = llm
        self.tool_executor = tool_executor
        self.session_store = session_store
        self.memory_store = memory_store
        self.context = context or ContextManager()
        self.trace_factory = trace_factory or (
            lambda user_id, session_id: TraceLogger(user_id, session_id)
        )
        self.on_thought = on_thought
        self.keep_thinking_in_memory = keep_thinking_in_memory
        self.max_steps = max_steps
        self.max_turns = max_turns

    def run_turn(self, session: Session, user_text: str) -> str:
        user_text = user_text.strip()
        if not user_text:
            return "Please enter a message."

        trace = self.trace_factory(session.user_id, session.id)
        if session.turn_count >= self.max_turns:
            return (
                f"Reached the maximum of {self.max_turns} turns for this session. "
                "Start a new session to continue."
            )

        session.status = "busy"
        if not session.title:
            session.title = user_text[:40]
        user_msg = user_message(user_text)
        session.messages.append(user_msg)
        trace.log(
            "user_message",
            chars=len(user_text),
            preview=user_text[:200],
        )

        for record in self.memory_store.capture_from_user_text(
            session.user_id, user_text, session.id
        ):
            trace.log(
                "memory_write",
                memory_id=record.id,
                memory_type=record.type,
                content_chars=len(record.content),
                preview=record.content[:120],
            )

        memories = self.memory_store.recall(session.user_id, user_text, top_k=3)
        if session.turn_count == 0:
            startup = self.memory_store.startup_memories(session.user_id, top_k=5)
            seen = {record.id for record in memories}
            memories = startup + [record for record in memories if record.id not in seen]
        if memories:
            trace.log(
                "memory_recall",
                ids=[record.id for record in memories],
                reason="startup+keyword" if session.turn_count == 0 else "keyword",
            )
            self.memory_store.touch(session.user_id, [record.id for record in memories])

        tool_schemas = self.tool_executor.schemas()
        tool_ctx = ToolContext(
            user_id=session.user_id,
            session=session,
            trace=trace,
            artifacts_dir=config.artifacts_dir(),
            memory_store=self.memory_store,
        )
        system = prompt.build_system_prompt(session, memories)

        compact_info = self.context.maybe_compact(session, self.llm, system)
        if compact_info:
            trace.log("compact", **compact_info)
            # maybe_compact already archived the folded raw messages to
            # artifacts/transcripts before mutating session.messages.  This
            # save persists the compacted *working* state (recent messages +
            # summary); the archive preserves the raw history.
            self.session_store.save(session)
            # The summary lives in the system prompt; rebuild it.
            system = prompt.build_system_prompt(session, memories)

        tools_used: list[str] = []
        for step in range(self.max_steps):
            trace.log(
                "llm_request",
                model=self.llm.model,
                messages=len(session.messages),
                estimated_tokens=self.context.estimate_tokens(system, session.messages),
                step=step + 1,
            )
            try:
                response = self.llm.complete(system, session.messages, tool_schemas)
            except LLMError as exc:
                return self._fail_turn(session, user_msg, exc, trace)
            except Exception as exc:  # defensive: never crash the REPL
                return self._fail_turn(session, user_msg, exc, trace)

            trace.log(
                "llm_response",
                stop_reason=response.stop_reason,
                usage=response.usage,
                text_chars=len(response.text or ""),
                thought_chars=len(response.thought or ""),
                # Tool arguments are recorded by the following tool_call
                # events; keep only names here to avoid duplicating payloads.
                tool_names=[call.name for call in response.tool_calls],
            )

            # Thinking is display-only: output it, but it is stripped before
            # session/transcript persistence.
            if response.thought and self.on_thought is not None:
                self.on_thought(response.thought)

            content = response.raw_content
            if not content:
                if response.tool_calls:
                    content = [
                        {
                            "type": "tool_use",
                            "id": call.id,
                            "name": call.name,
                            "input": call.arguments,
                        }
                        for call in response.tool_calls
                    ]
                else:
                    content = [{"type": "text", "text": response.text or ""}]
            session.messages.append(assistant_message(content))

            if not response.tool_calls:
                final = response.text or "(The model returned no text.)"
                if response.stop_reason == "max_tokens":
                    final += "\n\n[Response truncated by max_tokens.]"
                return self._finish_turn(session, final, trace, tools_used)

            results = []
            for call in response.tool_calls:
                trace.log(
                    "tool_call",
                    tool=call.name,
                    call_id=call.id,
                    arguments=call.arguments,
                )
                result = self.tool_executor.execute(call, tool_ctx)
                trace.log(
                    "tool_result",
                    tool=call.name,
                    call_id=call.id,
                    ok=not result.is_error,
                    chars=len(result.content),
                )
                results.append(result)
                tools_used.append(call.name)
            session.messages.append(tool_result_message(results))
            # The in-memory session is enough for the next model call; persist
            # at the turn boundary instead of once per tool batch.
            # Goal/todo/memory may have changed; refresh the dynamic system tail.
            system = prompt.build_system_prompt(session, memories)

        final = (
            f"Stopped after {self.max_steps} tool steps in one turn. "
            "The task may be incomplete; ask me to continue."
        )
        # Close the turn with an assistant message. Without this, the session
        # would end on a tool_result user message, and the next user turn
        # would append another user message without an assistant in between.
        session.messages.append(
            assistant_message([{"type": "text", "text": final}])
        )
        return self._finish_turn(session, final, trace, tools_used)

    def _finish_turn(
        self,
        session: Session,
        final: str,
        trace: TraceLogger,
        tools_used: list[str],
    ) -> str:
        session.turn_count += 1
        session.status = "idle"
        self.session_store.save(session)
        # Thinking is display-only by default. If the caller explicitly wants
        # cross-turn replay, keep it in memory (never on disk).
        if not self.keep_thinking_in_memory:
            session.messages = strip_thinking_blocks(session.messages)
        trace.log(
            "turn_end",
            turn=session.turn_count,
            tools_used=tools_used,
            response_chars=len(final),
        )
        return final

    def _fail_turn(
        self,
        session: Session,
        user_msg: dict[str, Any],
        exc: Exception,
        trace: TraceLogger,
    ) -> str:
        # If the failure happened before any assistant/tool output, roll the
        # user message back so a retry does not create two user turns.
        if session.messages and session.messages[-1] == user_msg:
            session.messages.pop()
        else:
            session.messages.append(
                assistant_message(
                    [{"type": "text", "text": f"[Interrupted by an error: {exc}]"}]
                )
            )
        session.status = "error"
        self.session_store.save(session)
        if not self.keep_thinking_in_memory:
            session.messages = strip_thinking_blocks(session.messages)
        trace.log("error", stage="llm", error=str(exc))
        return f"[LLM error] {exc}"


def compact_session_summary(session: Session) -> str:
    """Small helper for /history and debugging."""
    if not session.summary:
        return ""
    return session.summary


def last_exchange_text(session: Session, limit: int = 6) -> str:
    messages = session.messages[-limit:]
    return "\n".join(message_text(message) for message in messages)
