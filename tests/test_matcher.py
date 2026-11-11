import json
from pathlib import Path
import httpx
import pytest
from pydantic import ValidationError
from ride_matcher.models import AgentState, ModelCall, ModelDecision
from ride_matcher.graph import run_match
from ride_matcher.provider import OpenRouterMatcher

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def state():
    return AgentState(request=json.loads((ROOT / "data/requests.example.json").read_text())[0],
                      all_candidates=json.loads((ROOT / "data/drivers.example.json").read_text()))

def fake_call():
    return ModelCall(requested_model="test:free", returned_model="test:free", generation_id="mock-only",
        started_at_utc="2026-01-01T00:00:00Z", finished_at_utc="2026-01-01T00:00:01Z", latency_ms=1000, raw_content="mock")

def test_bridge_and_filter_and_immutability(state):
    before = state.model_dump_json()
    def provider(request, candidates):
        assert {d.driver_id for d in candidates} == {"farther-same-bank"}
        assert all(d.status == "available" for d in candidates)
        return ModelDecision(selected_driver_id="farther-same-bank", estimated_pickup_time_minutes=5,
                             decision_rationale="5 minutes beats 18 minutes"), fake_call()
    result = run_match(state, provider)
    assert state.model_dump_json() == before
    assert result.final_match.selected_driver_id == "farther-same-bank"
    assert result.final_match.estimated_pickup_time_minutes == 5
    assert len(result.final_match.evaluated_candidates) == 4
    assert result.final_match.verification == "model_verified"

@pytest.mark.parametrize("selected,eta", [("busy-nearby",1), ("near-across-river",18), ("farther-same-bank",0), ("invented",2)])
def test_bad_model_cannot_override_eta(state, selected, eta):
    def bad(*args):
        return ModelDecision(selected_driver_id=selected, estimated_pickup_time_minutes=eta,
                             decision_rationale="Wrong proposal"), fake_call()
    result = run_match(state, bad).final_match
    assert result.selected_driver_id == "farther-same-bank"
    assert result.estimated_pickup_time_minutes == 5
    assert result.verification == "model_overridden_by_eta_guard"

@pytest.mark.parametrize("status", ["offline", "on_trip"])
def test_no_available_skips_model(state,status):
    data = state.model_dump()
    for d in data["all_candidates"]: d["status"] = status
    def fail(*args): pytest.fail("Must not call model with no eligible candidates")
    result = run_match(AgentState.model_validate(data), fail)
    assert result.final_match.selected_driver_id is None
    assert result.final_match.model_call is None

def test_missing_route_skips_model(state):
    data = state.model_dump()
    for d in data["all_candidates"]: d["actual_pickup_time_minutes"] = None
    assert run_match(AgentState.model_validate(data)).final_match.selected_driver_id is None

def test_empty(state):
    assert run_match(AgentState(request=state.request, all_candidates=())).final_match.selected_driver_id is None

def test_tie_and_zero(state):
    data = state.model_dump()
    for d in data["all_candidates"]: d["actual_pickup_time_minutes"] = 0
    result = run_match(AgentState.model_validate(data)).final_match
    assert result.selected_driver_id == "farther-same-bank"
    assert result.estimated_pickup_time_minutes == 0

@pytest.mark.parametrize("eta", [-1, float("nan"), float("inf")])
def test_invalid_eta(state,eta):
    data = state.model_dump()
    data["all_candidates"][0]["actual_pickup_time_minutes"] = eta
    with pytest.raises(ValidationError): AgentState.model_validate(data)

def test_wrong_request_and_duplicates(state):
    data = state.model_dump()
    data["all_candidates"][0]["request_id"] = "other"
    with pytest.raises(ValidationError): AgentState.model_validate(data)
    data = state.model_dump()
    data["all_candidates"] = [data["all_candidates"][0]] * 2
    with pytest.raises(ValidationError): AgentState.model_validate(data)

def test_model_failure_audited_without_secret(state):
    def fail(*args): raise RuntimeError("secret API token")
    result = run_match(state,fail)
    assert result.final_match.selected_driver_id == "farther-same-bank"
    assert result.final_match.verification == "model_failed_deterministic_fallback"
    assert "secret" not in result.model_dump_json()

def test_openrouter_http_contract(state, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "mock:free")
    original = httpx.Client
    def handler(request):
        body = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer test-key"
        assert body["model"].endswith(":free")
        sent = json.loads(body["messages"][1]["content"])
        assert all(c["driver_id"] not in ("busy-nearby", "offline-nearby") for c in sent["candidates"])
        return httpx.Response(200, json={"id":"mock-generation", "model":"mock:free", "choices":[{"message":{"content":json.dumps({"selected_driver_id":"farther-same-bank", "estimated_pickup_time_minutes":5, "decision_rationale":"Minimum road ETA"})}}]})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    result = run_match(state, OpenRouterMatcher())
    assert result.final_match.model_call.generation_id == "mock-generation"
    assert result.final_match.verification == "model_verified"
