# Verification

## Guided demo update

The expanded public demo passed **117 pytest cases on both Python 3.11 and 3.12** in [GitHub Actions](https://github.com/bhavesh-210/ai-agent-ride-matcher/actions/runs/43509181054), from source `1b8553afc7fadb0cda2db6e7e2e5717ab1a8925a`. [Local raw log](../evidence/guided-demo/pytest.txt) · [Source metadata](../evidence/guided-demo/pytest.txt.metadata.json). Four new tests cover 60 browser/Python policy parity scenarios, invalid browser inputs, complete static assets and exact preservation of archived prompts/shortlists. All 20 request/trace views passed DOM checks. Cloud-browser checks covered the bridge guide, rejected nearest-car proposal, availability changes, zero and negative ETAs, and the empty eligible set. The [current CI workflow](https://github.com/bhavesh-210/ai-agent-ride-matcher/actions/workflows/tests.yml) verifies the committed version on Python 3.11 and 3.12.

The public page remains a recorded-evidence viewer and browser policy simulator. No new real OpenRouter call or hosted trace upload is claimed. [Remaining production work](project-readiness.md).

## Archived portfolio hardening

The portfolio update was checked with **113 passing pytest cases** on Python 3.12. Tests include all 20 recorded live trace replays, concurrent API trace headers, explicit no-match handling, provider failure fallback, auditor corruption cases and nonzero-shortlist bridge export.

| Check | Result |
|---|---|
| Pytest | 113 passed |
| Saved live trace replay | 20 traces; zero outcome or candidate-audit mismatches |
| Stronger saved-export field audit | 20 traces; no missing required fields or incomplete model records |
| Offline benchmark | 19 matches; 113 → 60 supplied ETA minutes; 46.9% aggregate reduction |
| Demo API coverage | All 20 snapshot request routes returned results |
| Demo DOM interaction | All 20 selectors/results rendered correctly; no script errors |
| Diagram | SVG rendered and visually inspected |

DOM interaction was checked with jsdom against actual demo API results. A headless Chromium attempt was blocked by this review environment's socket restrictions, so this is **not a completed real-browser layout/responsiveness check**. The demo includes responsive CSS, but desktop/mobile visual checking remains a manual step.

No new real OpenRouter calls or hosted Langfuse uploads were performed for this update. API trace integration was verified with the real SDK and an in-memory exporter. The separately archived live batch remains tied to its original source commit. The GitHub Actions matrix is configured for Python 3.11 and 3.12; its actual run status is shown by the repository badge.

Tested source: [`68fd4c8`](https://github.com/bhavesh-210/ai-agent-ride-matcher/commit/68fd4c8debcc014093efd4a025633bfd7b4301b0). All **36 runtime, test, config and data files** in a separate clean test directory matched their published blob hashes. [Fresh verification record](../evidence/portfolio-final/verification.json) · [Raw pytest output](../evidence/portfolio-final/pytest.txt) · [Log provenance](../evidence/portfolio-final/pytest.txt.metadata.json).

[GitHub Actions run](https://github.com/bhavesh-210/ai-agent-ride-matcher/actions/runs/43498001458): **113 tests passed on both Python 3.11 and 3.12**; both snapshot benchmark jobs passed.

The initial local-only record at source `98f1726` is superseded: CI caught an omitted demo HTML asset in the first published tree. That asset was added before the clean-checkout verification. The first failing CI run and the correction are retained in history. Original assignment/live evidence was not edited.
