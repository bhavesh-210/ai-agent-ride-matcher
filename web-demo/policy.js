/* Browser simulator of the published ETA policy, not a model or routing service. */
(function (root) {
  'use strict';
  function match(candidates, allowance, proposal = null) {
    if (!Number.isFinite(allowance) || allowance < 0) throw new Error('Pickup allowance must be finite and nonnegative.');
    const ids = new Set();
    for (const d of candidates) {
      if (typeof d.driver_id !== 'string' || !d.driver_id.trim() || ids.has(d.driver_id)) throw new Error('Driver IDs must be unique and nonempty.');
      ids.add(d.driver_id);
      if (!['available', 'offline', 'on_trip'].includes(d.status)) throw new Error('Unknown driver status.');
      if (d.road_eta_minutes !== null && (!Number.isFinite(d.road_eta_minutes) || d.road_eta_minutes < 0)) throw new Error('Road ETAs must be finite and nonnegative, or blank for a missing route.');
      if (!Number.isFinite(d.straight_line_distance_km) || d.straight_line_distance_km < 0) throw new Error('Map distances must be finite and nonnegative.');
    }
    const available = candidates.filter(d => d.status === 'available' && d.road_eta_minutes !== null);
    const ordered = [...available].sort((a, b) => a.road_eta_minutes - b.road_eta_minutes || (a.driver_id < b.driver_id ? -1 : a.driver_id > b.driver_id ? 1 : 0));
    const winner = ordered[0] || null;
    const eligible = available.filter(d => d.road_eta_minutes - winner.road_eta_minutes <= allowance);
    const accepted = !!winner && !!proposal && proposal.selected_driver_id === winner.driver_id && proposal.estimated_pickup_time_minutes === winner.road_eta_minutes;
    const verification = !winner ? 'no_candidates' : !proposal ? 'offline_deterministic_demo_no_api_call' : accepted ? 'model_verified' : 'model_overridden_by_eta_guard';
    return {
      selected_driver_id: winner ? winner.driver_id : null,
      estimated_pickup_time_minutes: winner ? winner.road_eta_minutes : null,
      eligible_driver_ids: eligible.map(d => d.driver_id),
      verification,
      proposal_accepted: accepted,
      evaluated_candidates: candidates.map(d => {
        let outcome, reason;
        if (d.status !== 'available') { outcome = 'excluded'; reason = 'Status ' + d.status + '; unavailable before the proposal.'; }
        else if (d.road_eta_minutes === null) { outcome = 'excluded'; reason = 'No supplied route ETA.'; }
        else if (!eligible.includes(d)) { outcome = 'excluded'; reason = 'Outside the configured pickup allowance.'; }
        else if (d === winner) { outcome = 'selected'; reason = 'Lowest road ETA; equal times use driver ID ascending.'; }
        else { outcome = 'not_selected'; reason = 'A faster eligible driver or the deterministic tie-break won.'; }
        return {...d, outcome, reason};
      })
    };
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {match};
  else root.RoadwisePolicy = {match};
})(typeof window !== 'undefined' ? window : globalThis);
