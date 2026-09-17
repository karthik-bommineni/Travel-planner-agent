"""Gemini tool-calling agent: extract spec, search shortlists, pick ids, write itinerary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .extract import extract_trip_spec
from .llm import generate_with_tools, text_from_content, tool_result_content, user_text
from .tools.registry import DECLARATIONS, run_tool
from .trip_spec import TripSpec

MAX_TURNS = 24
GenerateFn = Callable[..., Any]
OnEvent = Callable[[dict[str, Any]], None]

SYSTEM = """
You are a trip planner over a local 2026 flight and hotel catalog.

You must use tools. Python searches, scores, and checks the timeline; you only
choose among rows the tools return.

Loop:
1. Call search_flights once per spec leg and search_hotels once per stay city.
   Use per-leg time_of_day/cabin and per-stay min_stars/amenities when present;
   otherwise use the top-level defaults. Do not invent extra cities or returns.
2. Each search returns a SHORTLIST. Pick ONLY offer_id / hotel_id values from
   those shortlists. Never invent ids.
3. Call score_budget with the chosen ids, passenger count, and nights.
   Use money only from that tool.
4. Call check_timeline with the same ids, nights, stay_cities, and check_ins.
   If it fails, pick other ids from the same shortlists and score again.
5. When budget and timeline are ok, write the itinerary (copy ids and amounts)
   as plain text with no further function calls.

If a search is empty or the trip is over_budget after retries, say so clearly.
Dates are YYYY-MM-DD in 2026. Amenities on a stay are required filters.
""".strip()


@dataclass
class AgentResult:
    text: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    spec: TripSpec | None = None


def _shortlist_ids(name: str, result: dict[str, Any]) -> list[str]:
    if name == "search_flights":
        return [str(row["offer_id"]) for row in result.get("flights") or [] if row.get("offer_id")]
    if name == "search_hotels":
        return [str(row["hotel_id"]) for row in result.get("hotels") or [] if row.get("hotel_id")]
    if name in {"score_budget", "check_timeline"}:
        ids = [str(item.get("offer_id") or item.get("hotel_id") or "") for item in result.get("line_items") or []]
        extra = list(result.get("flight_offer_ids") or []) + list(result.get("hotel_ids") or [])
        return [i for i in [*ids, *[str(x) for x in extra]] if i]
    return []


def _step_record(name: str, args: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    err = result.get("error")
    ok = result.get("ok")
    if ok is None:
        ok = not err
    record: dict[str, Any] = {
        "name": name,
        "args": args,
        "ok": bool(ok),
        "shortlist": _shortlist_ids(name, result),
    }
    if err:
        record["error"] = err
        record["ok"] = False
    if result.get("reason"):
        record["reason"] = result["reason"]
    if name == "score_budget" and result.get("total") is not None:
        record["total"] = result.get("total")
        record["remaining"] = result.get("remaining")
    return record


def run_agent(
    prompt: str,
    *,
    spec: TripSpec | None = None,
    trace: bool = True,
    on_event: OnEvent | None = None,
    generate_fn: GenerateFn | None = None,
    extract_fn: Callable[[str], TripSpec | dict] | None = None,
) -> AgentResult:
    emit = on_event or (lambda _event: None)
    generate = generate_fn or generate_with_tools
    extract = extract_fn or extract_trip_spec

    extracted = spec
    if extracted is None:
        emit({"type": "status", "message": "Reading the trip request…"})
        extracted = extract(prompt)
    if not isinstance(extracted, TripSpec):
        message = extracted.get("message") or "Could not understand the trip request."
        if trace:
            print(f"[agent] extract failed: {extracted.get('error')}")
        emit({"type": "error", "message": message})
        return AgentResult(text=message)

    emit({"type": "spec", "spec": extracted.model_dump()})
    user = (
        f"User request:\n{prompt}\n\n"
        "Validated trip spec (use this for tool arguments; do not add legs or stays):\n"
        f"{extracted.model_dump_json()}\n"
    )
    history = [user_text(user)]
    steps: list[dict[str, Any]] = []

    for _ in range(MAX_TURNS):
        content = generate(history, system=SYSTEM, declarations=DECLARATIONS)
        history.append(content)
        calls = [part for part in (content.parts or []) if getattr(part, "function_call", None)]
        if not calls:
            text = text_from_content(content)
            emit({"type": "text", "text": text})
            return AgentResult(text=text, steps=steps, spec=extracted)
        results = []
        for part in calls:
            call = part.function_call
            args = dict(call.args or {})
            if trace:
                print(f"[agent] {call.name}({args})")
            emit({"type": "tool", "name": call.name, "args": args})
            result = run_tool(call.name, args)
            results.append((call.name, result))
            step = _step_record(call.name, args, result)
            steps.append(step)
            emit({"type": "tool_result", **step})
        history.append(tool_result_content(results))
    message = "Stopped: too many tool rounds without a final itinerary."
    emit({"type": "error", "message": message})
    return AgentResult(text=message, steps=steps, spec=extracted)
