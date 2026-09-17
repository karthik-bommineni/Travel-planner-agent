"""Optional Prometheus metrics. No-ops if prometheus_client is missing."""

from __future__ import annotations

from typing import Any

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
except ImportError:  # pragma: no cover
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    Counter = Histogram = None  # type: ignore
    generate_latest = None  # type: ignore

REQUESTS = (
    Counter("travel_planner_requests_total", "HTTP requests", ["path", "method", "code"])
    if Counter
    else None
)
LATENCY = (
    Histogram("travel_planner_request_seconds", "HTTP latency", ["path"])
    if Histogram
    else None
)
TOOL_CALLS = (
    Counter("travel_planner_tool_calls_total", "Catalog tool calls", ["tool", "ok"])
    if Counter
    else None
)
PLANS = (
    Counter("travel_planner_plans_total", "Chat turns", ["status"])
    if Counter
    else None
)


def observe_request(path: str, method: str, code: int, seconds: float) -> None:
    if REQUESTS is not None:
        REQUESTS.labels(path=path, method=method, code=str(code)).inc()
    if LATENCY is not None:
        LATENCY.labels(path=path).observe(seconds)


def observe_tool(name: str, ok: bool) -> None:
    if TOOL_CALLS is not None:
        TOOL_CALLS.labels(tool=name, ok="true" if ok else "false").inc()


def observe_plan(status: str) -> None:
    if PLANS is not None:
        PLANS.labels(status=status).inc()


def render_metrics() -> tuple[bytes, str]:
    if generate_latest is None:
        return b"prometheus_client not installed\n", "text/plain; charset=utf-8"
    return generate_latest(), CONTENT_TYPE_LATEST
