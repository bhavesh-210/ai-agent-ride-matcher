"""Compare supplied road ETAs against the nearest available driver; no network."""
import json
from .evaluate import evaluate


def benchmark():
    report = evaluate()
    matched = [r for r in report['requests'] if r['final_match']['selected_driver_id'] is not None]
    baseline = sum(r['nearest_available_road_eta_minutes'] for r in matched)
    guarded = sum(r['final_match']['estimated_pickup_time_minutes'] for r in matched)
    return {'mode': 'offline_snapshot_benchmark', 'requests': report['request_count'],
            'matched': len(matched), 'no_match': report['request_count'] - len(matched),
            'improved_requests': report['strict_eta_improvement_count'],
            'nearest_available_total_minutes': baseline, 'matcher_total_minutes': guarded,
            'aggregate_eta_reduction_percent': round(100 * (baseline - guarded) / baseline, 2) if baseline else 0,
            'scope': 'Supplied routing estimates on this snapshot only; not measured real-world waiting time.'}


if __name__ == '__main__':
    print(json.dumps(benchmark(), indent=2))
