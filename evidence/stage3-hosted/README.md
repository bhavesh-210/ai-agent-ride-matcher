# Stage 3 hosted Langfuse evidence

Stage: `stage-3-tracing`. Instrumented source: [`d218193fa5bcbe199ff47c4cf19926d02d70dc96`](https://github.com/bhavesh-210/ai-agent-ride-matcher/commit/d218193fa5bcbe199ff47c4cf19926d02d70dc96).

**20 requests, 20 distinct hosted traces, 288 ended observations.** The SDK flushed the batch and the exporter read every trace back from the Langfuse v2 Observations API before writing these artifacts. `hosted_read_verified` is true. The dashboard independently showed 20 root observations.

Provider mode: **offline**. These are real hosted Langfuse traces of deterministic graph execution. No new OpenRouter calls or model generations are claimed. There are 19 valid matches and one explicit no-match for the existing source-ID mismatch, which also has its own trace.

## Files

- [traces.json](traces.json): complete server-returned observations, grouped into all 20 traces with stage, source commit, dataset hashes and batch session metadata.
- [bridge-trace.json](bridge-trace.json): extracted actual bridge trace, including full input, per-candidate decision audit and child observations.
- [summary.json](summary.json): trace count, bridge check, 19 matches and unmatched request ID.
- [verification.json](verification.json): independent checks against the source snapshots; observation counts and runtime timeout setting.

Dashboard screenshots are published with explicit user authorization:

- [Twenty ride roots](langfuse-roots.png)
- [Bridge winner and rationale](langfuse-bridge.png)
- [Slower driver's exclusion and detour reason](langfuse-bridge-reason.png)

Each unedited screenshot has a metadata sidecar identifying the stage, executed source commit and content hash. The screenshots show organization/project context; API credentials are absent. Project keys remain private in the ignored `.env`.

## Bridge explanation checked

Request `RQ-0303-002`, trace `2079c2fdd069cafe983dac043f7d902b` selected available driver `DRV-16643` at **4 minutes** (1.14 km). The closer available `DRV-52907` (1.03 km) takes **16 minutes**. Its audit says the zero-extra-minute policy excludes it and preserves the source note: the Morrison Bridge eastbound ramp is unreachable from SW Naito, requiring a detour via Burnside Bridge. The winner audit says minimum road ETA wins and distance does not determine rank.

The bridge was also inspected in the authenticated Langfuse dashboard; the trace was not made public.

## Reproduce

With private project keys and regional base URL in `.env`, run from source commit `d218193`:

```bash
LANGFUSE_TIMEOUT=30 python -m ride_matcher.trace_batch --destination langfuse --provider-mode offline --source-commit d218193fa5bcbe199ff47c4cf19926d02d70dc96 --output-dir evidence/stage3-hosted-new-run
```

A new invocation creates a new batch session and new trace IDs. Keep its exports separate and label them with the code actually executed. The initial attempt expired during authentication at the default timeout and created no ride traces; the 30-second timeout retry produced the 20 traces documented here.

The 62 passing SDK/matching tests for this same source revision are archived in [the local test output](../stage3-local/pytest.txt); those test results are distinct from this hosted read-back proof. The earlier `stage3-local` exports remain local-only evidence and were not relabeled as hosted.
