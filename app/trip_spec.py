"""Structured trip request. Gemini fills this; Python plans from it.

Flight search (`search_flights`) is already a one-leg lookup. This spec is the
whole trip: one or more legs (return only if listed), stays, hotel prefs, budget.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
Cabin = Literal["economy", "business"]
TimeOfDay = Literal["morning", "afternoon", "night"]
SortBy = Literal["price", "duration"]
YesNo = Literal["yes", "no"]
PricePreference = Literal["cheapest", "most_expensive"]


def _require_iso_date(value: str) -> str:
    raw = value.strip()
    if not DATE_RE.match(raw):
        raise ValueError("date must be YYYY-MM-DD")
    if not raw.startswith("2026-"):
        raise ValueError("v1 dates must be in 2026")
    return raw


class FlightLeg(BaseModel):
    origin: str
    destination: str
    date: str

    @field_validator("origin", "destination")
    @classmethod
    def strip_place(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("origin/destination cannot be empty")
        return text

    @field_validator("date")
    @classmethod
    def date_iso(cls, value: str) -> str:
        return _require_iso_date(value)


class Stay(BaseModel):
    city: str
    nights: int = Field(ge=1, le=30)
    check_in: str | None = None

    @field_validator("city")
    @classmethod
    def strip_city(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("city cannot be empty")
        return text

    @field_validator("check_in")
    @classmethod
    def check_in_iso(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        return _require_iso_date(str(value))


class HotelPrefs(BaseModel):
    min_stars: int = Field(default=1, ge=1, le=5)
    amenities: list[str] = Field(default_factory=list)

    @field_validator("amenities")
    @classmethod
    def norm_amenities(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for item in value:
            key = item.strip().lower()
            if key and key not in out:
                out.append(key)
        return out


class FlightPrefs(BaseModel):
    """Optional filters copied onto every leg in v1. Omit when the user did not ask."""

    time_of_day: TimeOfDay | None = None
    min_price_usd: int | None = Field(default=None, ge=0)
    max_price_usd: int | None = Field(default=None, ge=0)
    sort_by: SortBy = "price"
    is_refundable: YesNo | None = None


class TripSpec(BaseModel):
    """One trip. `legs` is only the hops the user asked for (no implied return)."""

    passengers: int = Field(default=1, ge=1, le=9)
    cabin: Cabin = "economy"
    budget_cap: float | None = Field(default=None, gt=0)
    overage_allowed: float = Field(default=0, ge=0)
    price_preference: PricePreference = "cheapest"
    hotel: HotelPrefs = Field(default_factory=HotelPrefs)
    flight: FlightPrefs = Field(default_factory=FlightPrefs)
    stays: list[Stay] = Field(min_length=1)
    legs: list[FlightLeg] = Field(min_length=1)

    @field_validator("budget_cap", mode="before")
    @classmethod
    def omit_empty_budget(cls, value):
        if value is None or value == "":
            return None
        return value

    @model_validator(mode="after")
    def prices_and_legs(self) -> TripSpec:
        mx = self.flight.max_price_usd
        mn = self.flight.min_price_usd
        if mx is not None and mn is not None and mx < mn:
            raise ValueError("max_price_usd must be >= min_price_usd")
        if self.budget_cap is None and self.overage_allowed:
            raise ValueError("overage_allowed requires a budget_cap")
        for leg in self.legs:
            if leg.origin.lower() == leg.destination.lower():
                raise ValueError("each flight leg must change city/airport")
        n_stays = len(self.stays)
        n_legs = len(self.legs)
        if n_legs < n_stays or n_legs > n_stays + 1:
            raise ValueError(
                "need one inbound flight per stay, plus at most one onward/return hop"
            )
        return self

    @property
    def budget_ceiling(self) -> float | None:
        if self.budget_cap is None:
            return None
        return self.budget_cap + self.overage_allowed

    def has_return_to_origin(self) -> bool:
        """True only if the last hop lands where the first hop started (same token)."""
        if len(self.legs) < 2:
            return False
        return self.legs[0].origin.lower() == self.legs[-1].destination.lower()
