"""Offline contract tests: no OpenRouter credentials or network needed."""
from itertools import permutations
from pathlib import Path

import pytest
from pydantic import ValidationError
from ride_matcher.config import MatchingConfig
from ride_matcher.datasets import load_requests, load_drivers
from ride_matcher.graph import run_match, build_graph
from ride_matcher.models import AgentState, ModelDecision


def make_state():
    drivers = []
    for driver_id, status, eta, distance in [
        ("fast", "available", 4, 1.14),
        ("boundary", "available", 6, 2),
        ("beyond", "available", 6.01, 2),
        ("bridge", "available", 16, 1.03),
        ("busy", "on_trip", 0, 0.1),
        ("offline", "offline", 0, 0.1),
        ("no-route", "available", None, 0.1),
    ]:
        drivers.append(dict(request_id="r", driver_id=driver_id, status=status,
                            actual_pickup_time_minutes=eta, straight_line_distance_km=distance,
                            coordinates=dict(lat=0, lon=0)))
    return AgentState(request=dict(request_id="r", rider_id="u",
                                   pickup_coordinates=dict(lat=0, lon=0)), all_candidates=drivers)


@pytest.mark.parametrize("extra,expected", [(0, {"fast"}), (2, {"fast", "boundary"})])
def test_policy_filters_before_provider_and_audits_every_original(extra, expected):
    state = make_state()
    before = state.model_dump_json()
    calls = []
    def provider(request, candidates):
        calls.append({d.driver_id for d in candidates})
        return ModelDecision(selected_driver_id="bridge", estimated_pickup_time_minutes=16,
                             decision_rationale="Closer on map"), None
    result = run_match(state, provider, MatchingConfig(accepted_extra_pickup_minutes=extra))
    assert calls == [expected]
    assert {d.driver_id for d in result.eligible_candidates} == expected
    assert state.model_dump_json() == before
    match = result.final_match
    assert match.selected_driver_id == "fast"
    assert match.estimated_pickup_time_minutes == 4
    assert match.verification == "model_overridden_by_eta_guard"
    assert match.accepted_extra_pickup_minutes == extra
    assert len(match.evaluated_candidates) == len(state.all_candidates)
    for audit in match.evaluated_candidates:
        if audit.driver_id not in expected:
            assert audit.outcome == "excluded"


@pytest.mark.parametrize("driver_id,eta", [("busy", 0), ("offline", 0), ("boundary", 6), ("invented", 1)])
def test_even_wider_shortlist_cannot_weaken_fastest_guard(driver_id, eta):
    def provider(*args):
        return ModelDecision(selected_driver_id=driver_id, estimated_pickup_time_minutes=eta,
                             decision_rationale="Untrusted proposal"), None
    match = run_match(make_state(), provider, MatchingConfig(accepted_extra_pickup_minutes=20)).final_match
    assert match.selected_driver_id == "fast"
    assert match.model_proposal.selected_driver_id == driver_id
    assert match.verification == "model_overridden_by_eta_guard"


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), "bad"])
def test_invalid_config_fails_closed(value):
    with pytest.raises(ValidationError):
        MatchingConfig(accepted_extra_pickup_minutes=value)


def test_environment_config_is_used_by_graph(monkeypatch):
    monkeypatch.setenv("ACCEPTED_EXTRA_PICKUP_MINUTES", "2")
    result = run_match(make_state())
    assert {d.driver_id for d in result.eligible_candidates} == {"fast", "boundary"}
    assert result.final_match.accepted_extra_pickup_minutes == 2
    assert set(build_graph().nodes) == {"__start__", "filter_available_drivers", "match_fastest_driver"}


def test_zero_eta_tie_is_independent_of_input_order():
    state = make_state()
    drivers = [d.model_copy(update={"actual_pickup_time_minutes": 0})
               for d in state.all_candidates[:3]]
    for order in permutations(drivers):
        result = run_match(AgentState(request=state.request, all_candidates=order), config=MatchingConfig())
        assert result.final_match.selected_driver_id == "beyond"
        assert result.final_match.estimated_pickup_time_minutes == 0


def test_actual_bridge_snapshot_rejects_slow_proposal_before_and_after_model():
    root = Path(__file__).resolve().parents[1] / "data/source"
    requests = load_requests(root / "requests.csv")
    drivers = load_drivers(root / "drivers.csv")
    request = next(r for r in requests if r.request_id == "RQ-0303-002")
    candidates = tuple(d for d in drivers if d.request_id == request.request_id)
    by_id = {d.driver_id: d for d in candidates}
    assert by_id["DRV-16643"].status == "available"
    assert by_id["DRV-16643"].actual_pickup_time_minutes == 4
    assert by_id["DRV-52907"].actual_pickup_time_minutes == 16
    calls = []
    def provider(request, eligible):
        calls.append([d.driver_id for d in eligible])
        return ModelDecision(selected_driver_id="DRV-52907", estimated_pickup_time_minutes=16,
                             decision_rationale="Looks closest"), None
    result = run_match(AgentState(request=request, all_candidates=candidates), provider, MatchingConfig())
    assert calls == [["DRV-16643"]]
    assert result.final_match.selected_driver_id == "DRV-16643"
    assert result.final_match.estimated_pickup_time_minutes == 4
    assert result.final_match.verification == "model_overridden_by_eta_guard"
