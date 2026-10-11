import { useEffect, useState } from 'react'

export default function InspectionMode() {
  const [configuration, setConfiguration] = useState(null)
  const [effective, setEffective] = useState(null)
  const [draft, setDraft] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [timing, setTiming] = useState(null)
  useEffect(() => {
    let active = true
    async function refresh() {
      try {
        const response = await fetch('/api/inspection/config')
        if (!response.ok) throw new Error('Inspection settings are unavailable')
        const data = await response.json()
        if (active) {
          setConfiguration(data.config); setEffective(data.effective)
          setTiming(data.recommended_timing)
          setDraft((previous) => previous || data.config.nine_view)
        }
      } catch (problem) { if (active) setError(problem.message) }
    }
    refresh()
    const timer = window.setInterval(refresh, 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])
  async function save(patch) {
    setBusy(true); setError(''); setMessage('')
    try {
      const response = await fetch('/api/inspection/config', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...patch, expected_version: configuration.version }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not save inspection settings')
      setConfiguration(data.config); setDraft(data.config.nine_view); setMessage(data.message)
    } catch (problem) { setError(problem.message) }
    finally { setBusy(false) }
  }
  function field(name, label, step = 'any') {
    return <label>{label}<input type="number" step={step} value={draft?.[name] ?? ''}
      onChange={(event) => setDraft({ ...draft, [name]: event.target.value === '' ? null : Number(event.target.value) })} /></label>
  }
  return <section className="panel inspection-mode" aria-label="Inspection algorithm">
    <div className="panel-heading"><div><span className="eyebrow">INSPECTION METHOD</span><h2>Algorithm for entering fruit</h2></div>
      <span className="panel-caption">{configuration ? `CONFIGURATION ${configuration.version}` : 'CONNECTING'}</span></div>
    <div className="filter-tabs" role="group" aria-label="Algorithm for newly entering fruit">
      {[['surface_mapping', 'Surface mapping'], ['nine_view', 'Multiview grading']].map(([value, label]) =>
        <button key={value} type="button" aria-pressed={configuration?.algorithm === value}
          className={configuration?.algorithm === value ? 'selected' : ''} disabled={busy || !configuration}
          onClick={() => save({ algorithm: value })}>{label}</button>)}
    </div>
    <p className="evidence-note">Changes apply when fruit enter the inspection region. Active fruit finish with their assigned method and thresholds.</p>
    {timing && <button type="button" className="secondary-button" disabled={busy || !configuration}
      onClick={() => save({ algorithm: 'nine_view', nine_view: { ...timing, region: configuration.nine_view.region || effective?.nine_view.region || [0, 0, 1, 1] } })}>
      Use measured timing · {timing.required_views} views every {timing.snapshot_interval_seconds} seconds</button>}
    {configuration?.algorithm === 'nine_view' && <>
      <p className="evidence-note">Capture target: {configuration.nine_view.required_views ?? 9} views. Grade the captured snapshots using the worst supported view.</p>
      <p className="evidence-note">Calibration: {configuration.nine_view.calibration_status} ({configuration.nine_view.calibration_id}). {configuration.nine_view.calibration_status === 'experimental' ? 'Experimental thresholds produce provisional grades.' : 'Validated status refers to the supplied calibration record.'}</p>
      {!effective?.nine_view.region && <p className="upload-error" role="alert">Set an inspection region below or in Tracking performance to capture fruit snapshots.</p>}
    </>}
    {draft && <details className="map-details"><summary>Multiview acquisition and grading settings</summary>
      <form onSubmit={(event) => { event.preventDefault(); save({ nine_view: draft }) }}>
        <p className="evidence-note">Region coordinates are fractions from 0 to 1. Leave the region unset to reuse the Tracking performance region.</p>
        <div className="inspection-settings">
          <label>Snapshot selection<select value={draft.acquisition ?? 'progress_bins'} onChange={(event) => setDraft({ ...draft, acquisition: event.target.value })}>
            <option value="timed">Elapsed time</option><option value="progress_bins">Conveyor progress</option></select></label>
          {field('required_views', 'Views per fruit (4–9)', '1')}
          {field('snapshot_interval_seconds', 'Time between snapshots (seconds)')}
          {field('first_snapshot_delay_seconds', 'First snapshot delay (seconds)')}
          {field('snapshot_lateness_seconds', 'Allowed snapshot delay (seconds)')}
          {field('minimum_stream_change', 'Minimum conveyor image change (0 disables check)')}
          {field('conveyor_stop_grace_seconds', 'Conveyor stop grace (seconds)')}
          <label>Timing calibration record<input value={draft.timing_calibration_id ?? 'not_calibrated'} onChange={(event) => setDraft({ ...draft, timing_calibration_id: event.target.value })} /></label>
          {['Left', 'Top', 'Right', 'Bottom'].map((label, index) => <label key={label}>{label}<input type="number" min="0" max="1" step="0.01"
            value={draft.region?.[index] ?? ''} onChange={(event) => {
              const region = [...(draft.region || [0, 0, 1, 1])]
              region[index] = Number(event.target.value); setDraft({ ...draft, region })
            }} /></label>)}
          <label>Conveyor direction<select value={draft.direction} onChange={(event) => setDraft({ ...draft, direction: event.target.value })}>
            <option value="top_to_bottom">Top to bottom</option><option value="bottom_to_top">Bottom to top</option>
            <option value="left_to_right">Left to right</option><option value="right_to_left">Right to left</option></select></label>
          {field('class_1_max_defect_pct', 'Class 1 below defect %')}
          {field('class_2_max_defect_pct', 'Class 2 through defect %')}
          {field('minimum_instance_confidence', 'Minimum defect confidence')}
          {field('decision_deadline_seconds', 'Decision deadline after entry (seconds)')}
          {field('maximum_dwell_seconds', 'Maximum dwell (seconds)')}
          {field('expected_dwell_seconds', 'Expected dwell (optional seconds)')}
          {field('expected_fruit_rate', 'Expected arrivals (optional fruit/second)')}
          {field('minimum_crop_pixels', 'Minimum crop edge (pixels)', '1')}
          {field('minimum_blur_variance', 'Minimum blur variance')}
          {field('maximum_glare_fraction', 'Maximum glare fraction')}
          {field('maximum_occlusion_fraction', 'Maximum overlap fraction')}
          {field('track_loss_seconds', 'Track loss timeout (seconds)')}
          {field('minimum_mask_box_fraction', 'Minimum visible mask / box area')}
          {field('minimum_defect_pixels', 'Minimum supported defect pixels', '1')}
          <label>Contact sheet<select value={draft.contact_sheet ? 'on' : 'off'} onChange={(event) => setDraft({ ...draft, contact_sheet: event.target.value === 'on' })}>
            <option value="on">Save chronological contact sheet</option><option value="off">Individual evidence only</option></select></label>
          <label>Evidence files<select value={draft.evidence_level ?? 'full'} onChange={(event) => setDraft({ ...draft, evidence_level: event.target.value })}>
            <option value="contact_sheet">Contact sheet and view statistics</option><option value="full">All source crops, masks and overlays</option></select></label>
          <label>Calibration record<input value={draft.calibration_id} onChange={(event) => setDraft({ ...draft, calibration_id: event.target.value })} /></label>
          <label>Calibration status<select value={draft.calibration_status} onChange={(event) => setDraft({ ...draft, calibration_status: event.target.value })}>
            <option value="experimental">Experimental</option><option value="validated">Validated against labelled fruit</option></select></label>
        </div>
        <div className="camera-actions"><button type="button" className="secondary-button" onClick={() => setDraft({ ...draft, region: null })}>Reuse tracking region</button>
          <button className="primary-button" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save for entering fruit'}</button></div>
      </form>
    </details>}
    {message && <p className="refresh-message" role="status">{message}</p>}
    {error && <p className="upload-error" role="alert">{error}</p>}
  </section>
}
