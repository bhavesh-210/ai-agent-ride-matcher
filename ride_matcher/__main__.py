import argparse
import hashlib
import json
from pathlib import Path
from dotenv import load_dotenv
from .models import AgentState, RideRequest, Driver
from .graph import run_match
from .provider import OpenRouterMatcher, list_free_models


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Two-node ride matcher")
    parser.add_argument("--requests", default="data/requests.example.json")
    parser.add_argument("--drivers", default="data/drivers.example.json")
    parser.add_argument("--request-id", default="bridge-001")
    parser.add_argument("--offline", action="store_true", help="Explicit demo; makes NO OpenRouter call")
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--output", default="evidence/run.json")
    args = parser.parse_args()
    if args.list_models:
        print("\n".join(list_free_models()))
        return
    requests_bytes = Path(args.requests).read_bytes()
    drivers_bytes = Path(args.drivers).read_bytes()
    requests = [RideRequest.model_validate(r) for r in json.loads(requests_bytes)]
    if len({r.request_id for r in requests}) != len(requests):
        raise ValueError("Duplicate request IDs")
    request = next((r for r in requests if r.request_id == args.request_id), None)
    if request is None:
        raise ValueError("Request ID not found")
    drivers = [Driver.model_validate(d) for d in json.loads(drivers_bytes)]
    state = AgentState(request=request, all_candidates=tuple(d for d in drivers if d.request_id == request.request_id))
    result = run_match(state, None if args.offline else OpenRouterMatcher())
    evidence = {"mode": "offline_demo" if args.offline else "live_openrouter",
        "input_sha256": {"requests": hashlib.sha256(requests_bytes).hexdigest(),
                         "drivers": hashlib.sha256(drivers_bytes).hexdigest()},
        "result": result.model_dump(mode="json")}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    if not args.offline and (result.final_match.model_call is None or result.final_match.verification != "model_verified"):
        raise SystemExit("Live run not verified; inspect evidence and rerun before submission.")

if __name__ == "__main__":
    main()
