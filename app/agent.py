"""Optional path: Gemini chooses tools; Python runs them. Default CLI uses pipeline.py."""

from __future__ import annotations

from .llm import generate_with_tools, text_from_content, tool_result_content, user_text
from .tools.registry import DECLARATIONS, run_tool

MAX_TURNS = 12

SYSTEM = """
You are a trip planner over a local 2026 flight and hotel catalog.

Call search_flights and search_hotels whenever you need inventory. Call them
once per leg and once per stay city. Prefer ids from tool results only.

Then call score_budget with those ids, passenger count, and nights. Never
invent offer ids, hotel ids, or money totals. Quote totals from score_budget.

Rules:
- Dates are YYYY-MM-DD in 2026.
- You cannot book or pay. Selecting catalog rows is the plan.
- Amenities the user named are required filters.
- cheapest (default): sort_by price. most expensive / luxury: sort_by most_expensive.
- If they gave no budget, omit budget_cap.
- If nights per city are missing, say so and stop. Do not guess nights.
- Do not invent a return flight unless they asked for it.
- If search returns nothing or score_budget is over_budget, say so clearly.
""".strip()


def run_agent(prompt: str, *, trace: bool = True) -> str:
    history = [user_text(prompt)]
    for _ in range(MAX_TURNS):
        content = generate_with_tools(history, system=SYSTEM, declarations=DECLARATIONS)
        history.append(content)
        calls = [part for part in (content.parts or []) if getattr(part, "function_call", None)]
        if not calls:
            return text_from_content(content)
        results = []
        for part in calls:
            call = part.function_call
            args = dict(call.args or {})
            if trace:
                print(f"[agent] {call.name}({args})")
            result = run_tool(call.name, args)
            results.append((call.name, result))
        history.append(tool_result_content(results))
    return "Stopped: too many tool rounds without a final answer."
