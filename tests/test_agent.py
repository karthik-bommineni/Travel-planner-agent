from app.agent import _shortlist_ids, _step_record
from app.tools.registry import SHORTLIST, run_tool


def test_shortlist_ids_from_search_results() -> None:
    ids = _shortlist_ids(
        "search_flights",
        {"flights": [{"offer_id": "FLT-1"}, {"offer_id": "FLT-2"}]},
    )
    assert ids == ["FLT-1", "FLT-2"]
    hotels = _shortlist_ids(
        "search_hotels",
        {"hotels": [{"hotel_id": "HTL-1"}]},
    )
    assert hotels == ["HTL-1"]


def test_step_record_search_ok_without_ok_flag() -> None:
    step = _step_record(
        "search_flights",
        {"origin": "HYD", "destination": "MUC", "date": "2026-06-15"},
        {"flights": [{"offer_id": "FLT-1"}]},
    )
    assert step["ok"] is True
    assert step["shortlist"] == ["FLT-1"]


def test_step_record_over_budget() -> None:
    step = _step_record(
        "score_budget",
        {"passengers": 2},
        {"ok": False, "error": "over_budget", "total": 5000, "remaining": -1000, "line_items": []},
    )
    assert step["ok"] is False
    assert step["error"] == "over_budget"
    assert step["total"] == 5000


def test_unknown_tool_is_rejected() -> None:
    result = run_tool("not_a_tool", {})
    assert result["ok"] is False
    assert result["error"] == "unknown_tool"


def test_agent_search_shortlist_cap() -> None:
    assert SHORTLIST == 5
