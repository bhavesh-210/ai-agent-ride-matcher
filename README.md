# AI Agent Ride Matcher

A two-node LangGraph workflow that filters unavailable drivers before calling OpenRouter, then independently verifies the model's choice against supplied road pickup minutes. Every original candidate has a human-readable audit entry.

Public repository: https://github.com/bhavesh-210/ai-agent-ride-matcher

## Submission status

- Implemented: LangGraph, Pydantic v2 validation, immutable state updates, OpenRouter integration, ETA guard, per-candidate audit, CLI, and optional FastAPI.
- Assignment CSVs loaded, validated and published with explicit authorization: **20 requests and 80 candidate rows**.
- **54 tests pass**, including pre-model pickup policy enforcement, the actual bridge detour, unavailable drivers, all-request evaluation, and source-ID mismatch.
- Actual-data offline evaluation: **19 matches, 1 unmatched request, 7 strict ETA improvements over the nearest available driver**.
- Successful live OpenRouter run and matching Activity/Logs screenshots are committed. The actual post-build Claude Code Plan Mode review is now documented below; the repository-copy launch-command screenshot and reviewer acceptance remain pending.
- Evidence files containing `offline` or `offline_assignment_evaluation_no_api_call` are explicitly NOT live API evidence.
- Langfuse is deferred; no Langfuse tracing is claimed.

## Install and verify

Python 3.11+; run from the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python -m ride_matcher.evaluate
```

## Actual-data evaluation

The private assignment files contain 20 requests and 80 driver rows. Local evaluation produces 19 matches and one unmatched request. Four candidate rows use a request ID absent from the requests file. IDs are joined exactly; the matcher never guesses a correction.

Seven requests have a strictly faster road ETA than the nearest available driver. In the actual bridge example, the closer available driver takes 16 minutes due to a bridge-ramp detour; a farther available driver takes 4 minutes and wins. A separate freight/rail case chooses a 3-minute driver over a nearer 9-minute driver. Source flags are not used to rank candidates.

An aggregate report is published in `evidence/assignment-summary.json`. The user explicitly authorized public publication of the supplied assignment CSVs and detailed offline audit outputs. They are included in this repository; API credentials remain excluded.

To reproduce locally, place the request CSV at `data/source/requests.csv` and the candidate CSV at `data/source/drivers.csv`, then run:

```bash
python -m ride_matcher.evaluate
```

For a single request, use its actual request ID in the commands below.

## Real OpenRouter API run — required before submission

Create/save your key privately at https://openrouter.ai/workspaces/default/keys . It must remain in your local gitignored `.env` and must never be pasted into a README, screenshot, commit or command argument.

```bash
cp .env.example .env
python -m ride_matcher --list-models
```

Edit `.env` locally, setting `OPENROUTER_API_KEY` and an available `OPENROUTER_MODEL` ID ending `:free`. Do not assume old model slugs still exist. Free models may have quota or availability limits.

```bash
python -m ride_matcher --requests data/source/requests.csv --drivers data/source/drivers.csv --request-id YOUR_REQUEST_ID --output evidence/live-run.json
```

Success requires `verification: model_verified`, the actual returned/requested model IDs, generation ID, UTC timestamps and latency. A failed call or incorrect proposal produces visible fallback and nonzero CLI exit status; that does not satisfy the required successful call.

After the successful run, open https://openrouter.ai/activity and locate that call. Match the recorded UTC time (convert to the page timezone), model and generation metadata. Save a genuine screenshot as `evidence/openrouter-activity.png`, cropping unrelated account details without hiding the required evidence. Then add:

```markdown
![OpenRouter Activity evidence](evidence/openrouter-activity.png)
```

Review the live JSON and screenshot for identifiers or location data before publishing. Detailed live JSON is gitignored by default; publish a sanitized version or obtain explicit source-data publication authorization. The committed screenshots and live JSON are genuine records of the verified run described below.

## Verified live submission evidence

Executed on **11 November 2026 at 10:27 UTC / 15:57 IST** using `liquid/lfm-2.5-2.6b:free`.

- Request: `RQ-0303-002`.
- Winner: `DRV-16643`, available, **4 minutes**.
- Closer available alternative: `DRV-52907`, **16 minutes**.
- Verification: `model_verified`; offline and on-trip profiles were removed before the call.
- Generation ID: `gen-1794392855-fCmEANln4i1mJWadCRdR`.
- Client elapsed time: 13,659.24 ms; this includes network/API overhead and is distinct from provider latency shown in OpenRouter.
- OpenRouter Logs display Nov 11, 03:57 PM in GMT+5:30, matching the UTC timestamps in [live-run.json](evidence/live-run.json).
- OpenRouter reports **$0.00** cost for this call.
- The temporary API key has a one-hour expiry and a $0 credit limit. Its secret is kept only in a private gitignored `.env`, never in source or published evidence. Configure your own key to reproduce after expiry.

OpenRouter's current UI separates aggregate Activity from individual Logs, so both views are included.

![OpenRouter Activity overview](evidence/openrouter-activity.png)

![OpenRouter call timestamp and model](evidence/openrouter-call.png)

![OpenRouter matching generation details](evidence/openrouter-generation.png)

## Source data and explicit mapping

The supplied assignment files are preserved byte-for-byte as `data/source/requests.csv` and `data/source/drivers.csv`. Their original titles are:

- Uber Ride Requests Test Set (week of 3-9 March 2025).csv
- Uber Candidate Drivers Snapshot (week of 3-9 March 2025).csv

| Source CSV fields | Validated model fields |
|---|---|
| pickup_lat, pickup_lng | pickup_coordinates.lat, pickup_coordinates.lon |
| driver_lat, driver_lng | coordinates.lat, coordinates.lon |
| driver_status | status |
| straight_line_km | straight_line_distance_km |
| road_pickup_minutes | actual_pickup_time_minutes |
| request_id, driver_id, rider_id | Preserved verbatim |
| route_note | Preserved in canonical candidate audit |

Source timestamps, zones, river sides and scenario flags remain in the original CSVs. They do not override the numeric road ETA or status. Missing road ETA is unavailable for ranking; zero is a valid ETA. JSON example input remains supported. Input-byte hashes and dataset join warnings are saved with individual CLI run evidence.

### Data quality findings and gap pushed back on

One request has no matching candidate ID and four candidate rows reference an absent request ID. The matcher returns no match and reports orphan rows instead of silently repairing the source. The `distance_time_disagree` flags conflict with strict numeric ETA improvement on 10 joinable requests; numeric road times and available status are authoritative.

“Guaranteed pickup time” cannot be promised by a historical snapshot or LLM. The guard guarantees selection of the lowest supplied ETA among eligible routable candidates, not actual physical arrival. Historical status is not live availability. Production dispatch requires fresh routing/status and atomic reservation.

Seven requests show a strict ETA improvement; equal-ETA ties are not counted as improvements. Detailed offline per-request reports are published in `evidence/assignment-evaluation.json`, with individual samples in `evidence/assignment-bridge-offline.json` and `evidence/assignment-sample-offline.json`. These are not live API evidence.

## Two-node architecture

```mermaid
flowchart TD
    S["Request and snapshot"] --> F["Filter available drivers"]
    F --> M["OpenRouter matcher and ETA guard"]
    M --> R["Match and full candidate audit"]
