"""Chat with the sample River Table restaurant agent."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .agent import AgentLoop, LMStudioModel
from .harness import Actor, SecurityHarness
from .tools import RestaurantDirectory
from .tui import run_tui


def load_env(path: Path = Path(".env")) -> None:
    """Read the project's simple KEY=VALUE settings without overriding the shell."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            os.environ.setdefault(key, value.strip().strip('"\''))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", help="Ask one question and print the streamed answer")
    args = parser.parse_args()
    if args.prompt is not None and not args.prompt.strip():
        parser.error("--prompt needs a question")

    load_env()
    directory = RestaurantDirectory(os.getenv("RESTAURANT_DB_PATH", "data/restaurants.sqlite3"))
    try:
        role = os.getenv("RESTAURANT_ROLE", "guest")
        user_id = os.getenv("RESTAURANT_USER_ID") or {
            "guest": "guest", "customer": "customer-1", "owner": "owner-1"
        }.get(role, "")
        actor = Actor(role, user_id)
        agent = AgentLoop(
            LMStudioModel(
                os.getenv("BASE_URL") or os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1"),
                os.getenv("CHAT_MODEL") or os.getenv("LM_STUDIO_MODEL", "qwen3.5-4b"),
            ),
            SecurityHarness(directory),
        )
        if args.prompt is None:
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                parser.exit(2, "The TUI needs a terminal. Use --prompt for a one-shot question.\n")
            run_tui(agent, actor)
        else:
            streamed_text = ""

            def print_delta(delta: str) -> None:
                nonlocal streamed_text
                streamed_text += delta
                print(delta, end="", flush=True)

            def print_tool(name: str, status: str) -> None:
                if status == "running":
                    if streamed_text and not streamed_text.endswith("\n"):
                        print()
                    print(f"Tool: {name}...", end="", flush=True)
                else:
                    print(f" {status}", flush=True)

            result = agent.run(
                args.prompt, actor, on_delta=print_delta, on_tool_event=print_tool
            )
            if streamed_text != result.response:
                if streamed_text:
                    print()
                print(result.response)
            else:
                print()
    except (ConnectionError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"Restaurant agent error: {exc}\n")
    finally:
        directory.close()


if __name__ == "__main__":
    main()
