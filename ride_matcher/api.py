from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from .models import AgentState
from .graph import run_match
from .provider import OpenRouterMatcher

load_dotenv()
app = FastAPI(title="Ride Matcher", version="0.1.0")

@app.post("/match", response_model=AgentState)
def match(state: AgentState):
    # Ignore caller-supplied derived fields: always rebuild from source inputs.
    clean = AgentState(request=state.request, all_candidates=state.all_candidates)
    try:
        provider = OpenRouterMatcher()
    except ValueError:
        raise HTTPException(status_code=503, detail="Configure OpenRouter key and :free model")
    return run_match(clean, provider)
