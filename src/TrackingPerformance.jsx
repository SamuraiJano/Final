import { useEffect, useState } from 'react'

const labels = {
  id_fragmentation: 'ID Fragmentation', lost_track: 'Lost Track',
  mid_region_new_id: 'New Mid-region ID', possible_id_swap: 'Possible ID Swap',
  regional_continuity_drop: 'Regional Continuity Drop',
}
const exports = ['tracking_summary.csv', 'region_continuity.csv', 'checkpoint_crossings.csv', 'tracking_events.csv']
const pct = (value) => value == null ? '—' : `${Number(value).toFixed(1)}%`
const number = (value) => value == null ? '—' : Number(value).toLocaleString()
const decimal = (value) => value == null ? '—' : Number(value).toFixed(1)
const seconds = (value) => value == null ? '—' : `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 6 })} s`

async function json(url, options) {
  const response = await fetch(url, options)
  const result = await response.json()
  if (!response.ok) throw new Error(result.detail || `Request failed: ${response.status}`)
  return result
}

function RegionalChart({ regions }) {
  const [hovered, setHovered] = useState(null)
  const left = 56, top = 20, width = 810, height = 190
  const x = (p) => left + p * width / 100
  const y = (p) => top + height * (1 - p / 100)
  const region = regions[hovered]
  return <div className="tracking-chart">
    <div className="tracking-chart-canvas"><svg viewBox="0 0 900 260" role="group" aria-label="Regional ID Continuity across conveyor position, from zero to one hundred percent">
      {[0, 25, 50, 75, 100].map((p) => <g key={p}><line x1={left} x2={left + width} y1={y(p)} y2={y(p)} className="chart-grid" /><text x={left - 12} y={y(p) + 4} textAnchor="end">{p}</text></g>)}
      {[0, 20, 40, 60, 80, 100].map((p) => <text key={p} x={x(p)} y={top + height + 22} textAnchor="middle">{p}%</text>)}
      <text x="460" y="253" textAnchor="middle">Conveyor position (%)</text>
      <text transform="translate(12 120) rotate(-90)" textAnchor="middle">ID continuity (%)</text>
      {regions.map((r, index) => <g key={r.region_start_percent}>
        <rect x={x(r.region_start_percent)} y={top} width={x(r.region_end_percent) - x(r.region_start_percent)} height={height} className={r.evaluated ? 'chart-evaluated' : 'chart-unavailable'} />
        {r.continuity_percent != null && <line x1={x(r.region_start_percent)} x2={x(r.region_end_percent)} y1={y(r.continuity_percent)} y2={y(r.continuity_percent)} className={`chart-value ${r.region_pass ? '' : 'chart-drop'}`} />}
        <rect x={x(r.region_start_percent)} y={top - 5} width={x(r.region_end_percent) - x(r.region_start_percent)} height={height + 10} fill="transparent" tabIndex="0" role="button"
          aria-label={`${r.region_start_percent}% to ${r.region_end_percent}%: ${r.continuity_percent == null ? 'not evaluated' : pct(r.continuity_percent)}`}
          onMouseEnter={() => setHovered(index)} onFocus={() => setHovered(index)} onClick={() => setHovered(index)}>
          <title>{`${r.region_start_percent}% → ${r.region_end_percent}% · ${pct(r.continuity_percent)}`}</title>
        </rect>
      </g>)}
    </svg></div>
    <p className="tracking-chart-scroll-hint">Scroll across the graph to view the full conveyor.</p>
    <div className="tracking-chart-readout" aria-live="polite">{region ? <>
      <strong>Region {region.region_start_percent}% → {region.region_end_percent}%</strong>
      <span>Continuity: {region.evaluated ? pct(region.continuity_percent) : 'Not evaluated'}</span>
      <span>Lost IDs: {region.lost_ids.join(', ') || 'None'}</span><span>New IDs: {region.new_ids.join(', ') || 'None'}</span>
      {!!region.pending_ids.length && <span>Pending IDs: {region.pending_ids.join(', ')}</span>}
    </> : <span>Hover, tap or focus a region to inspect continuity and IDs. Shaded regions have no completed comparison.</span>}</div>
  </div>
}

