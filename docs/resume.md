# Resume entry

**Roadwise — Auditable AI Ride Matcher**  
Python · LangGraph · Pydantic · OpenRouter · FastAPI · Langfuse · pytest

- Built a two-node matching workflow that filters unavailable drivers and validates LLM proposals against deterministic road-ETA ranking, with auditable fallback on invalid responses or provider errors.
- Reduced aggregate supplied pickup ETA from 113 to 60 minutes (**46.9%**) versus nearest-car selection across 19 matched snapshot requests; handled a 16-versus-4-minute bridge detour and a source-ID no-match explicitly.
- Added FastAPI trace integration, an interactive offline demo and 113 automated tests, including regression replay of 20 archived live traces and concurrent request tracing.

Repository: https://github.com/bhavesh-210/ai-agent-ride-matcher

Use two bullets if space is tight. The percentage describes snapshot routing estimates, not measured live rider wait times. The recorded live evidence is 20 hosted traces and 19 real model calls; the unmatched request correctly has no generation. Do not claim production fleet deployment, live traffic routing, or that the LLM itself computes routes.
