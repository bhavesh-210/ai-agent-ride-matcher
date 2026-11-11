"""One pickup policy value, shared by the CLI, API and graph."""
import os
import json
from pathlib import Path
from pydantic import Field
from .models import StrictModel


POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "matching.json"


def project_extra_pickup_minutes():
    return json.loads(POLICY_PATH.read_text())["accepted_extra_pickup_minutes"]


class MatchingConfig(StrictModel):
    # Relative to the fastest available driver with a supplied route.
    accepted_extra_pickup_minutes: float = Field(default_factory=project_extra_pickup_minutes, ge=0, validate_default=True)

    @classmethod
    def from_env(cls):
        override = os.getenv("ACCEPTED_EXTRA_PICKUP_MINUTES")
        return cls() if override is None else cls(accepted_extra_pickup_minutes=override)
