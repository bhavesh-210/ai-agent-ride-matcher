from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from ride_matcher import api
from ride_matcher.models import AgentState, ModelDecision
from ride_matcher.trace_batch import local_observations
from ride_matcher.tracing import local_tracer
from tests_helpers import snapshot_state


@pytest.fixture
def client(monkeypatch):
    tracer, exporter = local_tracer(source_commit='a'*40, session_id='api-test', provider_mode='mock', input_hashes={})
    provider = Mock(return_value=(ModelDecision(selected_driver_id='DRV-16643',
                     estimated_pickup_time_minutes=4, decision_rationale='Fastest road ETA'), None))
    monkeypatch.setattr(api, 'get_provider', lambda: provider)
    with TestClient(api.create_app(tracer=tracer, configure_tracing=False)) as test_client:
        yield test_client, tracer, exporter, provider
    tracer.client.shutdown()


def test_match_endpoint_returns_trace_header_and_resets_caller_shortlist(client):
    http, tracer, exporter, provider = client
    payload = snapshot_state().model_dump(mode='json')
    payload['eligible_candidates'] = [payload['all_candidates'][0]]
    response = http.post('/match', json=payload)
    assert response.status_code == 200
    assert response.json()['final_match']['selected_driver_id'] == 'DRV-16643'
    tracer.client.flush()
    roots = [r for r in local_observations(exporter.get_finished_spans()) if r['name'] == 'ride.match']
    assert len(roots) == 1
    assert response.headers['X-Trace-Id'] == roots[0]['traceId']
    assert [d.driver_id for d in provider.call_args.args[1]] == ['DRV-16643']


def test_api_falls_back_on_provider_failure(client):
    http, _, _, provider = client
    provider.side_effect = RuntimeError('PRIVATE-KEY')
    response = http.post('/match', json=snapshot_state().model_dump(mode='json'))
    assert response.status_code == 200
    result = response.json()
    assert result['final_match']['selected_driver_id'] == 'DRV-16643'
    assert result['final_match']['verification'] == 'model_failed_deterministic_fallback'
    assert 'PRIVATE-KEY' not in response.text


def test_no_candidates_skips_provider_and_still_has_one_trace(client):
    http, tracer, exporter, provider = client
    state = snapshot_state('RQ-0308-018')
    response = http.post('/match', json=state.model_dump(mode='json'))
    assert response.status_code == 200
    assert response.json()['final_match']['selected_driver_id'] is None
    provider.assert_not_called()
    tracer.client.flush()
    rows = local_observations(exporter.get_finished_spans())
    assert len([r for r in rows if r['name'] == 'ride.match']) == 1
    assert not any(r['name'] == 'openrouter.match' for r in rows)


def test_invalid_cross_request_data_is_rejected_before_provider(client):
    http, _, _, provider = client
    payload = snapshot_state().model_dump(mode='json')
    payload['all_candidates'][0]['request_id'] = 'different-request'
    assert http.post('/match', json=payload).status_code == 422
    provider.assert_not_called()


def test_concurrent_api_calls_return_their_own_trace_ids(client):
    http, tracer, exporter, _ = client
    payload = snapshot_state().model_dump(mode='json')
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: http.post('/match', json=payload), range(4)))
    ids = {r.headers['X-Trace-Id'] for r in responses}
    assert all(r.status_code == 200 for r in responses)
    assert len(ids) == 4
    tracer.client.flush()
    roots = [r for r in local_observations(exporter.get_finished_spans()) if r['name'] == 'ride.match']
    assert ids == {r['traceId'] for r in roots}


def test_demo_has_no_provider_or_tracer_dependency(monkeypatch):
    monkeypatch.setattr(api, 'get_provider', Mock(side_effect=AssertionError('Demo must be offline')))
    with TestClient(api.create_app(configure_tracing=False)) as http:
        assert http.get('/').status_code == 200
        assert len(http.get('/demo/requests').json()['request_ids']) == 20
        bridge = http.post('/demo/match/RQ-0303-002').json()
        assert bridge['mode'] == 'offline_snapshot_demo'
        assert bridge['match']['selected_driver_id'] == 'DRV-16643'
        assert http.post('/demo/match/RQ-0308-018').json()['match']['selected_driver_id'] is None
        assert http.post('/demo/match/unknown').status_code == 404
        assert http.get('/health').json()['tracing_enabled'] is False


def test_missing_provider_credentials_return_503(monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    with TestClient(api.create_app(configure_tracing=False)) as http:
        assert http.post('/match', json=snapshot_state().model_dump(mode='json')).status_code == 503


def test_configured_api_initializes_shared_tracer_and_shuts_it_down(monkeypatch):
    from types import SimpleNamespace
    tracer = SimpleNamespace(client=Mock())
    factory = Mock(return_value=tracer)
    monkeypatch.setattr(api.RideTracer, 'from_env', factory)
    monkeypatch.setattr(api, 'load_dotenv', lambda: None)
    monkeypatch.setenv('LANGFUSE_PUBLIC_KEY', 'mock-public')
    monkeypatch.setenv('LANGFUSE_SECRET_KEY', 'mock-secret')
    monkeypatch.setenv('LANGFUSE_BASE_URL', 'http://localhost')
    monkeypatch.setenv('SOURCE_COMMIT', 'c'*40)
    with TestClient(api.create_app()) as http:
        assert http.get('/health').json()['tracing_enabled'] is True
        assert factory.call_args.kwargs['source_commit'] == 'c'*40
    tracer.client.flush.assert_called_once()
    tracer.client.shutdown.assert_called_once()


def test_demo_only_mode_cannot_initialize_hosted_tracing_or_call_provider(monkeypatch):
    monkeypatch.setenv('RIDE_MATCHER_DEMO_ONLY', '1')
    monkeypatch.setattr(api.RideTracer, 'from_env', Mock(side_effect=AssertionError('No hosted SDK')))
    monkeypatch.setattr(api, 'get_provider', Mock(side_effect=AssertionError('No provider')))
    with TestClient(api.create_app()) as http:
        assert http.get('/health').json()['demo_only'] is True
        assert http.post('/match', json=snapshot_state().model_dump(mode='json')).status_code == 503
        assert http.post('/demo/match/RQ-0303-002').status_code == 200
