"""In-memory confirm / edit sessions for the chat agent."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .agent import AgentResult, GenerateFn, OnEvent, run_agent
from .extract import extract_trip_spec, patch_trip_spec
from .trip_spec import TripSpec

CONFIRM_HINT = (
    "\n\nReply **confirm** to lock this plan, or say what to change "
    "(people, dates, a different flight, another hotel)."
)

_CONFIRM_RE = re.compile(
    r"^(confirm|yes|y|ok|okay|looks good|sounds good|perfect|go ahead|lock it in|that works)\.?$",
    re.I,
)


def is_confirm(text: str) -> bool:
    cleaned = re.sub(r"[^a-z\s]", "", text.strip().lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return bool(_CONFIRM_RE.match(cleaned))


@dataclass
class SessionState:
    status: str = "new"
    spec: TripSpec | None = None
    pending_prompt: str = ""
    last_text: str = ""
    last_steps: list[dict[str, Any]] = field(default_factory=list)


SESSIONS: dict[str, SessionState] = {}


@dataclass
class ChatTurn:
    session_id: str
    text: str
    steps: list[dict[str, Any]]
    status: str


def _emit(on_event: OnEvent | None, payload: dict[str, Any]) -> None:
    if on_event:
        on_event(payload)


def run_turn(
    prompt: str,
    session_id: str | None = None,
    *,
    trace: bool = False,
    on_event: OnEvent | None = None,
    generate_fn: GenerateFn | None = None,
    extract_fn: Callable[[str], TripSpec | dict] | None = None,
    patch_fn: Callable[[TripSpec, str], TripSpec | dict] | None = None,
) -> ChatTurn:
    sid = session_id or uuid.uuid4().hex[:12]
    state = SESSIONS.get(sid) or SessionState()
    extract = extract_fn or extract_trip_spec
    patch = patch_fn or patch_trip_spec

    if state.status == "proposed" and is_confirm(prompt):
        state.status = "confirmed"
        SESSIONS[sid] = state
        text = "Confirmed. This plan is locked. Send a new trip request whenever you want to start over."
        _emit(on_event, {"type": "text", "text": text})
        _emit(on_event, {"type": "done", "status": state.status, "session_id": sid})
        return ChatTurn(session_id=sid, text=text, steps=[], status=state.status)

    spec: TripSpec | None = None
    work_prompt = prompt

    if state.status == "proposed" and state.spec is not None:
        _emit(on_event, {"type": "status", "message": "Updating the trip…"})
        patched = patch(state.spec, prompt)
        if not isinstance(patched, TripSpec):
            message = patched.get("message") or "Could not apply that change."
            _emit(on_event, {"type": "error", "message": message})
            _emit(on_event, {"type": "done", "status": state.status, "session_id": sid})
            return ChatTurn(session_id=sid, text=message, steps=[], status=state.status)
        spec = patched
        work_prompt = f"{prompt}\n(Updated from the previous confirmed-pending plan.)"
    elif state.status == "incomplete" and state.pending_prompt:
        work_prompt = f"{state.pending_prompt}\n{prompt}"

    result: AgentResult = run_agent(
        work_prompt,
        spec=spec,
        trace=trace,
        on_event=on_event,
        generate_fn=generate_fn,
        extract_fn=extract if spec is None else (lambda _p: spec),
    )

    if result.spec is None:
        state.status = "incomplete"
        state.pending_prompt = work_prompt
        state.last_text = result.text
        state.last_steps = result.steps
        SESSIONS[sid] = state
        _emit(on_event, {"type": "done", "status": state.status, "session_id": sid})
        return ChatTurn(
            session_id=sid,
            text=result.text,
            steps=result.steps,
            status=state.status,
        )

    text = result.text + CONFIRM_HINT
    state.status = "proposed"
    state.spec = result.spec
    state.pending_prompt = ""
    state.last_text = text
    state.last_steps = result.steps
    SESSIONS[sid] = state
    _emit(on_event, {"type": "text", "text": CONFIRM_HINT.strip(), "append": True})
    _emit(on_event, {"type": "done", "status": state.status, "session_id": sid})
    return ChatTurn(session_id=sid, text=text, steps=result.steps, status=state.status)
