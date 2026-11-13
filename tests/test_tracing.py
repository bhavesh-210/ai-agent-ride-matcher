import json
from types import SimpleNamespace
import pytest
from opentelemetry import context
from ride_matcher.config import MatchingConfig
from ride_matcher.datasets import load_requests, load_drivers
from ride_matcher.graph import run_match
from ride_matcher.models import AgentState, ModelDecision
from ride_matcher.trace_batch import run_batch, local_observations, read_hosted_trace
from ride_matcher.tracing import local_tracer, RideTracer


@pytest.fixture
def tracing():
    tracer, exporter=local_tracer(source_commit='a'*40,session_id='pytest-batch',provider_mode='mock',input_hashes={})
    yield tracer, exporter
    tracer.client.shutdown()


def bridge_state():
    request=load_requests('data/source/requests.csv')[1]
    drivers=tuple(d for d in load_drivers('data/source/drivers.csv') if d.request_id==request.request_id)
    return AgentState(request=request,all_candidates=drivers)


def test_sdk_trace_has_root_tools_generation_guard_and_explanation(tracing):
    tracer,exporter=tracing
    def bad(request, candidates):
        assert [d.driver_id for d in candidates]==['DRV-16643']
        return ModelDecision(selected_driver_id='DRV-52907',estimated_pickup_time_minutes=16,
                             decision_rationale='Wrong closest-looking driver'),None
    state=bridge_state()
    expected=run_match(state,bad,MatchingConfig())
    actual=run_match(state,bad,MatchingConfig(),tracer)
    assert actual==expected
    tracer.client.flush()
    rows=local_observations(exporter.get_finished_spans())
    assert len({r['traceId'] for r in rows})==1
    roots=[r for r in rows if not r['parentObservationId']]
    assert len(roots)==1 and roots[0]['name']=='ride.match'
    root=roots[0]
    assert root['output']['selected_driver_id']=='DRV-16643'
    assert root['output']['verification']=='model_overridden_by_eta_guard'
    attrs=root['attributes']
    assert attrs['session.id']=='pytest-batch'
    assert attrs['langfuse.release']=='a'*40
    for name in ('check_availability','estimate_pickup_time','check_eligibility'):
        assert sum(r['name']==name for r in rows)==4
    generation=next(r for r in rows if r['name']=='openrouter.match')
    assert generation['type']=='generation'
    assert len(generation['input']['checked_candidates'])==1
    guard=next(r for r in rows if r['name']=='validate_model_choice')
    assert guard['type']=='guardrail' and guard['output']['accepted'] is False
    assert all(r['endTime'] for r in rows)


def test_provider_exception_is_traced_without_secret(tracing):
    tracer,exporter=tracing
    def failing(*args):
        raise RuntimeError('TOP-SECRET-KEY')
    result=run_match(bridge_state(),failing,tracer=tracer)
    tracer.client.flush()
    rows=local_observations(exporter.get_finished_spans())
    serialized=json.dumps(rows)
    assert 'TOP-SECRET-KEY' not in serialized
    assert result.final_match.selected_driver_id=='DRV-16643'
    generation=next(r for r in rows if r['name']=='openrouter.match')
    assert generation['attributes']['langfuse.observation.level']=='ERROR'
    assert generation['attributes']['langfuse.observation.status_message']=='RuntimeError'


def test_twenty_local_sdk_roots_include_no_match_and_bridge(tmp_path):
    summary=run_batch(destination='local',provider_mode='offline',source_commit='b'*40,output_dir=tmp_path)
    assert summary['trace_count']==20 and summary['matched']==19
    assert summary['_evidence']['hosted_read_verified'] is False
    export=json.loads((tmp_path/'traces.json').read_text())
    assert len({t['trace_id'] for t in export['traces']})==20
    assert len({t['request_id'] for t in export['traces']})==20
    for trace in export['traces']:
        assert len([r for r in trace['observations'] if not r['parentObservationId']])==1
        assert trace['input']['request_id']==trace['request_id']
    missing=next(t for t in export['traces'] if t['request_id']=='RQ-0308-018')
    assert missing['output']['selected_driver_id'] is None
    assert not any(r['type']=='generation' for r in missing['observations'])
    bridge=json.loads((tmp_path/'bridge-trace.json').read_text())
    assert bridge['output']['estimated_pickup_time_minutes']==4
    assert 'rider_id' not in json.dumps(export) and 'coordinates' not in json.dumps(export)


def test_each_invocation_is_a_new_trace_even_inside_another_root(tracing):
    tracer,exporter=tracing
    with tracer.client.start_as_current_observation(name='caller'):
        run_match(bridge_state(),tracer=tracer)
        run_match(bridge_state(),tracer=tracer)
    tracer.client.flush()
    roots=[r for r in local_observations(exporter.get_finished_spans()) if not r['parentObservationId']]
    assert len(roots)==3
    assert len({r['traceId'] for r in roots})==3


