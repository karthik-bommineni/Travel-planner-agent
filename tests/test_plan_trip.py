"""Planner evals against catalog.sqlite. No Gemini."""

from __future__ import annotations

from app.planner import _timeline_ok, plan_trip
from app.trip_spec import FlightLeg, Stay, TripSpec


def _hyd_muc(**kwargs) -> TripSpec:
    base = dict(
        passengers=2,
        cabin="economy",
        budget_cap=4000,
        overage_allowed=0,
        hotel={"min_stars": 3, "amenities": ["gym", "breakfast"]},
        flight={"time_of_day": "afternoon"},
        stays=[Stay(city="munich", nights=3, check_in="2026-06-15")],
        legs=[FlightLeg(origin="HYD", destination="MUC", date="2026-06-15")],
    )
    base.update(kwargs)
    return TripSpec.model_validate(base)


def _assert_grounded(plan: dict) -> None:
    total = sum(item["amount"] for item in plan["line_items"])
    assert plan["total"] == total
    for flight in plan.get("flights") or []:
        assert str(flight["offer_id"]).startswith("FLT-")
    for hotel in plan.get("hotels") or []:
        assert str(hotel["hotel_id"]).startswith("HTL-")
        amenities = {str(a).lower() for a in hotel.get("amenities") or []}
        assert hotel.get("rooms_available", 1) >= 1


def test_one_way_under_budget_picks_afternoon_and_gym_breakfast(catalog_path) -> None:
    _ = catalog_path
    plan = plan_trip(_hyd_muc())
    assert plan["ok"] is True
    assert plan["error"] is None
    assert plan["total"] <= 4000
    assert plan["remaining"] == 4000 - plan["total"]
    assert len(plan["flights"]) == 1
    assert len(plan["hotels"]) == 1
    flight = plan["flights"][0]
    assert "12:00" <= flight["depart_time"] < "17:00"
    hotel = plan["hotels"][0]
    amenities = {str(a).lower() for a in hotel["amenities"]}
    assert "gym" in amenities and "breakfast" in amenities
    assert hotel["stars"] >= 3
    assert hotel["hotel_id"] != "HTL-00399"
    _assert_grounded(plan)


def test_over_budget_fails_clearly(catalog_path) -> None:
    _ = catalog_path
    plan = plan_trip(_hyd_muc(budget_cap=50))
    assert plan["ok"] is False
    assert plan["error"] == "over_budget"
    assert plan["total"] > 50
    _assert_grounded(plan)


def test_unknown_amenity_means_no_hotels(catalog_path) -> None:
    _ = catalog_path
    plan = plan_trip(
        _hyd_muc(hotel={"min_stars": 3, "amenities": ["teleporter"]})
    )
    assert plan["ok"] is False
    assert plan["error"] == "no_hotels"


def test_return_leg_is_planned_only_when_listed(catalog_path) -> None:
    _ = catalog_path
    spec = TripSpec(
        passengers=2,
        cabin="economy",
        budget_cap=8000,
        hotel={"min_stars": 3, "amenities": ["gym", "breakfast"]},
        stays=[Stay(city="munich", nights=3, check_in="2026-06-15")],
        legs=[
            FlightLeg(origin="HYD", destination="MUC", date="2026-06-15"),
            FlightLeg(origin="MUC", destination="HYD", date="2026-06-18"),
        ],
    )
    plan = plan_trip(spec)
    assert plan["ok"] is True
    assert len(plan["flights"]) == 2
    assert plan["flights"][0]["destination_airport"] == "MUC"
    assert plan["flights"][1]["origin_airport"] == "MUC"
    assert plan["flights"][1]["destination_airport"] == "HYD"
    assert plan["flights"][1]["depart_date"] == "2026-06-18"
    _assert_grounded(plan)


def test_timeline_rejects_too_early_checkout_departure() -> None:
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
    hotels = [
        {
            "city": "munich",
            "city_name": "Munich",
            "check_out": "11:00",
        }
    ]
    spec = TripSpec(
        budget_cap=4000,
        stays=[Stay(city="munich", nights=3, check_in="2026-06-15")],
        legs=[
            FlightLeg(origin="HYD", destination="MUC", date="2026-06-15"),
            FlightLeg(origin="MUC", destination="HYD", date="2026-06-18"),
        ],
    )
    assert _timeline_ok(spec, flights, hotels) is False
    flights[1]["depart_time"] = "16:00"
    assert _timeline_ok(spec, flights, hotels) is True
