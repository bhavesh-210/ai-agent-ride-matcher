from copy import deepcopy
from ride_matcher.trace_audit import audit_trace_fields, REQUIRED_OUTPUT_FIELDS


def complete_export():
    return {'_evidence':{'provider_mode':'openrouter'},'traces':[{
        'trace_id':'trace','request_id':'ride','input':{},'observations':[{
            'name':'openrouter.match','model':'real-returned:free','usageDetails':{'input':10,'output':5,'total':15},
            'output':{'decision_rationale':'Actual model reason'}}],
        'output':{'request_id':'ride','selected_driver_id':'driver','estimated_pickup_time_minutes':4,
                  'decision_rationale':'Canonical minimum ETA','evaluated_candidates':[],
                  'model':'real-returned:free','tokens':{'input':10,'output':5,'total':15},
                  'latency_ms':150,'model_latency_ms':100,'generation_id':'generation',
                  'model_rationale':'Actual model reason','model_call_status':'completed','error':None,
                  'verification':'model_verified'}}]}


def test_complete_live_trace_accepts_explicit_null_error():
    audit=audit_trace_fields(complete_export())
    assert audit['missing_required_fields']==[]
    assert audit['incomplete_model_traces']==[]
    assert audit['model_call_trace_count']==1


def test_missing_error_is_not_the_same_as_explicit_null():
    export=complete_export();del export['traces'][0]['output']['error']
    audit=audit_trace_fields(export)
    assert audit['traces_missing_required_field_count']==1
    assert audit['missing_required_fields'][0]['missing']==['output.error']


def test_native_generation_columns_must_exist_not_just_root_copies():
    export=complete_export();export['traces'][0]['observations'][0].pop('usageDetails')
    audit=audit_trace_fields(export)
    assert audit['missing_required_fields']==[]
    assert 'generation.usageDetails' in audit['incomplete_model_traces'][0]['invalid']


def test_no_candidate_trace_keeps_null_fields_without_fake_generation():
    export=complete_export();trace=export['traces'][0]
    trace['observations']=[]
    trace['output'].update(model=None,tokens=None,model_rationale=None,generation_id=None,
                           model_latency_ms=None,selected_driver_id=None,model_call_status='skipped_no_eligible_candidates')
    audit=audit_trace_fields(export)
    assert audit['missing_required_fields']==[] and audit['incomplete_model_traces']==[]
    assert len(audit['skipped_no_eligible_candidates'])==1
    assert audit['model_call_trace_count']==0


def test_model_error_and_missing_tokens_prevent_success_claim():
    export=complete_export();trace=export['traces'][0]
    trace['output'].update(error='RuntimeError',model_call_status='failed',tokens=None)
    audit=audit_trace_fields(export)
    assert audit['incomplete_model_traces']
    assert 'tokens' in audit['incomplete_model_traces'][0]['invalid']
    assert 'error' in audit['incomplete_model_traces'][0]['invalid']
