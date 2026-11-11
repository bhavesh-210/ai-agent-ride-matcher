"""Deterministic snapshot tools, executed by Node 1 before OpenRouter."""
from .config import MatchingConfig
from .models import Driver


def check_availability(driver: Driver) -> bool:
    """Only the snapshot's available status permits dispatch."""
    return driver.status == "available"


def estimate_pickup_time(driver: Driver) -> float | None:
    """Read validated supplied road minutes; never infer time from distance."""
    return driver.actual_pickup_time_minutes


def check_eligibility(*, available: bool, pickup_minutes: float | None,
                      fastest_minutes: float | None, config: MatchingConfig) -> bool:
    """An inclusive extra-time allowance relative to the fastest available route."""
    return (available and pickup_minutes is not None and fastest_minutes is not None
            and pickup_minutes - fastest_minutes <= config.accepted_extra_pickup_minutes)
