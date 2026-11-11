# Stage 3 trace conventions

This project uses the official Langfuse Python SDK (tested 4.18.0, compatible range >=4.7,<5) and its OpenTelemetry observations. No assignment-specific conventions document was supplied in the repository; these mappings make the chosen conventions explicit and reviewable.

| Concept | Convention |
|---|---|
| Trace boundary | One new root `ride.match`, type `agent`, for each invocation/request, even inside an existing caller trace. Retries are separate invocations with new trace IDs. |
| Grouping | One `session_id` for a batch; `request_id` in metadata and root input/output. No rider identity or GPS coordinates are exported. |
| Provenance | `release` and root `version` are the full supplied source commit. Metadata contains stage, source commit, provider mode, effective threshold and SHA-256 hashes of both input files. |
| Sampling | Dedicated OpenTelemetry provider with `ALWAYS_ON`, so host environment sampling cannot silently drop rides. |
| Graph nodes | Child `chain` observations named `filter_available_drivers` and `match_fastest_driver`; still exactly two graph nodes. |
| Checks | Child `tool` observations named `check_availability`, `estimate_pickup_time`, `check_eligibility` for every source row; inputs, result and real start/end timestamps recorded. |
| Model | `generation` observation `openrouter.match` only when a provider is actually called. Real OpenRouter calls record the exact prompt messages, model, structured proposal, generation ID and client latency. SDK span timing is distinct from provider-reported latency. Missing cost/token metrics are not invented. |
| Guard | `guardrail` observation `validate_model_choice` records proposed versus expected driver/ETA, eligible IDs and acceptance or override. |
| Root output | Final winner, copied road ETA, human-readable rationale, every original candidate's audit, model verification/fallback status and sanitized failure class. |
| Errors/no match | No-match still has one trace and both node observations, with `WARNING`; no generation is invented. Provider failures have an error generation and deterministic fallback. Raw exception messages/keys are not recorded. |
| Export | Flush SDK, then read all observations via the cursor-paginated v2 Observations API. Wait with a deadline for the expected count, one complete root and ended observations. Group by trace ID. A flush or locally generated trace ID alone is not evidence of hosted ingestion. |
| Local testing | Real Langfuse SDK with an in-memory OTEL exporter. Labels say `local` and `hosted_read_verified: false`; this is never described as a hosted Langfuse export. |

The bridge trace must show `DRV-16643` available at 4 minutes, `DRV-52907` geographically closer at 16 minutes, its Burnside Bridge detour note and its exclusion at the zero-extra-minute policy. The root decision must explain that supplied road ETA beats straight-line distance. The batch's source-ID mismatch remains a traced no-match, not a fabricated assignment.

Official references consulted:

- [SDK overview and context managers](https://langfuse.com/docs/observability/sdk/overview)
- [Python SDK reference: trace attributes, nested observations, flush, export](https://python.reference.langfuse.com/langfuse)
- [Public API: Observations API v2 and cursor pagination](https://langfuse.com/docs/api-and-data-platform/features/public-api)
- [Export one trace through observations](https://langfuse.com/faq/all/export-single-trace-or-session)

This document describes conventions, not proof of a hosted run. The exported evidence's destination and `hosted_read_verified` fields establish which execution actually happened.
