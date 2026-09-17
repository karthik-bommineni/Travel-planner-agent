from __future__ import annotations

from app.session import SESSIONS, is_confirm, run_turn
from app.tools.registry import run_tool
from app.tools.timeline import evaluate_timeline
from app.trip_spec import FlightLeg, Stay, TripSpec


def _spec(**kwargs) -> TripSpec:
    base = dict(
        passengers=2,
        cabin="economy",
        budget_cap=4000,
        stays=[Stay(city="munich", nights=3, check_in="2026-06-15")],
        legs=[FlightLeg(origin="HYD", destination="MUC", date="2026-06-15")],
    )
    base.update(kwargs)
    return TripSpec.model_validate(base)


class _Part:
    def __init__(self, *, function_call=None, text=None):
        self.function_call = function_call
        self.text = text


class _Content:
    def __init__(self, parts):
        self.parts = parts


def test_is_confirm() -> None:
    assert is_confirm("confirm")
    assert is_confirm("Looks good.")
    assert is_confirm("OK")
    assert not is_confirm("make it 3 people")


def test_stay_hotel_and_leg_overrides() -> None:
    spec = _spec(
        hotel={"min_stars": 2, "amenities": ["wifi"]},
        stays=[
            Stay(
                city="munich",
                nights=3,
                check_in="2026-06-15",
                min_stars=4,
                amenities=["gym"],
            )
        ],
        legs=[
            FlightLeg(
                origin="HYD",
                destination="MUC",
                date="2026-06-15",
                time_of_day="afternoon",
            )
        ],
        flight={"time_of_day": "morning"},
    )
    hotel = spec.stay_hotel(0)
    assert hotel.min_stars == 4
    assert hotel.amenities == ["gym"]
    assert spec.leg_time_of_day(0) == "afternoon"


def test_evaluate_timeline_rejects_early_departure() -> None:
    flights = [
        {
            "arrive_date": "2026-06-15",
            "destination_city": "munich",
            "destination_airport": "MUC",
        },
        {
            "depart_date": "2026-06-18",
            "depart_time": "07:00",
            "origin_city": "munich",
            "origin_airport": "MUC",
        },
    ]
    hotels = [{"city": "munich", "city_name": "Munich", "check_out": "11:00"}]
    ok, reason = evaluate_timeline(
        flights,
        hotels,
        [3],
        ["munich"],
        ["2026-06-15"],
    )
    assert ok is False
    assert reason
    flights[1]["depart_time"] = "16:00"
    ok, _ = evaluate_timeline(flights, hotels, [3], ["munich"], ["2026-06-15"])
    assert ok is True


def test_check_timeline_unknown_id(catalog_path) -> None:
    _ = catalog_path
    result = run_tool(
        "check_timeline",
        {
            "flight_offer_ids": ["FLT-DOES-NOT-EXIST"],
            "hotel_ids": ["HTL-DOES-NOT-EXIST"],
            "nights": [3],
            "stay_cities": ["munich"],
        },
    )
    assert result["ok"] is False
    assert result["error"] in {"unknown_flight", "unknown_hotel"}


def test_session_confirm_and_passenger_edit() -> None:
    SESSIONS.clear()
    spec = _spec()

    def extract(_prompt: str) -> TripSpec:
        return spec

    def generate(history, **_kwargs):
        return _Content(parts=[_Part(text="Plan: HYD to Munich. Total $1616.")])

    first = run_turn("plan munich", extract_fn=extract, generate_fn=generate)
    assert first.status == "proposed"
    assert "confirm" in first.text.lower()

    def patch(current: TripSpec, _edit: str) -> TripSpec:
        return current.model_copy(update={"passengers": 3})

    edited = run_turn(
        "make it 3 people",
        first.session_id,
        patch_fn=patch,
        generate_fn=generate,
    )
    assert edited.status == "proposed"
    assert SESSIONS[first.session_id].spec.passengers == 3

    locked = run_turn("confirm", first.session_id)
    assert locked.status == "confirmed"
    assert "locked" in locked.text.lower()
