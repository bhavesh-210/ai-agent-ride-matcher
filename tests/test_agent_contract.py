"""Stage contract: shared policy, pre-model tools and all snapshot requests."""
from pathlib import Path
import json
import httpx
import pytest
from ride_matcher import tools as candidate_tools
from ride_matcher.config import MatchingConfig
from ride_matcher.datasets import load_requests, load_drivers
from ride_matcher.graph import run_match
from ride_matcher.models import AgentState
from ride_matcher.provider import OpenRouterMatcher

ROOT = Path(__file__).resolve().parents[1]
REQUESTS = load_requests(ROOT / 'data/source/requests.csv')
DRIVERS = load_drivers(ROOT / 'data/source/drivers.csv')


@pytest.mark.parametrize('ride_request', REQUESTS, ids=lambda r: r.request_id)
def test_each_request_has_one_available_match_within_shared_limit_or_explicit_no_route(ride_request):
    request = ride_request
    config = MatchingConfig.from_env()
    candidates = tuple(d for d in DRIVERS if d.request_id == request.request_id)
    available = [d for d in candidates if d.status == 'available' and d.actual_pickup_time_minutes is not None]
    calls = []
    def bad_provider(request, checked):
        calls.append(checked)
        assert all(d.status == 'available' for d in checked)
        fastest = min(d.actual_pickup_time_minutes for d in available)
        assert all(d.actual_pickup_time_minutes - fastest <= config.accepted_extra_pickup_minutes for d in checked)
        raise RuntimeError('Deliberate provider failure exercises deterministic fallback')
    result = run_match(AgentState(request=request, all_candidates=candidates), bad_provider, config).final_match
    selected = [a for a in result.evaluated_candidates if a.outcome == 'selected']
    if not available:
        # Source-ID mismatch is an explicit no-match, never a fabricated assignment.
        assert not selected and result.selected_driver_id is None and not calls
        assert 'no match' in result.decision_rationale.lower()
        return
    assert len(selected) == 1
    row = next(d for d in candidates if d.driver_id == result.selected_driver_id)
    assert row.status == 'available'
    minimum = min(d.actual_pickup_time_minutes for d in available)
    assert row.actual_pickup_time_minutes - minimum <= config.accepted_extra_pickup_minutes
    assert row.actual_pickup_time_minutes == minimum
    assert result.estimated_pickup_time_minutes == row.actual_pickup_time_minutes
    assert len(calls) == 1


def test_all_three_tools_execute_before_actual_openrouter_payload(monkeypatch):
    request = next(r for r in REQUESTS if r.request_id == 'RQ-0303-002')
    drivers = tuple(d for d in DRIVERS if d.request_id == request.request_id)
    config = MatchingConfig.from_env()
    events = []
    for name in ('check_availability', 'estimate_pickup_time', 'check_eligibility'):
        original = getattr(candidate_tools, name)
        def record(*args, _name=name, _original=original, **kwargs):
            events.append(_name)
            return _original(*args, **kwargs)
        monkeypatch.setattr(candidate_tools, name, record)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'mock-only-key')
    monkeypatch.setenv('OPENROUTER_MODEL', 'mock:free')
    original_client = httpx.Client
    def handler(http_request):
        assert events.count('check_availability') == len(drivers)
        assert events.count('estimate_pickup_time') == len(drivers)
        assert events.count('check_eligibility') == len(drivers)
        events.append('openrouter')
        body = json.loads(http_request.content)
        assert 'one short line' in body['messages'][0]['content']
        payload = json.loads(body['messages'][1]['content'])
        available = [d for d in drivers if d.status == 'available' and d.actual_pickup_time_minutes is not None]
        fastest = min(d.actual_pickup_time_minutes for d in available)
        expected = {d.driver_id for d in available if d.actual_pickup_time_minutes - fastest <= config.accepted_extra_pickup_minutes}
        assert {d['driver_id'] for d in payload['candidates']} == expected
        winner = min(available, key=lambda d: (d.actual_pickup_time_minutes, d.driver_id))
        return httpx.Response(200, json={'id':'mock-only', 'model':'mock:free', 'choices':[{'message':{'content':json.dumps({'selected_driver_id':winner.driver_id,'estimated_pickup_time_minutes':winner.actual_pickup_time_minutes,'decision_rationale':'Minimum supplied road ETA'})}}]})
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    result = run_match(AgentState(request=request, all_candidates=drivers), OpenRouterMatcher(), config)
    assert events[-1] == 'openrouter'
    assert result.final_match.verification == 'model_verified'
