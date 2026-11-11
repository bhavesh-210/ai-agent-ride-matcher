# Stage 3 local SDK export — not hosted Langfuse evidence

Stage: `stage-3-tracing`. Instrumented code commit: `d218193fa5bcbe199ff47c4cf19926d02d70dc96`.

The real Langfuse Python SDK produced 20 distinct ride traces and 288 observations using an in-memory OpenTelemetry exporter. The provider mode was `offline`: no new OpenRouter call and no Langfuse server upload occurred. All exports say `hosted_read_verified: false`.

- `traces.json`: complete 20-request local SDK export, grouped by trace ID, ready for replay work.
- `bridge-trace.json`: the actual bridge trace extracted from that export; 4-minute winner, 16-minute alternative excluded, road detour note and full audit.
- `summary.json`: 20 traces, 19 matches, one explicit source-ID no-match; bridge explanation check passed.
- `pytest.txt`: actual output, 62 passing tests. Its metadata file identifies the source commit and content hash.

Do not use these files as proof of hosted Langfuse ingestion. Hosted export is still pending private project credentials. The batch command flushes and then reads complete observations from the server before setting `hosted_read_verified: true`.
