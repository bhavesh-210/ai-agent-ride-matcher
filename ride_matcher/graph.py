from langgraph.graph import StateGraph, START, END
import time
from .models import AgentState, CandidateAudit, MatchResult
from .config import MatchingConfig
from . import tools as candidate_tools
from .tracing import observation, candidate_input, decision_output


def filter_available_drivers(state: AgentState, config: MatchingConfig | None = None, tracer=None):
    """New validated state updates; never mutate incoming state."""
    config = config if config is not None else MatchingConfig.from_env()
    checks = []
    for d in state.all_candidates:
        with observation(tracer, "check_availability", as_type="tool", input={"driver_id":d.driver_id,"status":d.status}) as span:
            available = candidate_tools.check_availability(d)
            span.update(output={"available":available})
        with observation(tracer, "estimate_pickup_time", as_type="tool", input={"driver_id":d.driver_id,"route_note":d.route_note}) as span:
            eta = candidate_tools.estimate_pickup_time(d)
            span.update(output={"road_pickup_minutes":eta,"source":"snapshot"})
        checks.append((d, available, eta))
    fastest = min((eta for _, available, eta in checks if available and eta is not None), default=None)
    eligible = []
    for d, available, eta in checks:
        with observation(tracer, "check_eligibility", as_type="tool",
                         input={"driver_id":d.driver_id,"available":available,"road_pickup_minutes":eta,
                                "fastest_minutes":fastest,"accepted_extra_pickup_minutes":config.accepted_extra_pickup_minutes}) as span:
            passes = candidate_tools.check_eligibility(available=available, pickup_minutes=eta,
                                                       fastest_minutes=fastest, config=config)
            span.update(output={"eligible":passes})
        if passes:
            eligible.append(d)
    eligible = tuple(eligible)
    updated = AgentState.model_validate({**state.model_dump(), "eligible_candidates": eligible})
    return {"eligible_candidates": updated.eligible_candidates}


