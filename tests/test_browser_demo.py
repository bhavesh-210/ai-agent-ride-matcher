"""Keep the public browser simulator aligned with the actual Python graph."""
import json
from html.parser import HTMLParser
from pathlib import Path
import random
import shutil
import subprocess

import pytest
from ride_matcher.config import MatchingConfig
from ride_matcher.graph import run_match
from ride_matcher.models import AgentState, Coordinates, Driver, ModelDecision, RideRequest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web-demo'


@pytest.mark.skipif(shutil.which('node') is None, reason='Optional browser-policy parity check requires Node.js')
def test_browser_policy_matches_python_graph_for_sixty_scenarios():
    rng = random.Random(730)
    records, expected = [], []
    point = Coordinates(lat=0, lon=0)
    for index in range(60):
        candidates = [dict(driver_id='DRV-'+str(i), status=rng.choice(['available','offline','on_trip']),
            road_eta_minutes=rng.choice([None,0,2,4,16]), straight_line_distance_km=rng.choice([0.1,1,2])) for i in range(4)]
        allowance = rng.choice([0,5,20])
        proposal = None if index % 4 == 0 else dict(selected_driver_id=rng.choice(['DRV-0','DRV-1','DRV-INVENTED']), estimated_pickup_time_minutes=rng.choice([0,2,4,16]), decision_rationale='Synthetic parity-test proposal')
        request = RideRequest(request_id='parity', rider_id='synthetic', pickup_coordinates=point)
        drivers = tuple(Driver(request_id='parity', driver_id=d['driver_id'], status=d['status'], coordinates=point,
            straight_line_distance_km=d['straight_line_distance_km'], actual_pickup_time_minutes=d['road_eta_minutes']) for d in candidates)
        def provider(request, checked):
            return ModelDecision.model_validate(proposal), None
        result = run_match(AgentState(request=request, all_candidates=drivers), provider if proposal else None,
                           MatchingConfig(accepted_extra_pickup_minutes=allowance))
        records.append(dict(candidates=candidates, allowance=allowance, proposal=proposal))
        expected.append(dict(selected_driver_id=result.final_match.selected_driver_id,
            estimated_pickup_time_minutes=result.final_match.estimated_pickup_time_minutes,
            eligible_driver_ids=[d.driver_id for d in result.eligible_candidates], verification=result.final_match.verification))
    script = """const fs=require('fs'),policy=require(process.argv[1]);
const cases=JSON.parse(fs.readFileSync(0,'utf8'));
console.log(JSON.stringify(cases.map(c=>{const r=policy.match(c.candidates,c.allowance,c.proposal);return {selected_driver_id:r.selected_driver_id,estimated_pickup_time_minutes:r.estimated_pickup_time_minutes,eligible_driver_ids:r.eligible_driver_ids,verification:r.verification};})));"""
    result = subprocess.run(['node','-e',script,str(WEB/'policy.js')],input=json.dumps(records),text=True,capture_output=True,check=True)
    assert json.loads(result.stdout) == expected


def test_all_public_demo_assets_and_recorded_trace_results_are_present():
    class Assets(HTMLParser):
        def __init__(self): super().__init__(); self.sources=[]
        def handle_starttag(self,tag,attrs):
            for key,value in attrs:
                if key=='src' and '://' not in value: self.sources.append(value)
    parser=Assets(); parser.feed((WEB/'index.html').read_text())
    assert 'app.js' in parser.sources and 'policy.js' in parser.sources
    assert all((WEB/path).is_file() for path in parser.sources)
    snapshot=json.loads((WEB/'snapshot.json').read_text())
    traces=json.loads((WEB/'traces.json').read_text())
    assert len(snapshot['results']) == len(traces['traces']) == 20
    for request_id, data in snapshot['results'].items():
        trace=traces['traces'][request_id]
        for field in ('selected_driver_id','estimated_pickup_time_minutes'):
            assert data['match'][field] == trace['output'][field]
        assert trace['source_commit'] == traces['_provenance']['source_commit']
    assert snapshot['_provenance']['default_accepted_extra_pickup_minutes'] == MatchingConfig().accepted_extra_pickup_minutes


@pytest.mark.skipif(shutil.which('node') is None, reason='Optional browser-policy validation requires Node.js')
def test_browser_simulator_rejects_bad_inputs_and_preserves_zero():
    script="""const assert=require('assert'),p=require(process.argv[1]);
const d={driver_id:'A',status:'available',road_eta_minutes:0,straight_line_distance_km:1};
assert.strictEqual(p.match([d],0).estimated_pickup_time_minutes,0);
for(const eta of [-1,Infinity,NaN,true]) assert.throws(()=>p.match([{...d,road_eta_minutes:eta}],0));
assert.throws(()=>p.match([d,d],0));assert.throws(()=>p.match([d],-1));
assert.strictEqual(p.match([{...d,road_eta_minutes:null}],0).selected_driver_id,null);
assert.strictEqual(p.match([{...d,status:'offline'}],0).selected_driver_id,null);
console.log('browser policy validation passed');"""
    result=subprocess.run(['node','-e',script,str(WEB/'policy.js')],text=True,capture_output=True,check=True)
    assert 'passed' in result.stdout


def test_public_trace_excerpts_preserve_real_prompt_and_checked_shortlist():
    original=json.loads((ROOT/'evidence/stage3-live/traces.json').read_text())
    public=json.loads((WEB/'traces.json').read_text())
    def decode(value):
        return json.loads(value) if isinstance(value,str) else value
    for trace in original['traces']:
        shown=public['traces'][trace['request_id']]
        generation=next((o for o in trace['observations'] if o['name']=='openrouter.match'),None)
        filtered=next(o for o in trace['observations'] if o['name']=='filter_available_drivers')
        assert shown['generation_input'] == (decode(generation['input']) if generation else None)
        assert shown['checked_candidate_ids'] == decode(filtered['output'])['eligible_driver_ids']
        assert shown['output'] == trace['output']
    text=json.dumps(public)
    assert 'rider_id' not in text and 'coordinates' not in text
