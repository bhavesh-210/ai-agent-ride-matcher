'use strict';
const $ = id => document.getElementById(id);
let snapshot, traces, currentTrace, sandboxSeed;
const guideText = [
  'Offline and on-trip drivers are removed first. Only available drivers with a usable route can compete.',
  'DRV-52907 looks closer at 1.03 km, but a bridge-ramp detour makes its road ETA 16 minutes. DRV-16643 is 1.14 km away and needs only 4 minutes. At zero extra wait, only the fastest route reaches the model.',
  'The model only proposes. Python checks the returned ID and ETA against the eligible set and deterministic minimum. A 16-minute, unavailable or invented driver is rejected; code keeps the 4-minute winner without another model call.'
];
function cell(row, value) {
  const td = document.createElement('td'); td.textContent = value; row.appendChild(td); return td;
}
function renderCandidates(match) {
  $('rows').replaceChildren();
  for (const d of match.evaluated_candidates) {
    const row = document.createElement('tr'); row.dataset.driver = d.driver_id; row.dataset.status = d.status;
    if (d.outcome === 'selected') row.className = 'selected';
    cell(row, d.driver_id); cell(row, d.status); cell(row, d.straight_line_distance_km.toFixed(2) + ' km');
    cell(row, d.road_eta_minutes === null ? 'No route' : d.road_eta_minutes + ' min');
    const td = cell(row, ''); const pill = document.createElement('span'); pill.className = 'pill';
    pill.textContent = d.outcome.replace('_', ' '); td.appendChild(pill); cell(row, d.reason); $('rows').appendChild(row);
  }
}
function traceMetric(label, value) {
  const box = document.createElement('div'); box.className = 'evidence-item';
  const small = document.createElement('small'); small.textContent = label;
  const strong = document.createElement('strong'); strong.textContent = value;
  box.append(small, strong); $('trace-metrics').appendChild(box);
}
function renderTrace(id) {
  currentTrace = traces.traces[id]; $('trace-metrics').replaceChildren();
  if (!currentTrace) { $('trace-model-reason').textContent = 'No recorded trace is available for this request.'; $('trace-json').textContent = ''; $('download-trace').disabled = true; return; }
  $('download-trace').disabled = false;
  const out = currentTrace.output;
  traceMetric('Request', id);
  traceMetric('Recorded model', out.model || 'Skipped: no candidates');
  traceMetric('Tokens · input / output', out.tokens ? out.tokens.input + ' / ' + out.tokens.output : 'No model call');
  traceMetric('Graph / client model time', out.latency_ms.toFixed(1) + ' / ' + (out.model_latency_ms === null ? '—' : out.model_latency_ms.toFixed(1)) + ' ms');
  $('trace-model-reason').textContent = out.model_rationale || 'No model explanation exists: this request had no eligible candidates, so the model call was skipped.';
  const names = [...new Set([...currentTrace.observations].sort((a, b) => a.startTime.localeCompare(b.startTime)).map(o => o.name))];
  $('trace-stages').textContent = 'Checked candidates: ' + (currentTrace.checked_candidate_ids.join(', ') || 'none; model skipped') + '. Recorded observations: ' + names.join(' · ');
  $('trace-provenance').textContent = 'Trace ' + currentTrace.trace_id + ' · archived source ' + currentTrace.source_commit.slice(0, 7) + ' · verification: ' + out.verification + ' · error: ' + (out.error === null ? 'null (no error)' : out.error) + '. Times belong to that historical run, not this page.';
  $('trace-json').textContent = JSON.stringify(currentTrace, null, 2);
}
function renderRide() {
  const data = snapshot.results[$('ride').value], match = data.match;
  $('request').textContent = data.request_id + ' · RECORDED SNAPSHOT';
  $('winner').textContent = match.selected_driver_id ? 'Selected ' + match.selected_driver_id : 'No eligible driver';
  $('eta').textContent = match.estimated_pickup_time_minutes === null ? '—' : match.estimated_pickup_time_minutes + ' min';
  renderCandidates(match); $('reason').textContent = match.decision_rationale;
  $('status').textContent = match.selected_driver_id ? 'Recorded result · deterministic road ETA selection · ' + match.accepted_extra_pickup_minutes + ' extra minutes allowed' : 'No match · exact request ID has no usable available candidates; no assignment invented.';
  renderTrace(data.request_id);
  document.querySelectorAll('[data-guide]').forEach(b => b.setAttribute('aria-pressed', 'false'));
}
function showGuide(step) {
  if (!snapshot) return;
  $('ride').value = 'RQ-0303-002'; renderRide(); $('guide-copy').textContent = guideText[step];
  document.querySelectorAll('[data-guide]').forEach(b => b.setAttribute('aria-pressed', String(Number(b.dataset.guide) === step)));
  document.querySelectorAll('#rows tr').forEach(row => {
    const highlight = step === 0 ? row.dataset.status !== 'available' : step === 1 ? row.dataset.driver === 'DRV-52907' : row.dataset.driver === 'DRV-16643';
    if (highlight) row.classList.add('guide-row');
  });
}
function resetSandbox() {
  $('sandbox-rows').replaceChildren(); $('proposal-mode').value = 'fastest';
  for (const d of sandboxSeed) {
    const row = document.createElement('tr'); row.dataset.driver = d.driver_id;
    cell(row, d.driver_id);
    const select = document.createElement('select'); select.setAttribute('aria-label', d.driver_id + ' status');
    for (const status of ['available', 'offline', 'on_trip']) { const o = document.createElement('option'); o.value = status; o.textContent = status; select.appendChild(o); }
    select.value = d.status; cell(row, '').appendChild(select); cell(row, d.straight_line_distance_km.toFixed(2) + ' km');
    const input = document.createElement('input'); input.type = 'number'; input.min = '0'; input.step = 'any'; input.value = d.road_eta_minutes === null ? '' : String(d.road_eta_minutes);
    input.setAttribute('aria-label', d.driver_id + ' road ETA'); cell(row, '').appendChild(input); $('sandbox-rows').appendChild(row);
  }
  simulate();
}
function simulate(event) {
  if (event) event.preventDefault();
  $('sandbox-error').textContent = '';
  try {
    const candidates = [...document.querySelectorAll('#sandbox-rows tr')].map((row, i) => ({...sandboxSeed[i], status: row.querySelector('select').value, road_eta_minutes: row.querySelector('input').value === '' ? null : Number(row.querySelector('input').value)}));
    const allowance = snapshot._provenance.default_accepted_extra_pickup_minutes;
    const base = RoadwisePolicy.match(candidates, allowance);
    let proposed;
    if ($('proposal-mode').value === 'fastest') proposed = candidates.find(d => d.driver_id === base.selected_driver_id);
    if ($('proposal-mode').value === 'closest') proposed = [...candidates].filter(d => d.status === 'available' && d.road_eta_minutes !== null).sort((a, b) => a.straight_line_distance_km - b.straight_line_distance_km || a.driver_id.localeCompare(b.driver_id))[0];
    if ($('proposal-mode').value === 'unavailable') proposed = candidates.find(d => d.status !== 'available');
    if ($('proposal-mode').value === 'invented') proposed = {driver_id: 'DRV-INVENTED', road_eta_minutes: 0};
    const proposal = proposed ? {selected_driver_id: proposed.driver_id, estimated_pickup_time_minutes: proposed.road_eta_minutes} : null;
    const result = RoadwisePolicy.match(candidates, allowance, proposal);
    $('sandbox-winner').textContent = result.selected_driver_id ? 'Selected ' + result.selected_driver_id + ' · ' + result.estimated_pickup_time_minutes + ' min' : 'No eligible driver · no assignment';
    $('sandbox-proposal').textContent = proposal ? 'Simulated proposal: ' + proposal.selected_driver_id + ' at ' + proposal.estimated_pickup_time_minutes + ' min.' : 'No simulated proposal is available for this scenario.';
    $('sandbox-guard').textContent = !result.selected_driver_id ? 'Model call would be skipped: no available driver has a usable route.' : !proposal ? 'Deterministic minimum selected. No model call was made.' : result.proposal_accepted ? 'Guard accepted: the proposed driver and ETA match the deterministic minimum.' : 'Guard rejected the proposal. Deterministic fallback keeps the fastest eligible driver; no second model call.';
    $('sandbox-shortlist').textContent = 'Checked model shortlist: ' + (result.eligible_driver_ids.join(', ') || 'empty') + ' · allowance: ' + allowance + ' extra minutes.';
  } catch (error) {
    $('sandbox-error').textContent = error.message;
    $('sandbox-winner').textContent = 'Scenario rejected'; $('sandbox-proposal').textContent = '';
    $('sandbox-guard').textContent = 'Correct the input before comparing drivers.'; $('sandbox-shortlist').textContent = '';
  }
}
$('run').disabled = true; $('reset-sandbox').disabled = true;
$('run').addEventListener('click', renderRide);
$('ride').addEventListener('change', renderRide);
document.querySelectorAll('[data-guide]').forEach(b => b.addEventListener('click', () => showGuide(Number(b.dataset.guide))));
$('sandbox-form').addEventListener('submit', simulate);
$('reset-sandbox').addEventListener('click', resetSandbox);
$('download-trace').addEventListener('click', () => {
  if (!currentTrace) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(currentTrace, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = currentTrace.request_id + '-recorded-trace-excerpt.json'; link.click(); URL.revokeObjectURL(url);
});
(async () => {
  try {
    const responses = await Promise.all([fetch('./snapshot.json'), fetch('./traces.json')]);
    if (responses.some(r => !r.ok)) throw new Error('Unable to load recorded evidence. Please refresh.');
    [snapshot, traces] = await Promise.all(responses.map(r => r.json()));
    $('ride').replaceChildren();
    for (const id of Object.keys(snapshot.results)) {
      const option = document.createElement('option'); option.value = id;
      option.textContent = id + (id === 'RQ-0303-002' ? ' · Bridge' : id === 'RQ-0308-018' ? ' · Missing candidates' : ''); $('ride').appendChild(option);
    }
    sandboxSeed = snapshot.results['RQ-0303-002'].match.evaluated_candidates.map(d => ({driver_id: d.driver_id, status: d.status, road_eta_minutes: d.road_eta_minutes, straight_line_distance_km: d.straight_line_distance_km}));
    showGuide(0); resetSandbox(); $('run').disabled = false; $('reset-sandbox').disabled = false;
  } catch (error) { $('status').textContent = error.message; $('trace-model-reason').textContent = 'Evidence could not be loaded.'; }
})();
