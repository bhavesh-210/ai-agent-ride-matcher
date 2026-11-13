"""Reproducible offline evaluation of all assignment requests; no API evidence."""
import json
from pathlib import Path
from .datasets import load_requests, load_drivers, dataset_warnings
from .models import AgentState
from .graph import run_match


def evaluate(requests_path='data/source/requests.csv', drivers_path='data/source/drivers.csv'):
    requests = load_requests(requests_path)
    drivers = load_drivers(drivers_path)
    records = []
    for request in requests:
        candidates = tuple(d for d in drivers if d.request_id == request.request_id)
        result = run_match(AgentState(request=request, all_candidates=candidates))
        eligible = [d for d in candidates if d.status == 'available' and d.actual_pickup_time_minutes is not None]
        nearest = min(eligible, key=lambda d: (d.straight_line_distance_km, d.driver_id), default=None)
        selected_eta = result.final_match.estimated_pickup_time_minutes
        records.append({'request_id': request.request_id,
            'nearest_available_driver_id': nearest.driver_id if nearest else None,
            'nearest_available_road_eta_minutes': nearest.actual_pickup_time_minutes if nearest else None,
            'strict_eta_improvement_over_nearest': bool(nearest and selected_eta < nearest.actual_pickup_time_minutes),
            'final_match': result.final_match.model_dump(mode='json')})
    return {'mode': 'offline_assignment_evaluation_no_api_call',
        'request_count': len(requests), 'candidate_row_count': len(drivers),
        'matched_request_count': sum(r['final_match']['selected_driver_id'] is not None for r in records),
        'strict_eta_improvement_count': sum(r['strict_eta_improvement_over_nearest'] for r in records),
        'dataset_warnings': dataset_warnings(requests, drivers), 'requests': records}

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', help='Optional new JSON path; existing files are never overwritten')
    parser.add_argument('--source-commit', help='Full tested source SHA; required with --output')
    args = parser.parse_args()
    if args.output:
        import re
        if not re.fullmatch(r'[0-9a-f]{40}', args.source_commit or ''):
            parser.error('--output requires a full --source-commit for provenance')
        if Path(args.output).exists():
            parser.error('Choose a new output path; archived evidence must not be overwritten')
    report = evaluate()
    if args.output:
        report['_evidence'] = {'stage': 'offline-evaluation', 'commit': args.source_commit,
                               'provider_mode': 'offline'}
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x') as file:
            file.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:v for k,v in report.items() if k != 'requests'}, indent=2))