def test_missing_hosted_keys_fails_before_claiming_upload(monkeypatch):
    for key in ('LANGFUSE_PUBLIC_KEY','LANGFUSE_SECRET_KEY','LANGFUSE_BASE_URL'):
        monkeypatch.delenv(key,raising=False)
    with pytest.raises(ValueError,match='privately'):
        RideTracer.from_env(source_commit='a'*40,session_id='test',provider_mode='offline',input_hashes={})


def test_hosted_export_follows_cursor_and_requires_complete_root():
    calls=[]
    class Row:
        def __init__(self, data): self.data=data
        def model_dump(self, **kwargs): return self.data
    def get_many(**kwargs):
        calls.append(kwargs)
        if kwargs['cursor'] is None:
            return SimpleNamespace(data=[Row({'name':'ride.match','parentObservationId':None,'output':{'ok':True},'endTime':'end'})],meta=SimpleNamespace(cursor='next'))
        return SimpleNamespace(data=[Row({'name':'child','parentObservationId':'parent','endTime':'end'})],meta=SimpleNamespace(cursor=None))
    client=SimpleNamespace(api=SimpleNamespace(observations=SimpleNamespace(get_many=get_many)))
    rows=read_hosted_trace(client,'id',start='start',end='end',expected_count=2,timeout=0)
    assert len(rows)==2 and [c['cursor'] for c in calls]==[None,'next']
    assert calls[0]['from_start_time']=='start'


def test_hosted_export_rejects_incomplete_ingestion():
    client=SimpleNamespace(api=SimpleNamespace(observations=SimpleNamespace(get_many=lambda **kw:SimpleNamespace(data=[],meta=SimpleNamespace(cursor=None)))))
    with pytest.raises(RuntimeError,match='deadline'):
        read_hosted_trace(client,'id',start='start',end='end',expected_count=3,timeout=0)


def test_generation_records_exact_openrouter_messages(tracing, monkeypatch):
    import httpx
    from ride_matcher.provider import OpenRouterMatcher
    tracer, exporter=tracing
    monkeypatch.setenv('OPENROUTER_API_KEY','mock-only-key')
    monkeypatch.setenv('OPENROUTER_MODEL','mock:free')
    sent=[]
    original=httpx.Client
    def handler(request):
        sent.extend(json.loads(request.content)['messages'])
        return httpx.Response(200,json={'id':'mock-generation','model':'mock:free','usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120},'choices':[{'message':{'content':json.dumps({'selected_driver_id':'DRV-16643','estimated_pickup_time_minutes':4,'decision_rationale':'Four beats sixteen'})}}]})
    monkeypatch.setattr(httpx,'Client',lambda **kwargs: original(transport=httpx.MockTransport(handler),**kwargs))
    run_match(bridge_state(),OpenRouterMatcher(),tracer=tracer)
    tracer.client.flush()
    rows=local_observations(exporter.get_finished_spans())
    generation=next(r for r in rows if r['name']=='openrouter.match')
    assert generation['input']==sent
    assert 'mock-only-key' not in json.dumps(rows)
    assert generation['attributes']['langfuse.observation.model.name']=='mock:free'
    root=next(r for r in rows if r['name']=='ride.match')
    assert root['output']['tokens']=={'input':100,'output':20,'total':120}
    assert root['output']['model']=='mock:free'
    assert root['output']['model_rationale']=='Four beats sixteen'
    assert root['output']['latency_ms']>=0
    assert 'error' in root['output'] and root['output']['error'] is None
    assert json.loads(generation['attributes']['langfuse.observation.usage_details'])=={'input':100,'output':20,'total':120}


def test_batch_refuses_to_overwrite_archived_evidence_before_any_calls(tmp_path):
    (tmp_path/'traces.json').write_text('preserve-this')
    with pytest.raises(FileExistsError, match='archived'):
        run_batch(destination='local', provider_mode='offline', source_commit='b'*40, output_dir=tmp_path)
    assert (tmp_path/'traces.json').read_text() == 'preserve-this'


def test_bridge_export_remains_valid_with_wider_configured_shortlist(tmp_path, monkeypatch):
    monkeypatch.setenv('ACCEPTED_EXTRA_PICKUP_MINUTES', '20')
    summary = run_batch(destination='local', provider_mode='offline', source_commit='b'*40, output_dir=tmp_path)
    assert summary['bridge_check'] == 'passed'
    bridge = json.loads((tmp_path/'bridge-trace.json').read_text())
    assert bridge['output']['selected_driver_id'] == 'DRV-16643'
    slower = next(a for a in bridge['output']['evaluated_candidates'] if a['driver_id'] == 'DRV-52907')
    assert slower['outcome'] == 'not_selected'
