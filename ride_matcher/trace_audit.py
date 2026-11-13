"""Validate exported trace fields and consistency; explicit null is not absence."""
import json
import math

REQUIRED_OUTPUT_FIELDS = (
    "request_id", "selected_driver_id", "estimated_pickup_time_minutes", "decision_rationale",
    "evaluated_candidates", "model", "tokens", "latency_ms", "model_rationale", "error", "model_call_status",
)


def finite_nonnegative(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def decode(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def valid_tokens(value):
    return (isinstance(value, dict) and all(type(value.get(k)) is int and value[k] >= 0
            for k in ("input", "output", "total"))
            and value["input"] + value["output"] == value["total"])


def audit_trace_fields(export):
    missing, incomplete, skipped = [], [], []
    called = 0
    seen_ids = set()
    for trace in export["traces"]:
        output = trace.get("output") or {}
        absent = ["output."+field for field in REQUIRED_OUTPUT_FIELDS if field not in output]
        absent += [field for field in ("trace_id", "request_id", "input", "observations") if field not in trace]
        if not finite_nonnegative(output.get("latency_ms")) and "output.latency_ms" not in absent:
            absent.append("output.latency_ms value")
        if absent:
            missing.append({"request_id": trace.get("request_id"), "trace_id": trace.get("trace_id"), "missing": absent})
        invalid = []
        if trace.get("trace_id") in seen_ids:
            invalid.append("duplicate trace_id")
        seen_ids.add(trace.get("trace_id"))
        if output.get("request_id") != trace.get("request_id"):
            invalid.append("output.request_id mismatch")
        source = trace.get("input") or {}
        if source.get("request_id", trace.get("request_id")) != trace.get("request_id"):
            invalid.append("input.request_id mismatch")
        candidates = source.get("candidates")
        winner = None
        if candidates is not None:
            routable = [d for d in candidates if d.get("status") == "available"
                        and finite_nonnegative(d.get("road_pickup_minutes"))]
            winner = min(routable, key=lambda d: (d["road_pickup_minutes"], d["driver_id"]), default=None)
            if (output.get("selected_driver_id") != (winner["driver_id"] if winner else None)
                    or output.get("estimated_pickup_time_minutes") != (winner["road_pickup_minutes"] if winner else None)):
                invalid.append("selection does not match available minimum road ETA")
        status = output.get("model_call_status")
        generations = [r for r in trace.get("observations", []) if r.get("name") == "openrouter.match"]
        if status == "skipped_no_eligible_candidates":
            skipped.append({"request_id": trace.get("request_id"), "reason": status})
            if any(output.get(k) is not None for k in ("model", "tokens", "model_rationale", "generation_id", "model_latency_ms")):
                invalid.append("invented model data for skipped call")
            if generations or output.get("selected_driver_id") is not None or output.get("estimated_pickup_time_minutes") is not None or winner:
                invalid.append("skipped call has candidates, selection or generation")
        elif export["_evidence"]["provider_mode"] == "openrouter":
            called += 1
            if status != "completed":
                invalid.append("model_call_status")
            for field in ("model", "tokens", "model_rationale", "generation_id", "model_latency_ms"):
                if output.get(field) is None or output.get(field) == "":
                    invalid.append(field)
            if not finite_nonnegative(output.get("model_latency_ms")):
                invalid.append("model_latency_ms value")
            tokens = output.get("tokens")
            if not valid_tokens(tokens):
                invalid.append("tokens.input/output/total")
            if len(generations) != 1:
                invalid.append("generation_observation")
            else:
                generation = generations[0]
                attrs = generation.get("attributes") or {}
                native_model = (generation.get("providedModelName") or generation.get("model")
                                or attrs.get("langfuse.observation.model.name"))
                native_usage = decode(generation.get("usageDetails") or attrs.get("langfuse.observation.usage_details"))
                if not native_model:
                    invalid.append("generation.model")
                elif native_model != output.get("model"):
                    invalid.append("generation.model mismatch")
                if not valid_tokens(native_usage):
                    invalid.append("generation.usageDetails")
                elif native_usage != tokens:
                    invalid.append("generation.usageDetails mismatch")
                proposal = decode(generation.get("output"))
                if not isinstance(proposal, dict):
                    invalid.append("generation.output")
                elif proposal.get("decision_rationale") != output.get("model_rationale"):
                    invalid.append("generation.rationale mismatch")
                if isinstance(proposal, dict) and output.get("verification") == "model_verified":
                    if any(proposal.get(k) != output.get(k) for k in
                           ("selected_driver_id", "estimated_pickup_time_minutes")):
                        invalid.append("verified generation.selection mismatch")
            if output.get("error") is not None:
                invalid.append("error")
            if output.get("verification") != "model_verified":
                invalid.append("verification")
        if invalid:
            incomplete.append({"request_id": trace.get("request_id"), "trace_id": trace.get("trace_id"), "invalid": invalid})
    return {"_evidence": export["_evidence"], "required_output_fields": list(REQUIRED_OUTPUT_FIELDS),
            "trace_count": len(export["traces"]), "missing_required_fields": missing,
            "traces_missing_required_field_count": len(missing), "incomplete_model_traces": incomplete,
            "model_call_trace_count": called, "skipped_no_eligible_candidates": skipped,
            "null_error_is_valid": True}
