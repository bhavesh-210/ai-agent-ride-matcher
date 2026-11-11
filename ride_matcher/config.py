"""One pickup policy value, shared by the CLI, API and graph."""
import os
from pydantic import Field
from .models import StrictModel


class MatchingConfig(StrictModel):
    # Relative to the fastest available driver with a supplied route.
    accepted_extra_pickup_minutes: float = Field(default=0, ge=0)

    @classmethod
    def from_env(cls):
        return cls(accepted_extra_pickup_minutes=os.getenv("ACCEPTED_EXTRA_PICKUP_MINUTES", "0"))
