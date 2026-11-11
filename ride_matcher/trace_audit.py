"""Check required fields on exported server observations without confusing null with absent."""
REQUIRED_OUTPUT_FIELDS = (
    "request_id", "selected_driver_id", "estimated_pickup_time_minutes", "decision_rationale",
    "evaluated_candidates", "model", "tokens", "latency_ms", "model_rationale", "error", "model_call_status",
)


def audit_trace_fields(export):
    missing = []
    incomplete = []
    called = 0
    skipped = []
    for trace in export["traces"]:
        output = trace.get("output") or {}
        absent = ["output."+field for field in REQUIRED_OUTPUT_FIELDS if field not in output]
        for field in ("trace_id", "request_id", "input", "observations"):
            if field not in trace:
                absent.append(field)
        if absent:
            missing.append({"request_id":trace.get("request_id"),"trace_id":trace.get("trace_id"),"missing":absent})
        status=output.get("model_call_status")
        if status=="skipped_no_eligible_candidates":
            skipped.append({"request_id":trace["request_id"],"reason":status})
            if any(output.get(k) is not None for k in ("model","tokens","model_rationale")):
                incomplete.append({"request_id":trace["request_id"],"invalid":["invented model data for skipped call"]})
        elif export["_evidence"]["provider_mode"]=="openrouter":
            called+=1
            invalid=[]
            if status!="completed": invalid.append("model_call_status")
            for field in ("model","tokens","model_rationale","generation_id","model_latency_ms"):
                if output.get(field) is None or output.get(field)=="": invalid.append(field)
            tokens=output.get("tokens")
            if not isinstance(tokens,dict) or any(not isinstance(tokens.get(k),int) or tokens[k]<0 for k in ("input","output","total")):
                invalid.append("tokens.input/output/total")
            generations=[r for r in trace.get("observations",[]) if r.get("name")=="openrouter.match"]
            if len(generations)!=1: invalid.append("generation_observation")
            else:
                generation=generations[0]
                # Langfuse v2 returns native model/usage columns, not only root copies.
                if "attributes" not in generation:
                    if not (generation.get("providedModelName") or generation.get("model")): invalid.append("generation.model")
                    if not generation.get("usageDetails"): invalid.append("generation.usageDetails")
                if generation.get("output") is None: invalid.append("generation.output")
            if output.get("error") is not None: invalid.append("error")
            if output.get("verification")!="model_verified": invalid.append("verification")
            if invalid: incomplete.append({"request_id":trace["request_id"],"trace_id":trace["trace_id"],"invalid":invalid})
        if output.get("latency_ms") is None or output.get("latency_ms",-1)<0:
            if not absent: missing.append({"request_id":trace["request_id"],"trace_id":trace["trace_id"],"missing":["output.latency_ms value"]})
    return {"_evidence":export["_evidence"],"required_output_fields":list(REQUIRED_OUTPUT_FIELDS),
            "trace_count":len(export["traces"]),"missing_required_fields":missing,
            "traces_missing_required_field_count":len(missing),"incomplete_model_traces":incomplete,
            "model_call_trace_count":called,"skipped_no_eligible_candidates":skipped,
            "null_error_is_valid":True}
