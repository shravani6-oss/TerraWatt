"""Pydantic request models: every body is validated and normalised before touching the database."""
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .security import validate_password_strength

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 254 or not EMAIL_RE.match(v):
        raise ValueError("Enter a valid email address.")
    return v


class RegisterIn(_Base):
    name: str = Field(min_length=2, max_length=60)
    email: str
    password: str
    home_country: Optional[str] = None
    _e = field_validator("email")(_email)
    _p = field_validator("password")(validate_password_strength)


class LoginIn(_Base):
    email: str
    password: str = Field(min_length=1, max_length=128)
    _e = field_validator("email")(_email)


class PasswordIn(_Base):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str
    _p = field_validator("new_password")(validate_password_strength)


class ProfileIn(_Base):
    name: Optional[str] = Field(default=None, min_length=2, max_length=60)
    home_country: Optional[str] = None


class PredictIn(_Base):
    country: str
    overrides: dict[str, float] = Field(default_factory=dict)
    mix: dict[str, float] = Field(default_factory=dict)
    access_gap_pct: Optional[float] = Field(default=None, ge=0, le=100)

    @field_validator("overrides", "mix")
    @classmethod
    def _finite(cls, v):
        import math
        for k, x in v.items():
            if not math.isfinite(x):
                raise ValueError(f"{k} must be a finite number")
        return v


class FootprintIn(_Base):
    """Advanced mode: exact physical quantities."""
    mode: Literal["advanced"] = "advanced"
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    country: str
    household_size: int = Field(default=1, ge=1, le=20)
    lpg_kg: float = Field(default=0, ge=0, le=2000)
    electricity_kwh: float = Field(default=0, ge=0, le=100000)
    gas_m3: float = Field(default=0, ge=0, le=50000)
    car_km: float = Field(default=0, ge=0, le=100000)
    flight_km: float = Field(default=0, ge=0, le=500000)
    renewable_pct: float = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def _something(self):
        if self.electricity_kwh + self.gas_m3 + self.car_km + self.flight_km + self.lpg_kg == 0:
            raise ValueError("Enter at least one non-zero activity.")
        return self


class AlertRuleIn(_Base):
    country: str
    metric: str
    condition: Literal["below", "above", "yoy_drop", "forecast_below"]
    threshold: float = Field(ge=-1e9, le=1e9)
    year: Optional[int] = Field(default=None, ge=2000, le=2060)

    @model_validator(mode="after")
    def _year(self):
        if self.condition == "forecast_below" and not self.year:
            raise ValueError("A target year is required for forecast alerts.")
        if self.condition == "yoy_drop" and self.threshold <= 0:
            raise ValueError("Drop threshold must be positive.")
        return self


class WatchIn(_Base):
    country: str


class AdminUserPatch(_Base):
    role: Optional[Literal["user", "admin"]] = None
    is_active: Optional[bool] = None


class _Electricity(_Base):
    kwh: Optional[float] = Field(default=None, ge=0, le=100000)
    bill_inr: Optional[float] = Field(default=None, ge=0, le=1000000)
    tariff_inr_per_kwh: Optional[float] = Field(default=None, gt=0, le=50)
    renewable_pct: float = Field(default=0, ge=0, le=100)


class _Cooking(_Base):
    type: Optional[Literal["lpg_14kg", "lpg_5kg", "piped", "none"]] = None
    per_month: float = Field(default=0, ge=0, le=100)          # cylinders per month (can be 0.7) or piped-gas m3
    exact: bool = False


class _Vehicle(_Base):
    type: Literal["none", "motorcycle", "scooter", "petrol_car", "diesel_car", "cng_car", "ev_car", "ev_two_wheeler"]
    km_per_month: float = Field(default=0, ge=0, le=20000)


class _Transit(_Base):
    bus_km: float = Field(default=0, ge=0, le=20000)
    train_km: float = Field(default=0, ge=0, le=20000)
    metro_km: float = Field(default=0, ge=0, le=20000)
    cab_km: float = Field(default=0, ge=0, le=20000)


class _Flights(_Base):
    frequency: Optional[Literal["never", "occasionally", "frequently"]] = None
    pkm_per_year: Optional[float] = Field(default=None, ge=0, le=500000)


class _Other(_Base):
    generator_hours: float = Field(default=0, ge=0, le=744)


class HouseholdIn(_Base):
    """Simple mode: everyday questions. Every section is optional (skip what does not apply)."""
    mode: Literal["simple"] = "simple"
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    country: str = "India"
    household_size: int = Field(default=1, ge=1, le=20)
    electricity: Optional[_Electricity] = None
    cooking: Optional[_Cooking] = None
    vehicles: list[_Vehicle] = Field(default_factory=list, max_length=4)
    transit: Optional[_Transit] = None
    flights: Optional[_Flights] = None
    other: Optional[_Other] = None


class GoalIn(_Base):
    kind: Literal["percent", "absolute"]
    percent: Optional[float] = Field(default=None, gt=0, le=90)
    target_kg: Optional[float] = Field(default=None, gt=0, le=1000000)
    baseline_period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")

    @model_validator(mode="after")
    def _one(self):
        if self.kind == "percent" and self.percent is None:
            raise ValueError("Choose a reduction percentage.")
        if self.kind == "absolute" and self.target_kg is None:
            raise ValueError("Enter a monthly emissions goal in kg CO₂e.")
        return self
