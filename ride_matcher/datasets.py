"""Explicit assignment CSV mapping. Preserve source IDs; never infer joins."""
import csv
import json
from collections import Counter
from pathlib import Path
from .models import RideRequest, Driver


def load_requests(path):
    path = Path(path)
    if path.suffix.lower() != '.csv':
        rows = json.loads(path.read_text())
    else:
        with path.open(newline='', encoding='utf-8-sig') as f:
            rows = [dict(request_id=r['request_id'], rider_id=r['rider_id'],
                         pickup_coordinates={'lat': float(r['pickup_lat']), 'lon': float(r['pickup_lng'])})
                    for r in csv.DictReader(f)]
    requests = tuple(RideRequest.model_validate(r) for r in rows)
    if len({r.request_id for r in requests}) != len(requests):
        raise ValueError('Duplicate request IDs')
    return requests


def load_drivers(path):
    path = Path(path)
    if path.suffix.lower() != '.csv':
        rows = json.loads(path.read_text())
    else:
        with path.open(newline='', encoding='utf-8-sig') as f:
            rows = [dict(request_id=r['request_id'], driver_id=r['driver_id'], status=r['driver_status'],
                         coordinates={'lat': float(r['driver_lat']), 'lon': float(r['driver_lng'])},
                         straight_line_distance_km=float(r['straight_line_km']),
                         actual_pickup_time_minutes=float(r['road_pickup_minutes']) if r['road_pickup_minutes'].strip() else None,
                         route_note=r.get('route_note', '')) for r in csv.DictReader(f)]
    drivers = tuple(Driver.model_validate(r) for r in rows)
    keys = [(d.request_id, d.driver_id) for d in drivers]
    if len(set(keys)) != len(keys):
        raise ValueError('Duplicate driver ID within a request')
    return drivers


def dataset_warnings(requests, drivers):
    request_ids = {r.request_id for r in requests}
    driver_ids = {d.request_id for d in drivers}
    return {
        'requests_without_candidates': sorted(request_ids - driver_ids),
        'orphan_candidate_request_ids': sorted(driver_ids - request_ids),
        'candidate_counts': dict(sorted(Counter(d.request_id for d in drivers).items())),
        'policy': 'Exact request_id join only; unmatched source IDs are never silently corrected.'}
