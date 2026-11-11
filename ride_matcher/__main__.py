import argparse
import hashlib
import json
from uuid import uuid4
from pathlib import Path
from dotenv import load_dotenv
from .models import AgentState
from .datasets import load_requests, load_drivers, dataset_warnings
from .graph import run_match
from .provider import OpenRouterMatcher, list_free_models
from .tracing import RideTracer


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Two-node ride matcher")
    parser.add_argument("--requests", default="data/requests.example.json")
    parser.add_argument("--drivers", default="data/drivers.example.json")
    parser.add_argument("--request-id", default="bridge-001")
    parser.add_argument("--offline", action="store_true", help="Explicit demo; makes NO OpenRouter call")
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--output", default="evidence/run.json")
    parser.add_argument("--trace", action="store_true", help="Require a hosted Langfuse trace")
    parser.add_argument("--source-commit", help="Full revision SHA for trace provenance")
    args = parser.parse_args()
    if args.list_models:
        print("\n".join(list_free_models()))
        return
    requests_bytes = Path(args.requests).read_bytes()
    drivers_bytes = Path(args.drivers).read_bytes()
    requests = load_requests(args.requests)
    if len({r.request_id for r in requests}) != len(requests):
        raise ValueError("Duplicate request IDs")
    request = next((r for r in requests if r.request_id == args.request_id), None)
    if request is None:
        raise ValueError("Request ID not found")
    drivers = load_drivers(args.drivers)
    state = AgentState(request=request, all_candidates=tuple(d for d in drivers if d.request_id == request.request_id))
    hashes = {"requests": hashlib.sha256(requests_bytes).hexdigest(),
              "drivers": hashlib.sha256(drivers_bytes).hexdigest()}
    tracer = None
    if args.trace:
        tracer = RideTracer.from_env(source_commit=args.source_commit or "", session_id="ride-"+uuid4().hex,
                                     provider_mode="offline" if args.offline else "openrouter", input_hashes=hashes)
    try:
        result = run_match(state, None if args.offline else OpenRouterMatcher(), tracer=tracer)
        if tracer:
            tracer.client.flush()
    finally:
        if tracer:
            tracer.client.shutdown()
    evidence = {"dataset_warnings": dataset_warnings(requests, drivers), "mode": "offline_demo" if args.offline else "live_openrouter",
        "input_sha256": hashes,
        "trace_ids": tracer.trace_ids if tracer else [],
        "result": result.model_dump(mode="json")}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    if not args.offline and (result.final_match.model_call is None or result.final_match.verification != "model_verified"):
        raise SystemExit("Live run not verified; inspect evidence and rerun before submission.")

if __name__ == "__main__":
    main()
