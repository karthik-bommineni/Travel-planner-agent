import pytest
from pydantic import ValidationError

from app.trip_spec import FlightLeg, Stay, TripSpec


def test_one_way_has_no_implied_return() -> None:
    spec = TripSpec(
        passengers=2,
        budget_cap=4000,
        stays=[Stay(city="munich", nights=3, check_in="2026-06-15")],
        legs=[FlightLeg(origin="HYD", destination="MUC", date="2026-06-15")],
    )
    assert spec.has_return_to_origin() is False
    assert len(spec.legs) == 1


def test_return_requires_second_leg() -> None:
    spec = TripSpec(
        passengers=2,
        budget_cap=4000,
        stays=[Stay(city="munich", nights=3, check_in="2026-06-15")],
        legs=[
            FlightLeg(origin="HYD", destination="MUC", date="2026-06-15"),
            FlightLeg(origin="MUC", destination="HYD", date="2026-06-18"),
        ],
    )
    assert spec.has_return_to_origin() is True


def test_rejects_two_stays_with_one_flight() -> None:
    with pytest.raises(ValidationError):
        TripSpec(
            budget_cap=4000,
            stays=[
                Stay(city="munich", nights=2, check_in="2026-06-15"),
                Stay(city="paris", nights=2, check_in="2026-06-17"),
            ],
            legs=[FlightLeg(origin="HYD", destination="MUC", date="2026-06-15")],
        )