def build_graph(provider=None, config: MatchingConfig | None = None, tracer=None):
    config = config if config is not None else MatchingConfig.from_env()
    def match_fastest_driver(state: AgentState):
        routable = tuple(d for d in state.eligible_candidates
                         if d.actual_pickup_time_minutes is not None)
        winner = min(routable, key=lambda d: (d.actual_pickup_time_minutes, d.driver_id), default=None)
        proposal = call = None
        error = None
        verification = "no_candidates"
        if winner is not None:
            if provider is None:
                verification = "offline_deterministic_demo_no_api_call"
            else:
                try:
                    with observation(tracer, "openrouter.match", as_type="generation",
                                     model=getattr(provider, "model", None),
                                     input=(provider.messages(state.request, routable) if hasattr(provider, "messages") else
                                            {"request_id":state.request.request_id,
                                             "checked_candidates":[candidate_input(d) for d in routable]})) as generation:
                        proposal, call = provider(state.request, routable)
                        generation.update(output=proposal.model_dump(mode="json"),
                                          metadata={"generation_id":call.generation_id if call else None,
                                                    "returned_model":call.returned_model if call else None,
                                                    "client_latency_ms":call.latency_ms if call else None})
                        if call:
                            generation.update(model=call.returned_model,
                                              usage_details=call.tokens.model_dump() if call.tokens else None)
                    with observation(tracer, "validate_model_choice", as_type="guardrail",
                                     input={"proposed_driver_id":proposal.selected_driver_id,
                                            "proposed_eta":proposal.estimated_pickup_time_minutes,
                                            "expected_driver_id":winner.driver_id,
                                            "expected_eta":winner.actual_pickup_time_minutes,
                                            "eligible_driver_ids":[d.driver_id for d in routable]}) as guard:
                        valid = (proposal.selected_driver_id == winner.driver_id and
                                 proposal.estimated_pickup_time_minutes == winner.actual_pickup_time_minutes)
                        verification = "model_verified" if valid else "model_overridden_by_eta_guard"
                        guard.update(output={"accepted":valid,"verification":verification})
                except Exception as exc:
                    # Safe class-only log; avoid leaking credentials or provider payloads.
                    error = f"Model call failed ({type(exc).__name__}); deterministic ETA fallback used"
                    verification = "model_failed_deterministic_fallback"
        audits = []
        for d in state.all_candidates:
            if d.status != "available":
                outcome, reason = "excluded", f"Status {d.status}; removed before model call."
            elif d.actual_pickup_time_minutes is None:
                outcome, reason = "excluded", "Missing road ETA; unavailable route cannot be ranked."
            elif d not in state.eligible_candidates:
                outcome, reason = "excluded", (
                    f"Road ETA exceeds fastest available route by more than the configured "
                    f"{config.accepted_extra_pickup_minutes:g} extra pickup minutes; removed before model call.")
            elif d == winner:
                outcome, reason = "selected", "Lowest road ETA; equal ETA ties use driver_id ascending."
            else:
                outcome = "not_selected"
                reason = (f"Road ETA {d.actual_pickup_time_minutes:g} min versus selected "
                          f"{winner.actual_pickup_time_minutes:g} min; distance does not determine rank.")
                if d.actual_pickup_time_minutes == winner.actual_pickup_time_minutes:
                    reason = "Equal road ETA; lost deterministic driver_id ascending tie-break."
            if d.route_note:
                reason += f" Snapshot route note: {d.route_note}"
            audits.append(CandidateAudit(driver_id=d.driver_id, status=d.status,
                straight_line_distance_km=d.straight_line_distance_km,
                road_eta_minutes=d.actual_pickup_time_minutes, outcome=outcome, reason=reason))
        rationale = (f"Selected {winner.driver_id}: minimum supplied road ETA "
                     f"{winner.actual_pickup_time_minutes:g} minutes among available routable drivers. "
                     "Straight-line distance is not a ranking input. ETA is an estimate from the snapshot."
                     if winner else "No available driver has a usable road ETA; no match made.")
        result = MatchResult(selected_driver_id=winner.driver_id if winner else None,
            estimated_pickup_time_minutes=winner.actual_pickup_time_minutes if winner else None,
            decision_rationale=rationale, evaluated_candidates=tuple(audits),
            model_call=call, model_proposal=proposal, verification=verification,
            accepted_extra_pickup_minutes=config.accepted_extra_pickup_minutes)
        updated = AgentState.model_validate({**state.model_dump(), "final_match": result, "error": error})
        return {"final_match": updated.final_match, "error": updated.error}

    def traced_node(name, function):
        def invoke(state):
            with observation(tracer, name, as_type="chain", input={"request_id":state.request.request_id}) as span:
                update = function(state)
                output = ({"eligible_driver_ids":[d.driver_id for d in update["eligible_candidates"]]}
                          if "eligible_candidates" in update else
                          {"selected_driver_id":update["final_match"].selected_driver_id,
                           "verification":update["final_match"].verification})
                span.update(output=output)
                return update
        return invoke

    graph = StateGraph(AgentState)
    graph.add_node("filter_available_drivers", traced_node("filter_available_drivers", lambda state: filter_available_drivers(state, config, tracer)))
    graph.add_node("match_fastest_driver", traced_node("match_fastest_driver", match_fastest_driver))
    graph.add_edge(START, "filter_available_drivers")
    graph.add_edge("filter_available_drivers", "match_fastest_driver")
    graph.add_edge("match_fastest_driver", END)
    return graph.compile()


def run_match(state: AgentState, provider=None, config: MatchingConfig | None = None, tracer=None):
    # LangGraph output is a dict; explicitly validate final boundaries too.
    config = config if config is not None else MatchingConfig.from_env()
    if tracer is None:
        return AgentState.model_validate(build_graph(provider, config).invoke(state))
    with tracer.ride(state, config) as root:
        started = time.perf_counter()
        result = AgentState.model_validate(build_graph(provider, config, tracer).invoke(state))
        root.update(output=decision_output(result, latency_ms=round((time.perf_counter()-started)*1000, 3)),
                    level="WARNING" if result.final_match.selected_driver_id is None or result.error else "DEFAULT",
                    status_message=result.final_match.verification)
        return result
