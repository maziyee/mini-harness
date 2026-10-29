"""CLI / REPL for MiniAgent."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import config
from .context import ContextManager
from .llm.anthropic import AnthropicClient
from .llm.base import LLMError
from .loop import AgentLoop
from .memory import MemoryStore
from .protocol import message_text
from .session import Session, SessionStore
from .tools import build_default_tools
from .tools.todo import format_todos
from .trace import trace_path


def load_dotenv() -> None:
    candidates = [Path.cwd() / ".env", config.REPO_ROOT / ".env"]
    path = next((item for item in candidates if item.exists()), None)
    if path is None:
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _print_thinking(text: str) -> None:
    print(f"\n[thinking]\n{text}\n")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def build_loop(args: argparse.Namespace, cfg: config.AppConfig) -> AgentLoop:
    llm = AnthropicClient(
        api_key=cfg.llm.api_key,
        auth_token=cfg.llm.auth_token,
        model=args.model or cfg.llm.model,
        base_url=cfg.llm.base_url,
        max_tokens=cfg.llm.max_tokens,
        timeout=cfg.llm.timeout if cfg.llm.timeout is not None else 60.0,
        max_retries=cfg.llm.max_retries if cfg.llm.max_retries is not None else 3,
        thinking=cfg.llm.thinking,
        thinking_budget=cfg.llm.thinking_budget,
    )
    tool_executor = build_default_tools()
    session_store = SessionStore()
    memory_store = MemoryStore()
    context_window = (
        args.context_window
        if args.context_window is not None
        else (cfg.agent.context_window or 200_000)
    )
    context = ContextManager(context_window=context_window)

    show_thinking = args.show_thinking
    if show_thinking is None:
        show_thinking = cfg.llm.show_thinking
    if show_thinking is None:
        show_thinking = _env_bool("ANTHROPIC_SHOW_THINKING", True)

    keep_thinking = args.keep_thinking_in_memory
    if keep_thinking is None:
        keep_thinking = cfg.llm.keep_thinking_in_memory
    if keep_thinking is None:
        keep_thinking = _env_bool("ANTHROPIC_KEEP_THINKING_IN_MEMORY", False)

    max_turns = (
        args.max_turns
        if args.max_turns is not None
        else (cfg.agent.max_turns or 20)
    )
    return AgentLoop(
        llm=llm,
        tool_executor=tool_executor,
        session_store=session_store,
        memory_store=memory_store,
        context=context,
        on_thought=_print_thinking if show_thinking else None,
        keep_thinking_in_memory=keep_thinking,
        max_steps=cfg.agent.max_steps or 8,
        max_turns=max_turns,
    )


def _print_sessions(store: SessionStore, user_id: str) -> None:
    items = store.list(user_id)
    if not items:
        print("No sessions yet.")
        return
    print(f"Sessions for {user_id}:")
    for item in items:
        print(
            f"  {item['id']:<28} turns={item['turn_count']:<3} "
            f"status={item['status']:<8} {item['title']}"
        )


def _print_history(session: Session, limit: int) -> None:
    messages = session.messages[-limit:] if limit > 0 else session.messages
    if not messages:
        print("No history.")
        return
    for message in messages:
        role = message.get("role", "?")
        text = message_text(message)
        if text:
            print(f"[{role}] {text}")


def _print_memory(store: MemoryStore, user_id: str) -> None:
    print(f"JSON: {store.json_path(user_id)}")
    print(f"MD:   {store.markdown_path(user_id)}")
    records = store.load(user_id)
    if not records:
        print("No long-term memories.")
        return
    for record in records:
        print(f"- [{record.type}, {record.created_at[:10]}] {record.content}")


def _print_trace(user_id: str, session_id: str) -> None:
    path = trace_path(user_id, session_id)
    if not path.exists():
        print(f"No trace yet: {path}")
        return
    print(f"Trace: {path}")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[-20:]:
        print(line)


def _resolve_session(
    store: SessionStore, user_id: str, session_id: str | None, new: bool
) -> Session:
    if new:
        return store.create(user_id)
    if session_id:
        return store.get_or_create(user_id, session_id)
    latest = store.latest(user_id)
    return latest or store.create(user_id)


def _repl(loop: AgentLoop, store: SessionStore, memory: MemoryStore, user_id: str, session: Session) -> None:
    print(f"MiniAgent · user={user_id} · session={session.id}")
    print("Type /help for commands, /quit to exit.\n")
    current = session
    while True:
        try:
            raw = input(f"{user_id}@{current.id}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            store.save(current)
            break
        if not raw:
            continue
        if raw.startswith("/"):
            parts = raw.split(maxsplit=1)
            command = parts[0].lower()
            argument = parts[1].strip() if len(parts) > 1 else ""
            if command in {"/quit", "/exit"}:
                store.save(current)
                break
            if command == "/help":
                print(
                    "/new [title]   new session\n"
                    "/sessions      list sessions\n"
                    "/switch <id>   switch session\n"
                    "/history [n]   show recent messages\n"
                    "/todos         show current todos\n"
                    "/memory        show long-term memory\n"
                    "/trace         show trace path and tail\n"
                    "/quit          exit"
                )
                continue
            if command == "/new":
                store.save(current)
                current = store.create(user_id, title=argument)
                print(f"Switched to new session {current.id}.")
                continue
            if command == "/sessions":
                _print_sessions(store, user_id)
                continue
            if command == "/switch":
                if not argument:
                    print("Usage: /switch <session-id>")
                    continue
                try:
                    loaded = store.load(user_id, argument)
                except ValueError as exc:
                    print(f"Error: {exc}")
                    continue
                if loaded is None:
                    print(f"Session not found: {argument}")
                    continue
                store.save(current)
                current = loaded
                print(f"Switched to session {current.id}.")
                continue
            if command == "/history":
                try:
                    limit = int(argument) if argument else 10
                except ValueError:
                    limit = 10
                _print_history(current, limit)
                continue
            if command == "/todos":
                print(format_todos(current.todos))
                continue
            if command == "/memory":
                _print_memory(memory, user_id)
                continue
            if command == "/trace":
                _print_trace(user_id, current.id)
                continue
            print(f"Unknown command: {command}. Type /help.")
            continue

        try:
            response = loop.run_turn(current, raw)
        except KeyboardInterrupt:
            print("\n[interrupted]")
            continue
        print(f"\nassistant> {response}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mini-agent",
        description="A minimal agent runtime (Anthropic backend).",
    )
    parser.add_argument("--user", default=os.environ.get("MINI_AGENT_USER", "alice"))
    parser.add_argument("--session", help="Session id (window). Create it if missing.")
    parser.add_argument("--new", action="store_true", help="Create a new session.")
    parser.add_argument("--config", help="Path to config.json.")
    parser.add_argument("--model", help="Anthropic model id.")
    parser.add_argument("-p", "--prompt", help="Run one prompt and exit.")
    parser.add_argument("--list-sessions", action="store_true")
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument(
        "--show-thinking",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Print Anthropic thinking blocks. "
            "Default: config.json / ANTHROPIC_SHOW_THINKING / on."
        ),
    )
    parser.add_argument(
        "--keep-thinking-in-memory",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Keep thinking blocks in memory across user turns. "
            "They are never written to session/transcript/trace."
        ),
    )
    parser.add_argument(
        "--context-window",
        type=int,
        default=None,
        help="Token window used for compaction estimates.",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    try:
        cfg = config.load_app_config(args.config)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if cfg.storage.root:
        os.environ["MINI_AGENT_HOME"] = str(
            Path(cfg.storage.root).expanduser()
        )

    store = SessionStore()
    memory = MemoryStore()

    if args.list_sessions:
        _print_sessions(store, args.user)
        return 0

    if args.prompt:
        try:
            loop = build_loop(args, cfg)
        except LLMError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        try:
            session = _resolve_session(store, args.user, args.session, args.new)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        print(loop.run_turn(session, args.prompt))
        return 0

    try:
        loop = build_loop(args, cfg)
    except LLMError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print(
            "Hint: edit config.json (or .env) and set an API key.",
            file=sys.stderr,
        )
        return 2

    try:
        session = _resolve_session(store, args.user, args.session, args.new)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    _repl(loop, store, memory, args.user, session)
    return 0
