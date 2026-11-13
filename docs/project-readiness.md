# What the project does, and what comes next

The project is an auditable **snapshot matching prototype**. The public demo now covers three distinct experiences:

| Experience | What executes | What it proves |
|---|---|---|
| Guided bridge walkthrough | Explanations and recorded candidate rows | Why a 4-minute road route beats a geographically closer 16-minute driver |
| Request and trace explorer | Read-only snapshot results and curated original hosted-trace excerpts | Actual candidate checks, model prompts, proposal, tokens, timings and source version |
| Editable scenario simulator | A browser implementation of the deterministic policy | How statuses, ETAs and deliberately bad simulated proposals affect the checked winner |

The browser simulator is compared against the Python graph over 60 deterministic synthetic scenarios. Its inputs remain in browser memory. It never calls OpenRouter and does not create a new Langfuse trace. The recorded trace evidence is unchanged by sandbox edits.

The real implementation lives in Python: two LangGraph nodes, immutable Pydantic state, three checks before the provider, OpenRouter JSON responses, deterministic validation/fallback, FastAPI and SDK tracing. Running the local FastAPI demo executes that graph; enabling the live endpoint requires privately configured provider credentials.

## Material gaps for a production dispatch service

1. **A hosted Python API connected to the public frontend.** A public live endpoint also needs a bounded usage budget, authentication/rate limiting, server-side secrets and deployment monitoring. The current public page deliberately needs no credentials or provider spending.
2. **Fresh routing and availability.** Road times and statuses currently come from a fixed snapshot. A routing provider, freshness checks, route-failure policy and current driver status would be needed to promise live pickups.
3. **Atomic driver reservation.** Selecting a driver is not reserving one. A real service must prevent two concurrent requests from claiming the same driver and handle cancellations and retries.
4. **Operational validation.** The snapshot benchmark is small. Load tests, failure recovery and broader data would be needed before claiming fleet-scale performance or real-world wait-time reductions.

These are future deployment requirements, not hidden implemented features. For an internship resume, the tested matching prototype, public scenario demo and inspectable trace evidence form a defensible project scope.
