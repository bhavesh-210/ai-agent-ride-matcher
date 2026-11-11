from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

class Coordinates(StrictModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)

class Driver(StrictModel):
    request_id: str = Field(min_length=1)
    driver_id: str = Field(min_length=1)
    status: Literal["available", "on_trip", "offline"]
    coordinates: Coordinates
    straight_line_distance_km: float = Field(ge=0)
    # None means no usable route, NOT a zero-minute ETA.
    actual_pickup_time_minutes: float | None = Field(default=None, ge=0)
    route_note: str = ""

class RideRequest(StrictModel):
    request_id: str = Field(min_length=1)
    rider_id: str = Field(min_length=1)
    pickup_coordinates: Coordinates

class CandidateAudit(StrictModel):
    driver_id: str
    status: str
    straight_line_distance_km: float
    road_eta_minutes: float | None
    outcome: Literal["excluded", "selected", "not_selected"]
    reason: str

class ModelDecision(StrictModel):
    selected_driver_id: str
    estimated_pickup_time_minutes: float = Field(ge=0)
    decision_rationale: str = Field(min_length=1)

class ModelCall(StrictModel):
    requested_model: str
    returned_model: str
    generation_id: str
    started_at_utc: str
    finished_at_utc: str
    latency_ms: float
    raw_content: str

class MatchResult(StrictModel):
    accepted_extra_pickup_minutes: float = Field(default=0, ge=0)
    selected_driver_id: str | None = None
    estimated_pickup_time_minutes: float | None = None
    decision_rationale: str
    evaluated_candidates: tuple[CandidateAudit, ...]
    model_call: ModelCall | None = None
    model_proposal: ModelDecision | None = None
    verification: str

class AgentState(StrictModel):
    request: RideRequest
    all_candidates: tuple[Driver, ...]
    eligible_candidates: tuple[Driver, ...] = ()
    final_match: MatchResult | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_candidates(self):
        ids = [d.driver_id for d in self.all_candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate driver IDs within a request")
        if any(d.request_id != self.request.request_id for d in self.all_candidates):
            raise ValueError("Candidate routing data belongs to a different request")
        return self
