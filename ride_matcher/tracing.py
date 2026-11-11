"""Langfuse SDK observations; local exports are never called hosted traces."""
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
import os
import re
from uuid import uuid4


class NoObservation:
    def update(self, **kwargs):
        pass


def observation(tracer, name, **kwargs):
    return tracer.observe(name, **kwargs) if tracer else nullcontext(NoObservation())


def candidate_input(driver):
    # Enough to audit/replay the decision; no rider identity or GPS coordinates.
    return {"driver_id": driver.driver_id, "status": driver.status,
            "straight_line_distance_km": driver.straight_line_distance_km,
            "road_pickup_minutes": driver.actual_pickup_time_minutes,
            "route_note": driver.route_note}


def decision_output(result, *, latency_ms=None):
    match = result.final_match
    call = match.model_call
    status = ("completed" if call else "failed" if result.error else
              "skipped_no_eligible_candidates" if match.verification == "no_candidates" else "skipped_offline")
    return {"request_id": result.request.request_id,
            "selected_driver_id": match.selected_driver_id,
            "estimated_pickup_time_minutes": match.estimated_pickup_time_minutes,
            "decision_rationale": match.decision_rationale,
            "verification": match.verification,
            "accepted_extra_pickup_minutes": match.accepted_extra_pickup_minutes,
            "evaluated_candidates": [a.model_dump(mode="json") for a in match.evaluated_candidates],
            "model_proposal": match.model_proposal.model_dump(mode="json") if match.model_proposal else None,
            "model": call.returned_model if call else None,
            "tokens": call.tokens.model_dump() if call and call.tokens else None,
            "model_rationale": match.model_proposal.decision_rationale if match.model_proposal else None,
            "generation_id": call.generation_id if call else None,
            "latency_ms": latency_ms,
            "model_latency_ms": call.latency_ms if call else None,
            "model_call_status": status,
            "error": result.error}


@dataclass
class RideTracer:
    client: object
    source_commit: str
    session_id: str
    provider_mode: str
    input_hashes: dict

    def __post_init__(self):
        if not re.fullmatch(r"[0-9a-f]{40}", self.source_commit):
            raise ValueError("Tracing requires a full source commit SHA")
        self.trace_ids = []

    @classmethod
    def from_env(cls, *, source_commit, session_id, provider_mode, input_hashes):
        from langfuse import Langfuse
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.sampling import ALWAYS_ON
        if not all(os.getenv(k) for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")):
            raise ValueError("Set LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_BASE_URL privately")
        if os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower() == "false":
            raise ValueError("Langfuse tracing is disabled")
        if os.getenv("OTEL_SDK_DISABLED", "false").lower() == "true":
            raise ValueError("OpenTelemetry tracing is disabled")
        # One trace for every request: do not inherit a host's sampling fraction.
        client = Langfuse(tracer_provider=TracerProvider(sampler=ALWAYS_ON),
                          environment="assignment", release=source_commit)
        if not client.auth_check():
            raise ValueError("Langfuse authentication failed")
        return cls(client, source_commit, session_id, provider_mode, input_hashes)

    @contextmanager
    def observe(self, name, **kwargs):
        error = None
        with self.client.start_as_current_observation(name=name, **kwargs) as span:
            try:
                yield span
            except Exception as exc:
                # Do not let the SDK capture raw provider errors containing secrets.
                span.update(level="ERROR", status_message=type(exc).__name__)
                error = exc
        if error is not None:
            raise error

    @contextmanager
    def ride(self, state, config):
        from langfuse import propagate_attributes
        from opentelemetry import context
        # A ride is a new root, even when the caller has an active trace.
        token = context.attach(context.Context())
        metadata = {"request_id": state.request.request_id, "stage": "stage-3-tracing",
                    "source_commit": self.source_commit, "provider_mode": self.provider_mode,
                    "accepted_extra_pickup_minutes": config.accepted_extra_pickup_minutes,
                    "dataset_sha256": self.input_hashes}
        try:
            with propagate_attributes(session_id=self.session_id, trace_name="ride.match",
                                      tags=["ride-matcher", "stage-3", self.provider_mode],
                                      metadata={"request_id": state.request.request_id, "source_commit": self.source_commit}):
                with self.observe("ride.match", as_type="agent", version=self.source_commit,
                                  metadata=metadata,
                                  input={"request_id": state.request.request_id,
                                         "candidates": [candidate_input(d) for d in state.all_candidates]}) as root:
                    self.trace_ids.append({"request_id":state.request.request_id, "trace_id":root.trace_id})
                    yield root
        finally:
            context.detach(token)


def local_tracer(*, source_commit, session_id, provider_mode, input_hashes):
    """Real Langfuse SDK with an in-memory OTEL exporter; NO hosted upload."""
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.sampling import ALWAYS_ON
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    exporter = InMemorySpanExporter()
    client = Langfuse(public_key="pk-lf-local-"+str(uuid4()), secret_key="local-unused",
                      base_url="http://localhost:1", tracer_provider=TracerProvider(sampler=ALWAYS_ON),
                      span_exporter=exporter, environment="local-test", release=source_commit)
    return RideTracer(client, source_commit, session_id, provider_mode, input_hashes), exporter
