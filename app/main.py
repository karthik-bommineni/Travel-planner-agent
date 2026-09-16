"""Trip planner: extract → Python plan → write-up. Optional --tools uses Gemini function calling."""

from __future__ import annotations

import argparse
import sys

from .agent import run_agent
from .pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plan a 2026 trip from a natural-language prompt."
    )
    parser.add_argument("prompt", nargs="*", help="Trip request")
    parser.add_argument(
        "--tools",
        action="store_true",
        help="Use the Gemini tool-calling agent instead of extract→planner→report",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Hide pipeline/tool traces",
    )
    args = parser.parse_args()
    prompt = " ".join(args.prompt).strip()
    if not prompt:
        parser.print_help()
        print(
            '\nExample: python -m app.main "2 people, HYD to Munich on 2026-06-15, 3 nights, budget 4000"'
        )
        sys.exit(1)
    trace = not args.quiet
    if args.tools:
        print(run_agent(prompt, trace=trace))
    else:
        print(run_pipeline(prompt, trace=trace))


if __name__ == "__main__":
    main()
