"""No Gemini. Checks that prompt leftovers fill stars, amenities, and afternoon."""

from app.extract import _enrich_from_prompt
from app.trip_spec import TripSpec


PROMPT = (
    "2 adults economy Hyderabad to Munich on 2026-06-15, stay 3 nights. "
    "3-star or better hotel with complementary breakfast and a gym. "
    "Afternoon departure. Budget 4000 USD, strictly within budget. No return."
)


def test_enrich_fills_dropped_hotel_and_flight_filters() -> None:
    raw = {
        "passengers": 2,
        "cabin": "economy",
        "budget_cap": 4000,
        "hotel": {"min_stars": 1, "amenities": []},
        "flight": {},
        "stays": [{"city": "munich", "nights": 3, "check_in": "2026-06-15"}],
        "legs": [{"origin": "HYD", "destination": "MUC", "date": "2026-06-15"}],
    }
    spec = TripSpec.model_validate(_enrich_from_prompt(raw, PROMPT))
    assert spec.hotel.min_stars == 3
    assert "breakfast" in spec.hotel.amenities
    assert "gym" in spec.hotel.amenities
    assert spec.flight.time_of_day == "afternoon"
    assert spec.overage_allowed == 0
    assert len(spec.legs) == 1
