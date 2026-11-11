from langgraph.graph import StateGraph, START, END
from .models import AgentState, CandidateAudit, MatchResult
from .config import MatchingConfig


def filter_available_drivers(state: AgentState, config: MatchingConfig | None = None):
    """New validated state updates; never mutate incoming state."""
    config = config if config is not None else MatchingConfig.from_env()
    routable = tuple(d for d in state.all_candidates if d.status == "available"
                     and d.actual_pickup_time_minutes is not None)
    fastest = min((d.actual_pickup_time_minutes for d in routable), default=None)
    eligible = tuple(d for d in routable
                     if d.actual_pickup_time_minutes - fastest <= config.accepted_extra_pickup_minutes)
    updated = AgentState.model_validate({**state.model_dump(), "eligible_candidates": eligible})
    return {"eligible_candidates": updated.eligible_candidates}


def build_graph(provider=None, config: MatchingConfig | None = None):
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
                    proposal, call = provider(state.request, routable)
                    valid = (proposal.selected_driver_id == winner.driver_id and
                             proposal.estimated_pickup_time_minutes == winner.actual_pickup_time_minutes)
                    verification = "model_verified" if valid else "model_overridden_by_eta_guard"
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

    graph = StateGraph(AgentState)
    graph.add_node("filter_available_drivers", lambda state: filter_available_drivers(state, config))
    graph.add_node("match_fastest_driver", match_fastest_driver)
    graph.add_edge(START, "filter_available_drivers")
    graph.add_edge("filter_available_drivers", "match_fastest_driver")
    graph.add_edge("match_fastest_driver", END)
    return graph.compile()


def run_match(state: AgentState, provider=None, config: MatchingConfig | None = None):
    # LangGraph output is a dict; explicitly validate final boundaries too.
    return AgentState.model_validate(build_graph(provider, config).invoke(state))
