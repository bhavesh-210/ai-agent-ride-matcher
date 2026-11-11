"""Private assignment integration tests. Supply CSVs locally to run these."""
from pathlib import Path
import pytest
from ride_matcher.datasets import load_requests, load_drivers, dataset_warnings
from ride_matcher.evaluate import evaluate
from ride_matcher.graph import run_match
from ride_matcher.models import AgentState

ROOT = Path(__file__).resolve().parents[1]
REQUESTS = ROOT / 'data/source/requests.csv'
DRIVERS = ROOT / 'data/source/drivers.csv'
pytestmark = pytest.mark.skipif(not REQUESTS.exists() or not DRIVERS.exists(),
                               reason='Assignment source CSVs must be supplied privately')

def test_assignment_counts_and_exact_join_warning():
    requests, drivers = load_requests(REQUESTS), load_drivers(DRIVERS)
    assert len(requests) == 20
    assert len(drivers) == 80
    warnings = dataset_warnings(requests, drivers)
    assert len(warnings['requests_without_candidates']) == 1
    assert len(warnings['orphan_candidate_request_ids']) == 1

@pytest.mark.parametrize('case_kind', ['bridge', 'other_detour'])
def test_real_snapshot_road_time_beats_distance(case_kind):
    requests, all_drivers = load_requests(REQUESTS), load_drivers(DRIVERS)
    cases = []
    for request in requests:
        drivers = tuple(d for d in all_drivers if d.request_id == request.request_id)
        eligible = [d for d in drivers if d.status == 'available' and d.actual_pickup_time_minutes is not None]
        if not eligible:
            continue
        nearest = min(eligible, key=lambda d:(d.straight_line_distance_km,d.driver_id))
        fastest = min(eligible, key=lambda d:(d.actual_pickup_time_minutes,d.driver_id))
        is_bridge = 'bridge' in nearest.route_note.lower()
        if fastest.actual_pickup_time_minutes < nearest.actual_pickup_time_minutes and is_bridge == (case_kind == 'bridge'):
            cases.append((request, drivers, fastest))
    assert cases
    request, drivers, expected = cases[0]
    def provider(request, candidates):
        assert all(d.status == 'available' for d in candidates)
        raise RuntimeError('intentional offline provider for guard test')
    result = run_match(AgentState(request=request, all_candidates=drivers), provider)
    assert result.final_match.selected_driver_id == expected.driver_id
    assert result.final_match.estimated_pickup_time_minutes == expected.actual_pickup_time_minutes
    assert len(result.final_match.evaluated_candidates) == len(drivers)

def test_every_assignment_result_obeys_eta_and_availability():
    drivers = load_drivers(DRIVERS)
    report = evaluate(REQUESTS, DRIVERS)
    assert report['matched_request_count'] == 19
    assert report['strict_eta_improvement_count'] == 7
    for row in report['requests']:
        eligible = [d for d in drivers if d.request_id == row['request_id'] and d.status == 'available'
                    and d.actual_pickup_time_minutes is not None]
        winner = min(eligible, key=lambda d:(d.actual_pickup_time_minutes,d.driver_id), default=None)
        result = row['final_match']
        assert result['selected_driver_id'] == (winner.driver_id if winner else None)
        assert result['estimated_pickup_time_minutes'] == (winner.actual_pickup_time_minutes if winner else None)
