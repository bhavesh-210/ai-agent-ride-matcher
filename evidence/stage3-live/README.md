# Stage 3 real OpenRouter batch — reviewer fixes

Stage: `stage-3-tracing`. Executed source: [`98c5804d18e90484023abf0d79b7f3a16469c40c`](https://github.com/bhavesh-210/ai-agent-ride-matcher/commit/98c5804d18e90484023abf0d79b7f3a16469c40c). Provider mode: **openrouter**. Destination: **hosted Langfuse**. Session: `ride-matcher-838f1d2a21f043a5bc9d24241e8e0723`.

## Real calls and server export

All **20 requests** have separate hosted traces. There are **326 ended observations**, including **19 real OpenRouter generations and 19 model-choice guards**. All 19 proposals passed the deterministic guard and produced the source-minimum available driver's ETA. The remaining request, `RQ-0308-018`, has no matching source candidates; it is an explicitly traced skip, not a model call or a fabricated assignment.

Returned model: `liquid/lfm-2.5-2.6b:free`. Actual API token totals: input **3285**, output **5218**, total **8503**. Each call has its own unique generation ID. No mocked provider or offline replacement was used for this batch. The earlier local and offline-provider hosted exports remain unchanged in their separate folders.

The exporter flushed the SDK, read every trace back through the paginated Langfuse Observations API with core/basic/time/IO/model/usage/metrics/trace-context fields, and waited for complete roots and ended observations before exporting.

## Required-field result

**Traces missing any required field: 0/20. Missing-field list: `[]`. Incomplete-model trace list: `[]`.**

See [field-audit.json](field-audit.json) for the field contract and exact result. `error` is explicitly present and null on all 20 roots. On the one no-candidate request, model, tokens and model rationale are explicitly null with `model_call_status: skipped_no_eligible_candidates`; these are intentional non-call values, not absent fields. The 19 completed calls require actual root model/token/rationale values plus native generation model/usage columns.

The pre-change check found 20 historical offline-provider traces missing the newly required fields; [before-field-audit.json](before-field-audit.json) preserves that actual result and records both the audited source revision and the audit implementation revision.

## Bridge field review

**No new bridge-specific explanation field was added.** `output.evaluated_candidates[*].reason` already contained the 16-minute driver's exclusion and Burnside Bridge detour, and `output.decision_rationale` already explained the 4-minute winner. The comparison verified that the canonical candidate audit and rationale did not change. [bridge-field-review.json](bridge-field-review.json) records the comparison.

The general field `model_rationale` is new: it saves the real model's own reason separately from the code's canonical audit. For this bridge request, the model correctly says only checked candidate `DRV-16643` was provided, with a 4-minute ETA. The model never received the excluded 16-minute driver at the zero-minute allowance; the code audit explains that comparison.

Opened the actual bridge trace in Langfuse and checked model, native tokens, latency and the explicit root error field: `8e32bc881a4d499fff1aaac44c7b117f`. Its actual usage is 169 input + 238 output = 407 total tokens; client model latency is 8055.78 ms and whole-graph latency 8066.084 ms. `error` is null. Native generation duration is separate from provider-reported inference time and includes client-side overhead.

## Artifacts and reproduction

- [traces.json](traces.json): all 20 server-exported traces and observations.
- [bridge-trace.json](bridge-trace.json): full actual bridge trace.
- [summary.json](summary.json): batch result and audit lists.
- [verification.json](verification.json): independent snapshot/token/native-generation checks.
- [pytest.txt](pytest.txt): **67 passing tests** for the executed revision; metadata sidecar gives the source SHA and log hash.

```bash
python -m pytest -q
python -m ride_matcher.trace_batch --destination langfuse --provider-mode openrouter --source-commit 98c5804d18e90484023abf0d79b7f3a16469c40c --output-dir evidence/stage3-live-new-run
```

Configure your own private Langfuse/OpenRouter keys and regional URL. The temporary replacement OpenRouter key has the same one-hour expiry and $0 paid-credit limit as the expired key, and the client only accepts `:free` models. API secrets were scanned out of publication; neither `.env` nor keys are in this evidence. Reproduction creates new trace and generation IDs and depends on free-model availability/quota.
