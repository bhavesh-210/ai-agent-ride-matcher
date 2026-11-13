"""REST matching API and an explicitly offline, key-free snapshot demo."""
from contextlib import asynccontextmanager
from pathlib import Path
import os
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse

from .config import MatchingConfig
from .datasets import load_drivers, load_requests
from .graph import run_match
from .models import AgentState
from .provider import OpenRouterMatcher
from .tracing import RideTracer

ROOT = Path(__file__).resolve().parents[1]


def get_provider():
    try:
        return OpenRouterMatcher()
    except ValueError:
        raise HTTPException(status_code=503, detail="Configure OpenRouter key and :free model") from None


def create_app(*, tracer=None, configure_tracing=True):
    @asynccontextmanager
    async def lifespan(app):
        owned = False
        if configure_tracing and not app.state.demo_only:
            load_dotenv()
            keys = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")
            # Partial configuration is an error, rather than silent untraced operation.
            if tracer is None and any(os.getenv(k) for k in keys[:2]):
                app.state.tracer = RideTracer.from_env(
                    source_commit=os.getenv("SOURCE_COMMIT", ""),
                    session_id="api-" + uuid4().hex, provider_mode="openrouter",
                    input_hashes={"source": "caller-supplied validated API inputs"})
                owned = True
        try:
            yield
        finally:
            if owned:
                app.state.tracer.client.flush()
                app.state.tracer.client.shutdown()

    app = FastAPI(title="Road ETA Ride Matcher", version="0.2.0", lifespan=lifespan)
    app.state.tracer = tracer
    app.state.demo_only = os.getenv("RIDE_MATCHER_DEMO_ONLY", "0") == "1"

    @app.get("/health")
    def health():
        return {"status": "ok", "tracing_enabled": app.state.tracer is not None,
                "demo_only": app.state.demo_only,
                "source_commit": os.getenv("SOURCE_COMMIT")}

    @app.post("/match", response_model=AgentState)
    def match(state: AgentState, request: Request, response: Response):
        if request.app.state.demo_only:
            raise HTTPException(status_code=503, detail="Demo-only mode; use /demo/match/{request_id}")
        # Rebuild derived state, including when a caller supplies its own shortlist.
        clean = AgentState(request=state.request, all_candidates=state.all_candidates)
        active_tracer = request.app.state.tracer
        result = run_match(clean, get_provider(), tracer=active_tracer)
        if active_tracer is not None:
            response.headers["X-Trace-Id"] = active_tracer.current_trace_id.get()
        return result

    @app.get("/", include_in_schema=False)
    def demo():
        return FileResponse(ROOT / "ride_matcher" / "static" / "index.html")

    @app.get("/demo/requests")
    def demo_requests():
        return {"mode": "offline_snapshot_demo", "request_ids": [
            r.request_id for r in load_requests(ROOT / "data/source/requests.csv")]}

    @app.post("/demo/match/{request_id}")
    def demo_match(request_id: str):
        ride = next((r for r in load_requests(ROOT / "data/source/requests.csv")
                     if r.request_id == request_id), None)
        if ride is None:
            raise HTTPException(status_code=404, detail="Unknown snapshot request")
        candidates = tuple(d for d in load_drivers(ROOT / "data/source/drivers.csv")
                           if d.request_id == request_id)
        result = run_match(AgentState(request=ride, all_candidates=candidates),
                           config=MatchingConfig.from_env())
        # This route never calls a provider or uploads a trace, even with live keys set.
        return {"mode": "offline_snapshot_demo", "request_id": request_id,
                "match": result.final_match.model_dump(mode="json")}

    return app


app = create_app()