```

Node 1 checks the request-specific snapshot rows, keeps only available drivers with usable routes, and enforces the configured extra pickup allowance before OpenRouter receives candidates. Node 2 requests a structured OpenRouter proposal, checks the driver ID and copied ETA against a deterministic minimum, and produces the audit. Equal road ETAs use driver_id ascending; distance never determines ranking or ties.

### One pickup policy setting

The single project policy value is `accepted_extra_pickup_minutes` in [`config/matching.json`](config/matching.json), currently **0**. The graph, CLI, API and all-request contract tests read it through `MatchingConfig.from_env()`. An optional `ACCEPTED_EXTRA_PICKUP_MINUTES` environment override uses the same loader; `.env.example` leaves this override commented out. Negative, nonfinite and malformed config values fail validation.

The allowance is **extra minutes relative to the fastest available routable driver's supplied road ETA**, not an absolute pickup-time limit. Before the model call, a candidate must satisfy `candidate_ETA - fastest_ETA <= accepted_extra_pickup_minutes`. The boundary is inclusive; missing routes are excluded and zero ETA is valid. Every excluded original candidate retains an audit reason, and the result records the effective config value.

With the default zero allowance, only the fastest candidates reach the model. A nonzero allowance widens the shortlist for evaluation, but the final ETA guard still requires the deterministic fastest driver, with driver ID ascending for equal ETAs. No slower model proposal is accepted. Invalid proposals are recorded and overridden without a second model call; no eligible route returns no match and skips the model.

For the actual bridge request `RQ-0303-002`, the snapshot marks `DRV-16643` available with a 4-minute ETA. `DRV-52907` is geographically closer but takes 16 minutes. The zero-minute allowance removes the 16-minute driver before OpenRouter, and an adversarial test proves that even a model proposal naming that removed driver is overridden.

Run `python -m pytest -q` to reproduce **54 passing tests**. `tests/test_pickup_policy.py` covers the config boundary, invalid config, environment loading, unavailable and invented picks, slower picks inside a wider shortlist, zero-ETA ties, and the actual 16-versus-4-minute snapshot case. These tests use deterministic provider doubles and do not make API calls. The prior live OpenRouter evidence predates this policy change; no new live run or Langfuse trace is claimed.

Pydantic models are frozen, candidate collections are tuples, and state updates and final graph output are explicitly validated. Duplicate driver IDs within a request, cross-request candidates, invalid statuses, negative ETAs and nonfinite numbers are rejected.

Unavailable profiles and rider identity are not sent to the model. Incorrect model proposals are retained but visibly overridden. Model rationale is an untrusted proposal; the canonical audit is produced from validated metrics. Provider failure logs do not contain response bodies, credentials or request headers.

## Stage 2 pre-model tools and verification

Exactly two graph nodes remain. Node 1 calls three deterministic Python tools in [`ride_matcher/tools.py`](ride_matcher/tools.py):

1. `check_availability`: reads the snapshot status; only `available` passes.
2. `estimate_pickup_time`: reads validated `road_pickup_minutes` via the explicit CSV mapping; returns no route for missing values. It does not estimate time from distance or invent traffic.
3. `check_eligibility`: applies availability, route presence and the inclusive shared extra-minute allowance relative to the fastest available route.

All three execute before Node 2 calls OpenRouter. These are graph-invoked Python tools, not optional LLM-requested checks. The mocked HTTP contract test records every tool call and inspects the actual provider messages, proving that the outgoing candidate IDs exactly equal the checked set. [Captured provider prompt](evidence/stage2-prompt-preview.json) is explicitly **mock transport evidence, not a new live call**.

The key prompt requires a fixed JSON response with `selected_driver_id`, `estimated_pickup_time_minutes`, and `decision_rationale`, copied road ETA, and driver-ID tie-breaking. Code rejects IDs outside the checked list, incorrect ETAs and nonminimum picks. It retains the proposal, uses the deterministic road-ETA winner and records the override. Straight-line distance does not rank or break ties.

### Shared threshold and reason

The project setting is **0 extra minutes**: with no supplied rider preference justifying extra delay, the fastest available road ETA is required. Tests for all requests load the same project setting; they do not duplicate a threshold constant. Separate boundary tests deliberately supply alternative configs to test inclusive boundaries and prove that widening the shortlist cannot weaken the final fastest-driver guard.

### Actual test/fix log

This is the actual sequence for this stage, not a reconstructed claim of earlier failures:

| Run / finding | Cause | Fix made or rejected, and why |
|---|---|---|
| Previous stage: 33 tests passed | Existing inline checks lacked the newly required named tools | Added a new contract suite before refactoring; prior passing tests alone did not prove this requirement. |
| First new-suite run: collection error, `cannot import name tools` | The three checks still lived inline and `ride_matcher/tools.py` did not exist | Added the three tool functions and wired all three into Node 1 before OpenRouter. [Original output](evidence/stage2-first-pytest.txt). |
| Second run: collection error, `request is a reserved name` | New parameterized test used pytest's reserved fixture name | Renamed the test parameter to `ride_request`. [Original output](evidence/stage2-second-pytest.txt). |
| Source join finding: `RQ-0308-018` has no candidates; four rows reference `RQ-0309-018` | Request IDs differ between supplied files | Rejected silently relabeling source rows: there is no authoritative correction. Preserve IDs, report the anomaly and return an explicit no-match. |
| Final run: **54 passed, 1 warning** | All implemented matching contracts pass | [Full output](evidence/stage2-final-pytest.txt). The remaining warning comes from the installed anyio pytest plugin's deprecated pytest alias, not a matcher failure. |

No assignment mismatch failure is claimed for the collection-error runs: collection stopped before assignments could execute. No failures or timestamps have been invented. The prior planning review and this work occurred after the original build.

### Three assignments checked against the snapshot

| Request | Selected driver | Snapshot status | Selected road ETA | Nearest available road ETA | Decision |
|---|---|---|---:|---:|---|
| `RQ-0303-001` | `DRV-20417` | available | 3 min | 3 min | Retain: already the minimum road ETA. |
| `RQ-0303-002` | `DRV-16643` | available | 4 min | 16 min (`DRV-52907`) | Retain 4-minute winner; reject closest-looking bridge driver and extra bridge penalties because detour is already in supplied ETA. |
| `RQ-0304-005` | `DRV-47038` | available | 4 min | 8 min (`DRV-26148`) | Retain faster road-ETA assignment; reject distance-based ranking. |

These comparisons were reproduced from the source rows and current offline outputs; no source data was changed. [All-request report and per-candidate audit](evidence/stage2-request-validation.json).

### All 20 requests and the explicit data exception

The parameterized contract suite exercises all **20** request IDs. For every request with available routable source rows it asserts exactly one selected available driver, an ETA within the shared allowance and equality to the minimum road ETA. It also verifies the checked provider inputs and a single-call deterministic fallback. The bridge trap has a separate actual-data adversarial model test.

**19 requests produce one valid match. `RQ-0308-018` produces an explicit no-match because of the source-ID mismatch above.** It would be dishonest to claim 20 successful assignments from these files. The remaining one-per-request requirement depends on an authoritative dataset correction; it is not hidden, skipped or fixed by guessing.

Reproduce from the repository root (no API key or network needed):

```bash
python -m pytest -q
python -m ride_matcher.validate_submission
```

The second command regenerates the offline request audits and captured mocked prompt. Langfuse tracing is still deferred to the next stage; no new live API run is claimed.

## Planning evidence

This review ran **after the original implementation already existed**, on a separate repository copy, using **Claude Code CLI in Plan Mode with local Ollama `qwen3:8b`**. It was not an Anthropic-hosted Claude model and was not planning before the original build.

The original-plan screenshot shows **done 5:29 PM**; the revised-plan screenshot shows **done 5:34 PM**. No calendar date or timezone is inferred from filenames or system settings.

[Read the actual planning evidence, excerpts and limitations](evidence/planning-review.md).

### Original proposal and actual pushback

The original plan proposed “bridge detour weight,” “Lowest bridge detour weight,” and “Most recent activity,” together with an extra risk calculation. These were invented inputs beyond the supplied road pickup minutes.

**The gap I objected to:** the model's selected driver must be independently checked against the eligible routable candidate set and the deterministic minimum supplied ETA. In the bridge case, an unchecked proposal could choose the closer **16-minute** driver over the **4-minute** driver. Supplied road times already account for bridge detours.

The screenshot of the actual pushback requests removal of invented ranking inputs and validation of eligible membership, copied ETA and deterministic minimum, with an audited fallback for invalid proposals. The revised plan states:

> Ensures selected driver exists in filtered list

> Confirms ETA matches driver's road_pickup_minutes

> Verifies ETA is deterministic minimum

![Original plan before pushback — terminal shows done 5:29 PM](evidence/plan-original.webp)

![Actual pushback and revised plan — terminal shows done 5:34 PM](evidence/plan-revised.webp)

### Terminal proof and remaining limitation

[Repository-copy terminal screenshot](evidence/plan-terminal.webp) shows `~/ai-agent-ride-matcher-plan-review`, `qwen3:8b` and `plan mode on`.

[Earlier launch-command screenshot](evidence/plan-launch-command.webp) shows `ollama launch claude --model qwen3:8b -- --permission-mode plan` and Plan Mode, but in the home folder. It is an earlier session, not evidence of the later repository-copy launch command. A screenshot of that later session's own launch command remains pending. Reviewer acceptance is not claimed.

## Optional local API

```bash
uvicorn ride_matcher.api:app --reload
```

Use http://127.0.0.1:8000/docs, POST `/match` with `{ "request": <request object>, "all_candidates": [<driver objects>] }`. Derived state fields are rebuilt. Credentials come from the server environment. This is an unauthenticated local development endpoint, not production dispatch. It does not reserve drivers or prevent concurrent double dispatch; those require atomic storage operations and fresh status checks.

## Remaining submission checklist

- [x] Public GitHub repository with source and README
- [x] Explicit CSV loader and private validation of actual assignment files
- [x] Explicit authorization received; source CSVs and detailed offline audits published
- [x] Two-node graph with pre-model availability filter
- [x] Road ETA guard, bridge test and complete audit
- [x] Offline run on actual data, all-request evaluation, and public aggregate summary
- [x] Temporary key configured privately; `liquid/lfm-2.5-2.6b:free` selected
- [x] Successful live API run with `model_verified`
- [x] Matching genuine OpenRouter Activity and generation screenshots committed
- [x] Actual post-build Claude Code Plan Mode screenshots and excerpts added, with Ollama model and visible times disclosed
- [ ] Repository-copy session's own launch-command screenshot
- [ ] Reviewer acceptance of planning evidence

Before any local commit, `git check-ignore .env` should print `.env`, and `git ls-files .env` should print nothing. Never commit an API key. The included `.env.example` contains no credentials.

Validation: 54 tests pass locally on Python 3.12 with the committed assignment CSVs. Tests include synthetic and actual bridge cases, pre-model pickup allowance, ETA/availability invariants across all requests, source-ID mismatch, malformed proposals, provider failure and mocked HTTP integration. Mocked integration is not proof of a live call. `requirements-tested.txt` records directly used versions; `requirements.txt` defines compatible ranges.
