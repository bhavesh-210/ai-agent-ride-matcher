"""Replay saved, redacted matching inputs and proposals without any network calls."""
import argparse
import json
from pathlib import Path

from .config import MatchingConfig
from .graph import run_match
from .models import AgentState, Coordinates, Driver, ModelDecision, RideRequest


def replay_trace(trace):
    """Coordinates are placeholders: ranking only uses recorded road ETA and status."""
    request_id = trace['request_id']
    point = Coordinates(lat=0, lon=0)
    state = AgentState(
        request=RideRequest(request_id=request_id, rider_id='redacted-replay', pickup_coordinates=point),
        all_candidates=tuple(Driver(request_id=request_id, driver_id=d['driver_id'], status=d['status'],
            coordinates=point, straight_line_distance_km=d['straight_line_distance_km'],
            actual_pickup_time_minutes=d['road_pickup_minutes'], route_note=d.get('route_note', ''))
            for d in trace['input']['candidates']))
    saved = trace['output'].get('model_proposal')
    def recorded_provider(request, candidates):
        return ModelDecision.model_validate(saved), None
    config = MatchingConfig(accepted_extra_pickup_minutes=trace['output']['accepted_extra_pickup_minutes'])
    return run_match(state, recorded_provider if saved else None, config)


def replay_export(path):
    export = json.loads(Path(path).read_text())
    mismatches = []
    for trace in export['traces']:
        result = replay_trace(trace).final_match
        saved = trace['output']
        for key in ('selected_driver_id', 'estimated_pickup_time_minutes'):
            if getattr(result, key) != saved[key]:
                mismatches.append({'request_id': trace['request_id'], 'field': key})
        if [a.model_dump(mode='json') for a in result.evaluated_candidates] != saved['evaluated_candidates']:
            mismatches.append({'request_id': trace['request_id'], 'field': 'evaluated_candidates'})
    return {'mode': 'offline_trace_replay', 'trace_count': len(export['traces']),
            'original_source_commit': export['_evidence']['commit'], 'mismatches': mismatches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', nargs='?', default='evidence/stage3-live/traces.json')
    args = parser.parse_args()
    report = replay_export(args.export)
    print(json.dumps(report, indent=2))
    if report['mismatches']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
