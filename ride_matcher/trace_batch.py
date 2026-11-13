"""Trace all snapshot requests, verify server reads, export replay-ready JSON."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4
from dotenv import load_dotenv
from .config import MatchingConfig
from .datasets import load_requests, load_drivers
from .graph import run_match
from .models import AgentState
from .provider import OpenRouterMatcher
from .tracing import RideTracer, local_tracer
from .trace_audit import audit_trace_fields


def decode(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            pass
    return value


def local_observations(spans):
    rows = []
    for span in spans:
        attrs = dict(span.attributes)
        rows.append({"id": format(span.context.span_id, "016x"),
                     "traceId": format(span.context.trace_id, "032x"),
                     "parentObservationId": format(span.parent.span_id, "016x") if span.parent else None,
                     "name":span.name,"type":attrs.get("langfuse.observation.type"),
                     "startTime":datetime.fromtimestamp(span.start_time/1e9, timezone.utc).isoformat(),
                     "endTime":datetime.fromtimestamp(span.end_time/1e9, timezone.utc).isoformat(),
                     "input":decode(attrs.get("langfuse.observation.input")),
                     "output":decode(attrs.get("langfuse.observation.output")),
                     "attributes":attrs})
    return rows


def read_hosted_trace(client, trace_id, *, start, end, expected_count, timeout=90):
    """Flush alone is not proof: require complete observations read from server."""
    deadline = time.monotonic()+timeout
    while True:
        cursor = None
        seen_cursors = set()
        rows = []
        while True:
            response = client.api.observations.get_many(trace_id=trace_id,
                fields="core,basic,time,io,model,usage,metrics,trace_context",
                from_start_time=start, to_start_time=end, limit=1000, cursor=cursor)
            rows.extend(row.model_dump(mode="json", by_alias=True) for row in response.data)
            cursor = response.meta.cursor
            if not cursor:
                break
            if cursor in seen_cursors:
                raise RuntimeError("Langfuse repeated a pagination cursor")
            seen_cursors.add(cursor)
        roots = [r for r in rows if r.get("name")=="ride.match" and not r.get("parentObservationId")]
        if len(rows) >= expected_count and len(roots)==1 and roots[0].get("output") is not None and all(r.get("endTime") for r in rows):
            return rows
        if time.monotonic() >= deadline:
            raise RuntimeError("Langfuse observations not fully readable before deadline")
        time.sleep(2)


def assemble_export(trace_ids, observations, evidence):
    traces = []
    for record in trace_ids:
        rows = [r for r in observations if r["traceId"]==record["trace_id"]]
        roots = [r for r in rows if r["name"]=="ride.match" and not r.get("parentObservationId")]
        if len(roots)!=1:
            raise ValueError("Each ride must have exactly one root observation")
        root=roots[0]
        traces.append({"_evidence":evidence,**record,"input":decode(root.get("input")),
                       "output":decode(root.get("output")),"observations":rows})
    if len({t["trace_id"] for t in traces}) != len(traces):
        raise ValueError("Different requests share a trace ID")
    return {"_evidence":evidence,"trace_count":len(traces),"traces":traces}


def check_bridge(export):
    bridge=next(t for t in export["traces"] if t["request_id"]=="RQ-0303-002")
    out=bridge["output"]
    assert out["selected_driver_id"]=="DRV-16643" and out["estimated_pickup_time_minutes"]==4
    audits={r["driver_id"]:r for r in out["evaluated_candidates"]}
    assert audits["DRV-52907"]["road_eta_minutes"]==16
    expected_outcome = "excluded" if out["accepted_extra_pickup_minutes"] < 12 else "not_selected"
    assert audits["DRV-52907"]["outcome"] == expected_outcome
    assert "Burnside Bridge" in audits["DRV-52907"]["reason"]
    assert audits["DRV-16643"]["outcome"]=="selected"
    assert "distance" in out["decision_rationale"].lower()
    return bridge


def run_batch(*, destination, provider_mode, source_commit, output_dir, session_id=None):
    output = Path(output_dir)
    if any((output / name).exists() for name in
           ("traces.json", "bridge-trace.json", "field-audit.json", "summary.json")):
        raise FileExistsError("Use a new output directory; archived trace evidence must not be overwritten")
    config=MatchingConfig.from_env()
    paths={"requests":Path('data/source/requests.csv'),"drivers":Path('data/source/drivers.csv')}
    hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in paths.items()}
    session_id=session_id or "ride-matcher-"+uuid4().hex
    kwargs=dict(source_commit=source_commit,session_id=session_id,provider_mode=provider_mode,input_hashes=hashes)
    exporter=None
    if destination=="local":
        tracer,exporter=local_tracer(**kwargs)
    elif destination=="langfuse":
        tracer=RideTracer.from_env(**kwargs)
    else:
        raise ValueError("Unknown trace destination")
    provider=None if provider_mode=="offline" else OpenRouterMatcher()
    start=datetime.now(timezone.utc)-timedelta(seconds=1)
    expected={}
    try:
        for request in load_requests(paths["requests"]):
            candidates=tuple(d for d in load_drivers(paths["drivers"]) if d.request_id==request.request_id)
            result=run_match(AgentState(request=request,all_candidates=candidates),provider,config,tracer)
            # Root, two graph nodes, three tools per source row, optional generation and guard.
            attempted=bool(provider and result.eligible_candidates)
            expected[tracer.trace_ids[-1]["trace_id"]]=3+3*len(candidates)+int(attempted)+int(result.final_match.model_proposal is not None)
        tracer.client.flush()
        end=datetime.now(timezone.utc)+timedelta(seconds=1)
        if exporter is not None:
            observations=local_observations(exporter.get_finished_spans())
        else:
            observations=[]
            for record in tracer.trace_ids:
                observations.extend(read_hosted_trace(tracer.client,record["trace_id"],start=start,end=end,
                                                      expected_count=expected[record["trace_id"]]))
        evidence={"stage":"stage-3-tracing","commit":source_commit,"commit_role":"instrumented_source_revision",
                  "destination":destination,"hosted_read_verified":destination=="langfuse",
                  "provider_mode":provider_mode,"session_id":session_id,"dataset_sha256":hashes,
                  "exported_at_utc":datetime.now(timezone.utc).isoformat(),
                  "format":"langfuse-observations-v2-grouped-by-trace" if destination=="langfuse" else "local-langfuse-sdk-otel-export-not-hosted"}
        export=assemble_export(tracer.trace_ids,observations,evidence)
        field_audit=audit_trace_fields(export)
        assert export["trace_count"]==20
        bridge=check_bridge(export)
        output=Path(output_dir); output.mkdir(parents=True,exist_ok=True)
        (output/'traces.json').write_text(json.dumps(export,indent=2)+'\n')
        (output/'bridge-trace.json').write_text(json.dumps(bridge,indent=2)+'\n')
        (output/'field-audit.json').write_text(json.dumps(field_audit,indent=2)+'\n')
        summary={"_evidence":evidence,"trace_count":20,"bridge_check":"passed",
                 "missing_required_fields":field_audit["missing_required_fields"],
                 "incomplete_model_traces":field_audit["incomplete_model_traces"],
                 "model_call_trace_count":field_audit["model_call_trace_count"],
                 "matched":sum(t["output"]["selected_driver_id"] is not None for t in export["traces"]),
                 "no_match_requests":[t["request_id"] for t in export["traces"] if t["output"]["selected_driver_id"] is None]}
        (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        return summary
    finally:
        tracer.client.shutdown()


def main():
    load_dotenv()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',choices=['langfuse','local'],default='langfuse')
    parser.add_argument('--provider-mode',choices=['offline','openrouter'],required=True)
    parser.add_argument('--source-commit',required=True)
    parser.add_argument('--output-dir',default='runs/traces-'+uuid4().hex)
    args=parser.parse_args()
    summary=run_batch(destination=args.destination,provider_mode=args.provider_mode,
                      source_commit=args.source_commit,output_dir=args.output_dir)
    print(json.dumps(summary,indent=2))
    if summary["missing_required_fields"] or summary["incomplete_model_traces"]:
        raise SystemExit("Trace field audit failed; inspect saved audit before submission")


if __name__=='__main__':
    main()
