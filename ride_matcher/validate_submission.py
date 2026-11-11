"""Reproduce stage evidence offline, including the actual OpenRouter prompt shape."""
import json
import os
from pathlib import Path
from unittest.mock import patch
import httpx
from .config import MatchingConfig
from .datasets import load_requests, load_drivers, dataset_warnings
from .graph import run_match
from .models import AgentState
from .provider import OpenRouterMatcher


def validate_submission():
    config = MatchingConfig.from_env()
    requests = load_requests('data/source/requests.csv')
    drivers = load_drivers('data/source/drivers.csv')
    records = []
    for request in requests:
        candidates = tuple(d for d in drivers if d.request_id == request.request_id)
        match = run_match(AgentState(request=request, all_candidates=candidates), config=config).final_match
        available = [d for d in candidates if d.status == 'available' and d.actual_pickup_time_minutes is not None]
        winner = next((d for d in candidates if d.driver_id == match.selected_driver_id), None)
        if available:
            minimum = min(d.actual_pickup_time_minutes for d in available)
            assert winner is not None and winner.status == 'available'
            assert sum(a.outcome == 'selected' for a in match.evaluated_candidates) == 1
            assert winner.actual_pickup_time_minutes - minimum <= config.accepted_extra_pickup_minutes
            assert winner.actual_pickup_time_minutes == minimum
        else:
            assert winner is None
        records.append({'request_id':request.request_id, 'final_match':match.model_dump(mode='json')})

    # Capture messages from the real provider implementation, using a mocked transport.
    request = next(r for r in requests if r.request_id == 'RQ-0303-002')
    candidates = tuple(d for d in drivers if d.request_id == request.request_id)
    prompt = {}
    original_client = httpx.Client
    def handler(http_request):
        body = json.loads(http_request.content)
        prompt.update({'mode':'mock_transport_no_live_api_call', 'messages':body['messages']})
        return httpx.Response(200, json={'id':'mock-only','model':'mock:free','choices':[{'message':{'content':json.dumps({'selected_driver_id':'DRV-16643','estimated_pickup_time_minutes':4,'decision_rationale':'Lowest supplied road pickup minutes'})}}]})
    with patch.dict(os.environ, {'OPENROUTER_API_KEY':'mock-only', 'OPENROUTER_MODEL':'mock:free'}):
        with patch('ride_matcher.provider.httpx.Client', side_effect=lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs)):
            result = run_match(AgentState(request=request, all_candidates=candidates), OpenRouterMatcher(), config)
    assert result.final_match.verification == 'model_verified'
    output = Path('evidence')
    output.mkdir(exist_ok=True)
    report = {'mode':'offline_validation_no_live_api_call','config':config.model_dump(),
              'request_count':len(requests),'matched':sum(r['final_match']['selected_driver_id'] is not None for r in records),
              'dataset_warnings':dataset_warnings(requests, drivers),'requests':records}
    (output / 'stage2-request-validation.json').write_text(json.dumps(report, indent=2)+'\n')
    (output / 'stage2-prompt-preview.json').write_text(json.dumps(prompt, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('requests','dataset_warnings')}, indent=2))


if __name__ == '__main__':
    validate_submission()
