import json
from pathlib import Path

import pytest
from ride_matcher.replay import replay_trace, replay_export
from ride_matcher.trace_audit import audit_trace_fields

EXPORT = Path(__file__).resolve().parents[1] / 'evidence/stage3-live/traces.json'
TRACES = json.loads(EXPORT.read_text())['traces']


@pytest.mark.parametrize('trace', TRACES, ids=[t['request_id'] for t in TRACES])
def test_saved_live_trace_replays_without_network(trace, monkeypatch):
    import socket
    def blocked(*args, **kwargs):
        raise AssertionError('Trace replay must not use network')
    monkeypatch.setattr(socket, 'create_connection', blocked)
    result = replay_trace(trace).final_match
    assert result.selected_driver_id == trace['output']['selected_driver_id']
    assert result.estimated_pickup_time_minutes == trace['output']['estimated_pickup_time_minutes']
    assert [a.model_dump(mode='json') for a in result.evaluated_candidates] == trace['output']['evaluated_candidates']


def test_complete_saved_live_export_passes_stronger_audit_and_replay():
    report = audit_trace_fields(json.loads(EXPORT.read_text()))
    assert report['trace_count'] == 20
    assert report['missing_required_fields'] == report['incomplete_model_traces'] == []
    assert replay_export(EXPORT)['mismatches'] == []
