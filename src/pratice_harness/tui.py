"""Small curses chat interface for the restaurant agent."""

from __future__ import annotations

import curses
import textwrap

from .agent import AgentLoop
from .harness import Actor


def _render(screen, actor: Actor, entries: list[tuple[str, str]], draft: str) -> None:
    screen.erase()
    height, width = screen.getmaxyx()
    if height < 5 or width < 24:
        screen.addnstr(0, 0, "Resize terminal to at least 24x5", max(0, width - 1))
        screen.refresh()
        return

    accent = curses.color_pair(1) if curses.has_colors() else 0
    user_color = curses.color_pair(2) if curses.has_colors() else 0
    error_color = curses.color_pair(3) if curses.has_colors() else 0
    tool_color = curses.color_pair(4) if curses.has_colors() else 0
    screen.addnstr(0, 1, "River Table", width - 2, accent | curses.A_BOLD)
    session = f"{actor.role} · {actor.user_id}"
    if len(session) < width - 16:
        screen.addnstr(0, width - len(session) - 2, session, len(session), curses.A_DIM)

    lines: list[str] = []
    for speaker, message in entries:
        prefix = f"{speaker}: "
        for index, paragraph in enumerate(message.splitlines() or [""]):
            wrapped = textwrap.wrap(
                paragraph, width=width - len(prefix) - 2, break_long_words=True,
                replace_whitespace=False, drop_whitespace=False,
            ) or [""]
            lines.extend((prefix if index == 0 and part == 0 else " " * len(prefix)) + line
                         for part, line in enumerate(wrapped))
        lines.append("")
    visible = lines[-(height - 3):]
    for row, line in enumerate(visible, start=1):
        if line.startswith("You: "):
            color = user_color
        elif line.startswith("Error: "):
            color = error_color
        elif line.startswith("Tool: "):
            color = tool_color
        else:
            color = accent if line.startswith("Agent: ") else 0
        screen.addnstr(row, 1, line, width - 2, color)

    screen.hline(height - 2, 1, curses.ACS_HLINE, width - 2, curses.A_DIM)
    prompt = "> " + draft
    visible_prompt = prompt[-(width - 1):]
    screen.addnstr(height - 1, 1, visible_prompt, width - 2)
    screen.move(height - 1, min(len(visible_prompt) + 1, width - 2))
    screen.refresh()


def run_tui(agent: AgentLoop, actor: Actor) -> None:
    def chat(screen) -> None:
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        if curses.has_colors():
            try:
                curses.start_color()
                curses.use_default_colors()
                curses.init_pair(1, curses.COLOR_CYAN, -1)
                curses.init_pair(2, curses.COLOR_GREEN, -1)
                curses.init_pair(3, curses.COLOR_RED, -1)
                curses.init_pair(4, curses.COLOR_YELLOW, -1)
            except curses.error:
                pass
        screen.keypad(True)
        entries: list[tuple[str, str]] = [
            ("", "Ask about the menu or reservations.  /quit to exit"),
        ]
        history: list[dict] | None = None
        draft = ""
        while True:
            _render(screen, actor, entries, draft)
            try:
                key = screen.get_wch()
            except curses.error:
                continue
            if key in ("\x03",):
                break
            if key in ("\n", "\r", curses.KEY_ENTER):
                prompt = draft.strip()
                draft = ""
                if not prompt:
                    continue
                if prompt.casefold() in {"/quit", "/exit"}:
                    break
                entries.append(("You", prompt))
                answer_index: int | None = None
                tool_index: int | None = None

                def show_delta(delta: str) -> None:
                    nonlocal answer_index
                    if answer_index is None:
                        answer_index = len(entries)
                        entries.append(("Agent", delta))
                    else:
                        speaker, response = entries[answer_index]
                        entries[answer_index] = (speaker, response + delta)
                    _render(screen, actor, entries, draft)

                def show_tool(name: str, status: str) -> None:
                    nonlocal answer_index, tool_index
                    if status == "running":
                        answer_index = None
                        tool_index = len(entries)
                        entries.append(("Tool", f"{name} (running...)"))
                    elif tool_index is not None:
                        entries[tool_index] = ("Tool", f"{name} ({status})")
                    _render(screen, actor, entries, draft)

                _render(screen, actor, entries, draft)
                try:
                    result = agent.run(
                        prompt, actor, history, on_delta=show_delta, on_tool_event=show_tool
                    )
                except (ConnectionError, RuntimeError, ValueError) as exc:
                    entries.append(("Error", str(exc)))
                else:
                    history = result.messages
                    if answer_index is None:
                        entries.append(("Agent", result.response))
                    else:
                        entries[answer_index] = ("Agent", result.response)
                continue
            if key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                draft = draft[:-1]
            elif key == "\x15":
                draft = ""
            elif isinstance(key, str) and key.isprintable():
                draft += key

    curses.wrapper(chat)
