"""Default product path: extract spec → plan_trip → report. No Gemini tool calls."""

from __future__ import annotations

from .extract import extract_trip_spec
from .planner import plan_trip
from .report import report_plan
from .trip_spec import TripSpec


def run_pipeline(prompt: str, *, trace: bool = True) -> str:
    extracted = extract_trip_spec(prompt)
    if not isinstance(extracted, TripSpec):
        if trace:
            print(f"[pipeline] extract failed: {extracted.get('error')}")
        return extracted.get("message") or "Could not understand the trip request."

    if trace:
        print(f"[pipeline] spec: {extracted.model_dump_json()}")

    plan = plan_trip(extracted)
    if trace:
        print(
            f"[pipeline] plan ok={plan.get('ok')} error={plan.get('error')} "
            f"total={plan.get('total')} remaining={plan.get('remaining')}"
        )

    return report_plan(plan, extracted)