export default function TrackingPerformance({ latestJobId, MetricCard, overlay, onOverlayChange }) {
  const [data, setData] = useState(null)
  const [runs, setRuns] = useState([])
  const [selectedRun, setSelectedRun] = useState('auto')
  const [config, setConfig] = useState(null)
  const [region, setRegion] = useState({ left: 0, top: 10, right: 100, bottom: 90 })
  const [direction, setDirection] = useState('top_to_bottom')
  const [fragmentGap, setFragmentGap] = useState('')
  const [lostGrace, setLostGrace] = useState('')
  const [error, setError] = useState('')
  const [pollError, setPollError] = useState('')
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)
  const [shownEvents, setShownEvents] = useState(12)
  const [trackSearch, setTrackSearch] = useState('')
  const [shownTracks, setShownTracks] = useState(10)
  const [selectedTrack, setSelectedTrack] = useState(null)

  useEffect(() => {
    let alive = true
    json('/api/tracking/config').then((value) => {
      if (!alive) return
      setConfig(value); setDirection(value.direction)
      setFragmentGap(value.fragment_gap_seconds); setLostGrace(value.lost_grace_seconds)
      if (value.region) setRegion(Object.fromEntries(['left', 'top', 'right', 'bottom'].map((key, i) => [key, value.region[i] * 100])))
    }).catch((e) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  useEffect(() => {
    let alive = true, busy = false, lastRuns = 0, lastJob = null
    const controller = new AbortController()
    async function refresh() {
      if (busy) return
      busy = true
      try {
        const status = await json('/api/tracking/status', { signal: controller.signal })
        const job = selectedRun === 'auto' ? (status.active || status.state === 'collecting' ? status.job_id : latestJobId) : selectedRun
        const result = job ? await json(`/api/tracking/runs/${encodeURIComponent(job)}`, { signal: controller.signal }) : null
        if (!alive) return
        if (lastJob !== job) { setShownEvents(12); setShownTracks(10); setSelectedTrack(null); setTrackSearch('') }
        lastJob = job
        setData(result); setPollError('')
        if (Date.now() - lastRuns > 15000) {
          const saved = await json('/api/tracking/runs', { signal: controller.signal })
          if (alive) setRuns(saved)
          lastRuns = Date.now()
        }
      } catch (e) { if (alive && e.name !== 'AbortError') setPollError(e.message) }
      finally { busy = false }
    }
    refresh()
    const timer = setInterval(refresh, 2000)
    return () => { alive = false; controller.abort(); clearInterval(timer) }
  }, [latestJobId, selectedRun])

  const summary = data?.summary
  const tracks = (data?.tracks || []).filter((t) => String(t.track_id).includes(trackSearch.trim()))
  const track = data?.tracks?.find((t) => t.track_id === selectedTrack)
  const body = (base) => ({ ...base, region: ['left', 'top', 'right', 'bottom'].map((key) => Number(region[key]) / 100), direction,
    fragment_gap_seconds: Number(fragmentGap), lost_grace_seconds: Number(lostGrace) })
  const post = (url, base = config) => json(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body(base)) })
  async function saveRegion(event) {
    event.preventDefault(); setSaving(true); setError(''); setMessage('')
    try {
      const result = await post('/api/tracking/config')
      setConfig(result.config); setMessage(result.message)
    } catch (e) { setError(e.message) }
    finally { setSaving(false) }
  }
  async function recalculate() {
    setSaving(true); setError(''); setMessage('')
    try {
      setData(await post(`/api/tracking/runs/${data.job_id}/recalculate`, data.config))
      setMessage('This run was recalculated from its recorded raw boxes and IDs.')
    } catch (e) { setError(e.message) }
    finally { setSaving(false) }
  }
  const worst = summary?.worst_region_start_percent == null ? 'No evaluated region' : `${summary.worst_region_start_percent}% → ${summary.worst_region_end_percent}%`
  return <section className="tracking-section" id="tracking">
    <div className="section-heading"><div><span className="eyebrow">04 / TRACKING PERFORMANCE</span><h2>Tracking performance</h2></div>
      <label className="tracking-run-select">Inspection run<select aria-label="Tracking inspection run" value={selectedRun} onChange={(e) => setSelectedRun(e.target.value)}><option value="auto">Current / latest run</option>{runs.map((run) => <option key={run.job_id} value={run.job_id}>{run.source_name || 'Inspection'} · {new Date(run.created_at).toLocaleString()}{run.available ? '' : ' · no metrics'}</option>)}</select></label>
    </div>
    <div className="panel tracking-config-panel">
      <details open={!config?.region}><summary>Tracking region and timing <span>{config?.region ? 'Configured for future runs' : 'Set the valid inspection area'}</span></summary>
        <p>Use camera-image percentages to define the valid conveyor rectangle. Checkpoints run from its entry to its exit at 1% intervals. The initial values below are a suggestion; apply the region that matches your conveyor.</p>
        <form className="tracking-config-form" onSubmit={saveRegion}>
          {['left', 'top', 'right', 'bottom'].map((key) => <label key={key}>{key[0].toUpperCase() + key.slice(1)} (%)<input type="number" min="0" max="100" step="0.1" required value={region[key]} onChange={(e) => setRegion({ ...region, [key]: e.target.value })} /></label>)}
          <label>Travel direction<select value={direction} onChange={(e) => setDirection(e.target.value)}><option value="top_to_bottom">Top → bottom</option><option value="bottom_to_top">Bottom → top</option><option value="left_to_right">Left → right</option><option value="right_to_left">Right → left</option></select></label>
          <label className="tracking-time-setting">Fragmentation window (seconds)<input type="number" min="0" step="any" required value={fragmentGap} onChange={(e) => setFragmentGap(e.target.value)} /></label>
          <label className="tracking-time-setting">Lost-track grace (seconds)<input type="number" min="0" step="any" required value={lostGrace} onChange={(e) => setLostGrace(e.target.value)} /></label>
          <button type="submit" className="primary-button" disabled={!config || saving}>{saving ? 'Saving…' : 'Apply for future runs'}</button>
          {data?.summary && data.state !== 'collecting' && <button type="button" className="secondary-button" disabled={!config || saving} onClick={recalculate}>Recalculate this run</button>}
        </form>
      </details>
      <div className="tracking-run-caption"><span>{data?.job_id ? `Run ${data.job_id.slice(0, 12)} · ${data.state}` : 'No inspection run yet'}{summary && ` · ${number(summary.frames_processed)} frames · ${number(summary.total_unique_track_ids)} raw IDs`}</span>
        <label><input type="checkbox" checked={overlay} onChange={(e) => onOverlayChange(e.target.checked)} /> Show processed IDs and 10% guides</label>
      </div>
      {data?.config?.region && <p className="tracking-note">This run: {data.config.region.map((v) => decimal(v * 100)).join(' / ')}% (left / top / right / bottom), {data.config.direction.replaceAll('_', ' ')}, {data.config.checkpoint_interval_percent}% checkpoints.</p>}
      {data?.config && <p className="tracking-note tracking-timing-details">{data.config.fragment_gap_seconds != null && data.config.lost_grace_seconds != null
        ? `Event timing for this run: fragmentation window ${seconds(data.config.fragment_gap_seconds)} · lost-track grace ${seconds(data.config.lost_grace_seconds)} · maximum interpolation gap ${seconds(data.config.max_interpolation_seconds)}. Uses video/monotonic timestamps, independent of processing FPS.`
        : 'This saved run used frame-based event timing. Recalculate this run to apply the settings in seconds.'}</p>}
      {message && <p className="refresh-message" role="status">{message}</p>}
      {(error || pollError) && <p className="upload-error" role="alert">{error || pollError}</p>}
    </div>
    {!summary ? <div className="panel tracking-empty"><strong>{data?.state === 'unavailable' ? 'This saved run predates tracking metrics' : 'Start a video or live inspection to collect tracking metrics'}</strong><p>New runs record raw TrackTrack observations automatically. Set the conveyor region once to enable spatial measurements.</p></div> : <>
      {!summary.region_configured && <p className="tracking-notice" role="status">Spatial metrics await a valid conveyor region. Timing and raw observations are being recorded. Apply a region, then recalculate this run after inspection finishes.</p>}
      {summary.direction_warning && <p className="tracking-notice" role="alert">Observed motion predominantly opposes the configured direction. Check the conveyor region and direction before interpreting continuity.</p>}
      <div className="tracking-metrics-grid">
        <MetricCard title="ID Continuity" value={pct(summary.id_continuity_percent)} hint={`${number(summary.completed_tracks)} completed / ${number(summary.valid_entering_tracks)} valid entries`} icon="check" tone="accent" />
        <MetricCard title="Mean Regional Continuity" value={pct(summary.mean_regional_continuity_percent)} hint={`${number(summary.valid_evaluated_regions)} evaluated regions`} icon="layers" />
        <MetricCard title="Regional Pass Rate" value={pct(summary.regional_pass_rate_percent)} hint="100% continuity and no order reversal" icon="check" />
        <MetricCard title="Possible ID Swaps" value={number(summary.region_configured ? summary.order_inversions : null)} hint="Pair-order inversions across adjacent checkpoints" icon="alert" />
        <MetricCard title="ID Fragmentations" value={number(summary.region_configured ? summary.id_fragmentations : null)} hint="Suspected replacements near predicted centres" icon="layers" />
        <MetricCard title="Lost Tracks" value={number(summary.region_configured ? summary.lost_tracks : null)} hint={`${number(summary.unfinished_entering_tracks)} unfinished entries excluded from loss count`} icon="alert" />
        <MetricCard title="Processing FPS" value={decimal(summary.processing_fps)} hint={`Detection + tracking · ${decimal(summary.average_processing_time_ms)} ms/frame`} icon="camera" />
        <MetricCard title="Minimum Continuity" value={pct(summary.minimum_regional_continuity_percent)} hint={`Worst region: ${worst}`} icon="alert" />
        <MetricCard title="Mid-region New IDs" value={number(summary.region_configured ? summary.mid_region_new_ids : null)} hint="First seen away from the entry band" icon="grid" />
      </div>
      <p className="tracking-note">Continuity uses raw TrackTrack IDs. Unfinished entries remain in the overall denominator; pending regional comparisons are excluded. Fragmentations and swaps are suspected events. These measurements use no manually annotated tracking ground truth.</p>
      <div className="panel tracking-graph-panel"><div className="panel-heading"><div><span className="eyebrow">CONVEYOR CHECKPOINTS</span><h3>Regional ID Continuity</h3></div><span className="panel-caption">0–100%</span></div><RegionalChart regions={data.regions || []} /></div>
      <div className="panel tracking-table-panel"><div className="panel-heading"><h3>Tracking Events</h3><span className="panel-caption">{number(data.events.length)} EVENTS</span></div>
        <div className="tracking-table-scroll"><table><thead><tr><th>Frame</th><th>Conveyor position</th><th>Event</th><th>Track ID(s)</th><th>Description</th></tr></thead><tbody>{data.events.slice(0, shownEvents).map((event, i) => <tr key={`${data.job_id}-${i}`}><td>{decimal(event.frame)}</td><td>{pct(event.position_percent)}</td><td>{labels[event.event_type] || event.event_type}</td><td>{event.IDs.join(event.event_type === 'id_fragmentation' ? ' → ' : ' / ')}</td><td>{event.description}</td></tr>)}</tbody></table></div>
        {!data.events.length && <p className="tracking-note">No suspicious events recorded.</p>}
        {data.events.length > shownEvents && <button className="text-button" onClick={() => setShownEvents(shownEvents + 25)}>Show more events</button>}
      </div>
      <div className="panel tracking-table-panel"><div className="panel-heading"><h3>Per-track details</h3><label className="search-box"><input aria-label="Find raw TrackTrack ID" placeholder="Find raw TrackTrack ID" value={trackSearch} onChange={(e) => { setTrackSearch(e.target.value); setShownTracks(10) }} /></label></div>
        <div className="tracking-table-scroll"><table><thead><tr><th>Raw ID</th><th>First / last frame</th><th>First / last checkpoint</th><th>Coverage</th><th>Frames tracked</th><th>Status</th><th>Problems</th></tr></thead><tbody>{tracks.slice(0, shownTracks).map((t) => <tr key={t.track_id}><td><button className="tracking-id-button" onClick={() => setSelectedTrack(t.track_id)}>ID {t.track_id}</button></td><td>{t.first_frame} / {t.last_frame}</td><td>{pct(t.first_checkpoint)} / {pct(t.last_checkpoint)}</td><td>{pct(t.region_coverage_percent)}</td><td>{t.frames_tracked}</td><td>{t.status.replaceAll('_', ' ')}</td><td>{t.problems.map((p) => labels[p]).join(', ') || 'None'}</td></tr>)}</tbody></table></div>
        {!tracks.length && <p className="tracking-note">No matching raw IDs.</p>}
        {tracks.length > shownTracks && <button className="text-button" onClick={() => setShownTracks(shownTracks + 25)}>Show more tracks</button>}
        {track && <div className="tracking-track-detail" role="region" aria-label={`Raw TrackTrack ID ${track.track_id} details`}><strong>ID {track.track_id} · {track.status.replaceAll('_', ' ').toUpperCase()}</strong><p>Frames {track.first_frame}–{track.last_frame} · {track.frames_tracked} observations · Checkpoints {pct(track.first_checkpoint)}–{pct(track.last_checkpoint)} · Coverage {pct(track.region_coverage_percent)} · {track.completed ? 'Complete inspection region' : 'Incomplete inspection region'} · {track.valid_entry ? 'Valid entry observed' : 'Entry not observed'}</p><p>Tracking problems: {track.problems.map((p) => labels[p]).join(', ') || 'None'}</p><button className="text-button" onClick={() => setSelectedTrack(null)}>Close details</button></div>}
      </div>
      <div className="tracking-exports"><span>Export this run</span>{exports.map((name) => <a key={name} href={`/api/tracking/runs/${data.job_id}/exports/${name}`} download={name} className="report-link">{name}</a>)}</div>
    </>}
  </section>
}
