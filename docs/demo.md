# Demo walkthrough

**Public resume link:** [https://roadwise-bhavesh-demo.scenicboat64.chatgpt.site/](https://roadwise-bhavesh-demo.scenicboat64.chatgpt.site/)

The public page replays recorded outputs from the Python graph. It needs no installation, sign-in or API keys. The steps below also work in the local FastAPI demo, which executes the graph on demand.

Start the server using the README, then open http://127.0.0.1:8000.

1. Run the default bridge case, `RQ-0303-002`. Compare the geographically closer 16-minute driver with the selected 4-minute driver.
2. Read the candidate reasons. The bridge detour is already reflected in the supplied routing ETA; no invented bridge penalty is added.
3. Switch rides and confirm unavailable candidates are excluded.
4. Choose `RQ-0308-018`: no assignment is invented for the mismatched source ID.
5. Open `/docs` to inspect the live REST contract. The visual demo is offline; it does not pretend to make a model call.

## Live API request

With OpenRouter configured privately in `.env`, prepare the existing example request:

```bash
python - <<'PY'
import json
from pathlib import Path
requests = json.loads(Path('data/requests.example.json').read_text())
drivers = json.loads(Path('data/drivers.example.json').read_text())
request = next(r for r in requests if r['request_id'] == 'bridge-001')
Path('/tmp/ride-request.json').write_text(json.dumps({
    'request': request,
    'all_candidates': [d for d in drivers if d['request_id'] == request['request_id']]
}))
PY
curl -i -X POST http://127.0.0.1:8000/match \
  -H 'Content-Type: application/json' --data-binary @/tmp/ride-request.json
```

This JSON example is a **separate synthetic fixture**, not the 16-versus-4-minute CSV bridge case. Its winner is `farther-same-bank` at 5 minutes. If Langfuse is configured, the response includes `X-Trace-Id`. A provider failure returns the deterministic winner and an explicit fallback verification value; it is not reported as a successful model call.

## Record a short project video

Show the bridge comparison, candidate audit, no-match ride, passing tests and saved live trace in that order. Say that the UI uses snapshot estimates and the historical live export is separately versioned. No provider account, key or billing page needs to appear on screen.

## Guided public walkthrough

- Read the three short problem/approach/proof cards.
- Click each bridge walkthrough step to see which candidate rows it explains.
- Pick a recorded request. Its trace panel updates to the same request, with actual archived model prompt, shortlisted IDs, token usage, model reason and timings. Download is a curated excerpt; the full original export remains linked.
- In the separate browser simulator, select **Nearest available car**: the default 16-minute proposal is rejected and the 4-minute driver wins. Try changing availability, entering zero minutes, leaving a route blank, or making all drivers unavailable.
- Sandbox edits never alter the historical evidence. [Project scope and remaining production work](project-readiness.md).
