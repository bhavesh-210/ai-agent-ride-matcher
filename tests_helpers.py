"""Shared snapshot fixture construction; no API credentials required."""
from pathlib import Path
from ride_matcher.datasets import load_drivers, load_requests
from ride_matcher.models import AgentState

ROOT = Path(__file__).resolve().parent


def snapshot_state(request_id='RQ-0303-002'):
    request = next(r for r in load_requests(ROOT / 'data/source/requests.csv') if r.request_id == request_id)
    candidates = tuple(d for d in load_drivers(ROOT / 'data/source/drivers.csv') if d.request_id == request_id)
    return AgentState(request=request, all_candidates=candidates)
