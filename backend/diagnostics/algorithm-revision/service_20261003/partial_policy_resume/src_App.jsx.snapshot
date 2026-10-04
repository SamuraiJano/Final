import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'

const emptyDashboard = {
  summary: { runs: 0, fruit_count: 0, classes: { 'Class 1': 0, 'Class 2': 0, 'Class 3': 0, ungraded: 0 } },
  latest_run: null,
  recent_fruits: [],
}

const iconShapes = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  camera: <><path d="M4 7h3l2-2h6l2 2h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1Z" /><circle cx="12" cy="13" r="3.5" /></>,
  layers: <><path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5" /></>,
  upload: <><path d="M12 16V3m-5 5 5-5 5 5" /><path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" /></>,
  search: <><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 5 5" /></>,
  arrow: <><path d="M5 12h14m-6-6 6 6-6 6" /></>,
  close: <><path d="M5 5 19 19M19 5 5 19" /></>,
  file: <><path d="M6 3h8l4 4v14H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M14 3v5h5M8 13h8m-8 4h8" /></>,
  check: <><path d="m4 12 5 5L20 6" /></>,
  alert: <><path d="m12 3 10 18H2L12 3Z" /><path d="M12 9v5m0 3h.01" /></>,
  refresh: <><path d="M20 11a8 8 0 1 0-2.3 6.3" /><path d="M20 4v7h-7" /></>,
}

function Icon({ name, size = 18 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{iconShapes[name]}</svg>
}

function formatNumber(value) { return new Intl.NumberFormat().format(value ?? 0) }
function formatPercent(value) { return value == null ? '—' : `${Number(value).toFixed(1)}%` }
function formatTime(value) { return value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : 'No inspections yet' }
function gradeText(fruit) {
  if (fruit.grade) return `${fruit.grade}${fruit.status === 'graded_partial' || fruit.grade_provisional ? ' (partial)' : ''}`
  return fruit.status === 'mapping_failed' ? 'Mapping failed' : 'Needs review'
}
function gradeClass(fruit) { return fruit.grade ? `grade-${fruit.grade.slice(-1)}` : 'grade-review' }

async function getJson(url) {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`Request failed: ${response.status}`)
  return response.json()
}

function MetricCard({ title, value, hint, icon, tone }) {
  return <div className={`metric-card ${tone || ''}`}><div className="metric-card-top"><span>{title}</span><span className="metric-icon"><Icon name={icon} size={17} /></span></div><div className="metric-value">{value}</div><div className="metric-hint">{hint}</div></div>
}

function ModelRow({ title, subtitle, data, accent }) {
  const confidence = data?.mean_confidence == null ? null : data.mean_confidence * 100
  return <div className="model-row"><div className="model-row-head"><span className={`model-mark ${accent}`}><Icon name={title === 'Fruit detection' ? 'camera' : 'layers'} size={17} /></span><div><strong>{title}</strong><small>{subtitle}</small></div><span className="model-latency">{data?.mean_latency_ms == null ? '—' : `${data.mean_latency_ms} ms`}</span></div><div className="confidence-line"><span>Mean confidence</span><strong>{confidence == null ? '—' : `${confidence.toFixed(1)}%`}</strong></div><div className="confidence-track"><span style={{ width: `${confidence ?? 0}%` }} /></div><small className="model-note">{data ? `${formatNumber(data.instances)} detections across ${formatNumber(data.calls)} ${title === 'Fruit detection' ? 'frames' : 'fruit views'}` : 'Available during live inspection or after video analysis'}</small></div>
}

function FruitDetail({ fruit, onClose }) {
  useEffect(() => {
    function onKeyDown(event) { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const degrees = (value) => value == null ? '\u2014' : `${Number(value).toFixed(1)}\u00b0`
  return <div className="drawer-backdrop" onClick={onClose}>
    <aside className="detail-drawer" role="dialog" aria-modal="true" aria-label={`Fruit ${fruit.track_id} inspection`} onClick={(event) => event.stopPropagation()}>
      <div className="drawer-top"><div><span className="eyebrow">FRUIT INSPECTION</span><h2>Fruit {String(fruit.track_id).padStart(3, '0')}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close inspection"><Icon name="close" /></button></div>
      <span className={`grade-pill ${gradeClass(fruit)}`}>{gradeText(fruit)}</span>
      <p className="drawer-subtitle">{fruit.source_name || 'Recorded video'} &middot; {formatTime(fruit.created_at)}</p>
      {(fruit.status === 'graded_partial' || fruit.grade_provisional) && <p className="evidence-note">Provisional grade based on the observed surface; unseen areas were not assessed.</p>}
      <div className="detail-map">{fruit.surface_map ? <img src={fruit.surface_map} alt={`Surface map of fruit ${fruit.track_id}`} /> : <div className="map-unavailable"><Icon name="alert" size={25} /><span>No surface map available</span></div>}</div>
      <div className="detail-stats">
        <div><span>Observed surface</span><strong>{formatPercent(fruit.observed_surface_pct)}</strong></div>
        <div><span>Surface defects</span><strong>{formatPercent(fruit.defect_pct_of_observed)}</strong></div>
        <div><span>Measured rotation</span><strong>{degrees(fruit.rotation_coverage_deg)}</strong></div>
        <div><span>Circumference observed</span><strong>{degrees(fruit.observed_longitude_deg)}</strong></div>
        <div><span>Captured views</span><strong>{fruit.views ?? '\u2014'}</strong></div>
        <div><span>Views used in map</span><strong>{fruit.mapped_view_frames?.length ?? '\u2014'}</strong></div>
        {fruit.first_seen_frame != null && <>
          <div><span>First tracked frame</span><strong>{fruit.first_seen_frame}</strong></div>
          <div><span>Last tracked frame</span><strong>{fruit.last_seen_frame}</strong></div>
          <div><span>Tracked frames</span><strong>{fruit.tracked_frames}</strong></div>
        </>}
      </div>
      {fruit.reason && <div className="review-reason"><Icon name="alert" size={18} /><span>{fruit.reason}</span></div>}
      {!!fruit.tracking_evidence?.length && <details className="map-details">
        <summary>Entry and last seen</summary>
        <p className="evidence-note">Tracking includes partially visible fruit at the frame edge. Surface reconstruction uses the usable complete-outline views from that same identity.</p>
        <div className="mask-grid">{fruit.tracking_evidence.map((view) => <div key={view.stage}>
          <span>{view.stage === 'entry' ? 'First tracked' : 'Last seen'} &middot; frame {view.frame}</span>
          <a href={view.crop} target="_blank" rel="noreferrer"><img src={view.crop} alt={`${view.stage === 'entry' ? 'Entry' : 'Last seen'} crop at frame ${view.frame}`} /></a>
        </div>)}</div>
      </details>}
      {!!fruit.view_evidence?.length && <details className="map-details">
        <summary>Source views and model masks</summary>
        <p className="evidence-note">Green outlines the fruit. Red shows predicted defects. These are model outputs, not manually verified labels.</p>
        {fruit.view_evidence.map((view) => <div className="evidence-view" key={view.frame}>
          <strong>Frame {view.frame}</strong>
          <div className="mask-grid evidence-grid">
            <div><span>Source crop</span><a href={view.crop} target="_blank" rel="noreferrer"><img src={view.crop} alt={`Fruit crop at frame ${view.frame}`} /></a></div>
            <div><span>Fruit mask</span><a href={view.fruit_mask} target="_blank" rel="noreferrer"><img src={view.fruit_mask} alt={`Fruit silhouette at frame ${view.frame}`} /></a></div>
            <div><span>{view.defect_inference_ran ? 'Predicted defects' : 'Fruit boundary only'}</span><a href={view.overlay} target="_blank" rel="noreferrer"><img src={view.overlay} alt={`Inspection overlay at frame ${view.frame}`} /></a></div>
          </div>
          {!view.defect_inference_ran && <p className="evidence-note">Defect inference was not run on this unused view.</p>}
        </div>)}
      </details>}
      {fruit.observed_mask && <details className="map-details"><summary>Observed area and defect maps</summary><div className="mask-grid"><div><span>Observed area</span><img src={fruit.observed_mask} alt="Observed surface area mask" /></div>{Object.entries(fruit.defect_maps || {}).map(([name, url]) => <div key={name}><span>{name.replaceAll('_', ' ')}</span><img src={url} alt={`${name.replaceAll('_', ' ')} mask`} /></div>)}</div></details>}
      <a className="report-link" href={`/results/${fruit.job_id}/report.json`} download>Download analysis report <Icon name="arrow" size={16} /></a>
    </aside>
  </div>
}

export default function App() {
  const [dashboard, setDashboard] = useState(emptyDashboard)
  const [health, setHealth] = useState(null)
  const [camera, setCamera] = useState({ configured: false, connected: false })
  const [live, setLive] = useState({ state: 'idle' })
  const [liveBusy, setLiveBusy] = useState(false)
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [viewMode, setViewMode] = useState('camera')
  const [uploading, setUploading] = useState(false)
  const [stopBusy, setStopBusy] = useState(false)
  const analysisIdRef = useRef(null)
  const [analysisProgress, setAnalysisProgress] = useState(null)
  const [backendControl, setBackendControl] = useState({ managed: false, refreshing: false })
  const [backendRefreshing, setBackendRefreshing] = useState(false)
  const [refreshMessage, setRefreshMessage] = useState('')
  const [error, setError] = useState('')
  const [historyScope, setHistoryScope] = useState('latest')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('All fruit')
  const [shown, setShown] = useState(6)
  const [selectedFruit, setSelectedFruit] = useState(null)

  const refreshDashboard = useCallback(async () => {
    try { setDashboard(await getJson('/api/dashboard')) } catch { setDashboard(emptyDashboard) }
  }, [])

  useEffect(() => {
    const initial = window.setTimeout(refreshDashboard, 0)
    const timer = window.setInterval(refreshDashboard, 15000)
    return () => { window.clearTimeout(initial); window.clearInterval(timer) }
  }, [refreshDashboard])

  useEffect(() => {
    async function refreshStatus() {
      try { setHealth(await getJson('/api/health')) } catch { setHealth(null) }
      try { setCamera(await getJson('/api/camera/status')) } catch { setCamera({ configured: false, connected: false }) }
      try { setLive(await getJson('/api/live/status')) } catch { setLive({ state: 'idle' }) }
      try { setBackendControl(await getJson('/api/backend/control')) } catch { setBackendControl({ managed: false, refreshing: false }) }
    }
    refreshStatus()
    const timer = window.setInterval(refreshStatus, 5000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl) }, [previewUrl])

  useEffect(() => {
    let active = true
    async function refreshProgress() {
      try {
        const progress = await getJson('/api/analysis/status')
        if (active) setAnalysisProgress(progress)
      } catch { /* The upload request will display the API error. */ }
    }
    refreshProgress()
    const timer = window.setInterval(refreshProgress, 1000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])

  function chooseFile(event) {
    const selected = event.target.files?.[0] || null
    setFile(selected)
    setPreviewUrl(selected ? URL.createObjectURL(selected) : null)
    if (selected) setViewMode('video')
    setError('')
  }

  async function analyze(event) {
    event.preventDefault()
    if (!file || analysisActive || liveActive || backendRefreshing || backendControl.refreshing) return
    setUploading(true)
    setStopBusy(false)
    setAnalysisProgress(null)
    setError('')
    setRefreshMessage('')
    const runId = crypto.randomUUID()
    analysisIdRef.current = runId
    try {
      const body = new FormData()
      body.append('video', file)
      const response = await fetch('/api/analyze-video', {
        method: 'POST', body, headers: { 'X-Analysis-Id': runId },
      })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Analysis failed')
      if (result.status === 'cancelled') {
        setRefreshMessage('Analysis stopped. No report was saved.')
      } else {
        await refreshDashboard()
      }
    } catch (problem) {
      setError(problem.message)
    } finally {
      analysisIdRef.current = null
      setStopBusy(false)
      setUploading(false)
    }
  }

  async function stopAnalysis() {
    const runId = analysisIdRef.current || analysisProgress?.run_id
    if (!runId || stopBusy) return
    setStopBusy(true)
    setError('')
    try {
      const response = await fetch('/api/analysis/stop', {
        method: 'POST', headers: { 'X-Analysis-Id': runId },
      })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Could not stop analysis')
      if (result.state === 'cancelling') {
        setAnalysisProgress((current) => ({ ...current, state: 'cancelling', run_id: runId }))
      } else {
        setStopBusy(false)
      }
    } catch (problem) {
      setError(problem.message)
      setStopBusy(false)
    }
  }

  async function changeLive() {
    if (backendRefreshing || backendControl.refreshing) return
    const action = ['starting', 'running'].includes(live.state) ? 'stop' : 'start'
    setLiveBusy(true)
    setError('')
    try {
      const response = await fetch(`/api/live/${action}`, { method: 'POST' })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Could not change live inspection')
      setLive(result)
      if (action === 'start') setViewMode('camera')
      await refreshDashboard()
    } catch (problem) {
      setError(problem.message)
    } finally {
      setLiveBusy(false)
    }
  }

  async function refreshBackend() {
    if (backendRefreshing || backendControl.refreshing || analysisActive || liveActive) return
    setBackendRefreshing(true)
    setRefreshMessage('')
    setError('')
    try {
      const response = await fetch('/api/backend/control', { method: 'POST' })
      const result = await response.json()
      if (!response.ok) throw new Error(result.error || result.detail || 'Could not refresh the backend')
      setAnalysisProgress(null)
      setHealth(await getJson('/api/health'))
      setCamera(await getJson('/api/camera/status'))
      setLive(await getJson('/api/live/status'))
      await refreshDashboard()
      setRefreshMessage('Backend refreshed. Ready for a new inference run.')
    } catch (problem) {
      setError(problem.message)
    } finally {
      setBackendRefreshing(false)
    }
  }

  const { summary: savedSummary, latest_run: latestRun, recent_fruits: fruits } = dashboard
  // Track IDs belong to one run. Repeated analyses remain separate records.
  const scopedFruits = historyScope === 'latest'
    ? fruits.filter((fruit) => fruit.job_id === latestRun?.job_id)
    : fruits
  const counts = { 'Class 1': 0, 'Class 2': 0, 'Class 3': 0, ungraded: 0 }
  for (const fruit of scopedFruits) {
    const grade = Object.hasOwn(counts, fruit.grade) ? fruit.grade : 'ungraded'
    counts[grade] += 1
  }
  const summary = {
    fruit_count: scopedFruits.length,
    runs: historyScope === 'latest' ? Number(Boolean(latestRun)) : savedSummary.runs,
  }
  const graded = counts['Class 1'] + counts['Class 2'] + counts['Class 3']
  const classOneShare = graded ? Math.round((counts['Class 1'] / graded) * 100) : null
  const searched = search.trim().toLowerCase()
  const filtered = scopedFruits.filter((fruit) => (filter === 'All fruit' || (filter === 'Needs review' ? !fruit.grade : fruit.grade === filter)) && (!searched || String(fruit.track_id).includes(searched) || (fruit.source_name || '').toLowerCase().includes(searched)))
  const visible = filtered.slice(0, shown)
  const previewActive = previewUrl && viewMode === 'video'
  const liveActive = ['starting', 'running', 'stopping'].includes(live.state)
  const analysisActive = uploading || ['uploading', 'loading_models', 'processing', 'building_maps', 'cancelling'].includes(analysisProgress?.state)
  const progressText = analysisProgress?.state === 'loading_models' ? 'Loading inference models…'
    : analysisProgress?.state === 'processing' ? `Processing frame ${formatNumber(analysisProgress.frames_processed)}${analysisProgress.frames_total ? ` of ${formatNumber(analysisProgress.frames_total)}` : ''}…`
      : analysisProgress?.state === 'building_maps' ? 'Building fruit surface maps…'
        : analysisProgress?.state === 'cancelling' ? 'Stopping analysis…'
        : 'Uploading video and starting analysis…'

  return <div className="app-shell" id="overview">
    <aside className="sidebar"><a className="brand" href="#overview"><span className="brand-mark"><span /></span><span><strong>Citrus<span>vision</span></strong><small>INSPECTION SYSTEM</small></span></a><div className="side-nav-label">WORKSPACE</div><nav className="side-nav" aria-label="Main navigation"><a className="active" href="#overview"><Icon name="grid" size={17} /> Overview</a><a href="#inspections"><Icon name="layers" size={17} /> Inspections</a></nav><div className="sidebar-bottom"><div className={`system-dot ${health?.cuda_available ? 'online' : ''}`} /><div><strong>{health?.cuda_available ? 'Models ready' : health ? 'GPU unavailable' : 'Backend offline'}</strong><span>{health?.cuda_available ? 'CUDA acceleration active' : 'Check the backend service'}</span></div></div></aside>

    <main className="workspace"><header className="topbar"><div className="breadcrumbs">OPERATIONS <span>/</span> OVERVIEW</div><div className="top-status"><span className={`live-dot ${camera.connected ? 'on' : ''}`} /> {liveActive ? `Inspection ${live.state}` : camera.connected ? 'Camera connected' : 'Camera offline'}<span className="top-status-divider" />{health ? 'Backend online' : 'Backend offline'}</div></header>
      <div className="page-heading"><div><span className="eyebrow">QUALITY CONTROL DASHBOARD</span><h1>Conveyor overview<span className="heading-period">.</span></h1><p>Camera, model signals and the latest naartjie surface inspections.</p></div><div className="last-analysis"><span>LATEST ANALYSIS</span><strong>{formatTime(latestRun?.created_at)}</strong></div></div>
      <div className="history-scope-row">
        <div className="filter-tabs history-scope" role="group" aria-label="Inspection history scope">
          {[['latest', 'Latest run'], ['all', 'All saved runs']].map(([value, label]) => <button key={value} type="button" className={historyScope === value ? 'selected' : ''} aria-pressed={historyScope === value} onClick={() => { setHistoryScope(value); setShown(6) }}>{label}</button>)}
        </div>
        <p>{historyScope === 'latest' ? latestRun ? `${latestRun.source_name || 'Recorded video'} · ${formatTime(latestRun.created_at)}` : 'No saved run yet' : 'Saved analyses include repeat runs of the same video.'}</p>
      </div>
      <section className="summary-grid" aria-label="Inspection summary"><MetricCard title="Inspection records" value={formatNumber(summary.fruit_count)} hint={`${formatNumber(summary.runs)} inspection ${summary.runs === 1 ? 'session' : 'sessions'}`} icon="grid" /><MetricCard title="Class 1 share" value={classOneShare == null ? '—' : `${classOneShare}%`} hint="Of fruit assigned a grade" icon="check" tone="accent" /><MetricCard title="Needs review" value={formatNumber(counts.ungraded)} hint="No usable map or defect estimate" icon="alert" /></section>

      <section className="monitor-grid" aria-label="Camera and model monitoring"><div className="panel camera-panel"><div className="panel-heading"><div><span className="eyebrow">01 / CAMERA</span><h2>Conveyor view</h2></div><span className={`feed-badge ${camera.connected ? 'connected' : ''}`}><span />{liveActive ? 'INSPECTION ACTIVE' : previewActive ? 'UPLOAD PREVIEW' : camera.connected ? 'LIVE FEED' : 'NO LIVE FEED'}</span></div><div className={`camera-stage ${previewActive || camera.configured ? 'has-video' : ''}`}>
        {previewActive ? <video src={previewUrl} controls muted playsInline aria-label="Selected conveyor video preview" /> : camera.configured ? <><img src="/api/camera/stream" alt="Live conveyor camera" />{!camera.connected && <div className="camera-overlay"><Icon name="camera" size={29} /><strong>Waiting for camera</strong><span>Checking {camera.source?.toLowerCase()} for frames</span></div>}</> : <div className="camera-empty"><div className="camera-empty-icon"><Icon name="camera" size={34} /></div><strong>Camera source not connected</strong><span>Configure a USB camera or network stream to monitor the conveyor here.</span></div>}
        <span className="camera-corner top-left" /><span className="camera-corner top-right" /><span className="camera-corner bottom-left" /><span className="camera-corner bottom-right" /></div>
        <form className="camera-controls" onSubmit={analyze}>
          <div className="source-caption"><span className="source-label">{previewActive ? 'SELECTED VIDEO' : 'CAMERA SOURCE'}</span><strong title={previewActive ? file?.name : camera.source || ''}>{previewActive ? file?.name : camera.source || 'Not configured'}</strong></div>
          <div className="camera-actions">
            {previewActive && camera.configured && <button type="button" className="text-button" onClick={() => setViewMode('camera')}>Live view</button>}
            {camera.configured && <button type="button" className={`live-button ${liveActive ? 'running' : ''}`} onClick={changeLive} disabled={liveBusy || analysisActive || backendRefreshing || backendControl.refreshing || live.state === 'stopping' || (!camera.connected && !liveActive)}>{live.state === 'starting' ? 'Starting…' : live.state === 'stopping' ? 'Stopping…' : liveActive ? 'Stop live' : 'Start live'}</button>}
            <label className={`secondary-button ${liveActive ? 'disabled' : ''}`} htmlFor="video-upload"><Icon name="upload" size={16} /> Choose video</label>
            <input id="video-upload" className="sr-only" type="file" accept=".mp4,.avi,.mov,.mkv,video/*" onChange={chooseFile} disabled={liveActive} />
            <button className="refresh-button" type="button" onClick={refreshBackend} disabled={!backendControl.managed || backendRefreshing || backendControl.refreshing || analysisActive || liveActive} title={backendControl.managed ? 'Restart the local inference API' : 'Start with npm run dev to manage the backend'}><Icon name="refresh" size={16} />{backendRefreshing || backendControl.refreshing ? 'Refreshing…' : 'Refresh backend'}</button>
            <button className="primary-button" type="submit" disabled={!file || analysisActive || liveActive || backendRefreshing || backendControl.refreshing}>{analysisActive ? 'Analyzing…' : 'Analyze'} <Icon name="arrow" size={16} /></button>
          </div>
        </form>
        {(error || live.error || analysisProgress?.error) && <p className="upload-error" role="alert"><Icon name="alert" size={16} />{error || live.error || analysisProgress?.error}</p>}
        {refreshMessage && <p className="refresh-message" role="status">{refreshMessage}</p>}
        {analysisActive && <div className="analysis-status-row"><div className="analysis-progress" role="status"><span />{progressText}</div><button className="stop-button" type="button" onClick={stopAnalysis} disabled={stopBusy || analysisProgress?.state === 'cancelling'}><Icon name="close" size={15} />{stopBusy || analysisProgress?.state === 'cancelling' ? 'Stopping…' : 'Stop analysis'}</button></div>}
        {live.state === 'starting' && <div className="analysis-progress" role="status"><span />Loading models for live inspection…</div>}
        </div>

      <div className="monitor-side"><div className="panel quality-panel"><div className="panel-heading"><div><span className="eyebrow">02 / QUALITY</span><h2>Class mix</h2></div><span className="panel-caption">{historyScope === 'latest' ? 'LATEST RUN' : 'ALL SAVED RUNS'}</span></div><div className="quality-total"><strong>{formatNumber(summary.fruit_count)}</strong><span>inspection records</span></div><div className="mix-bar" aria-label="Fruit class distribution">{['Class 1', 'Class 2', 'Class 3', 'ungraded'].map((name) => <span key={name} className={`mix-${name.replace(' ', '-').toLowerCase()}`} style={{ width: `${summary.fruit_count ? (counts[name] / summary.fruit_count) * 100 : 0}%` }} />)}</div><div className="mix-legend">{['Class 1', 'Class 2', 'Class 3', 'ungraded'].map((name) => <div key={name}><span className={`legend-dot mix-${name.replace(' ', '-').toLowerCase()}`} /><span>{name === 'ungraded' ? 'Review' : name}</span><strong>{formatNumber(counts[name])}</strong></div>)}</div></div><div className="panel performance-panel"><div className="panel-heading"><div><span className="eyebrow">03 / MODEL SIGNAL</span><h2>Inference performance</h2></div><span className="panel-caption">LATEST RUN</span></div><ModelRow title="Fruit detection" subtitle="D-FINE · object boxes" data={latestRun?.metrics?.detection} accent="detect" /><ModelRow title="Defect segmentation" subtitle="D-FINE-seg · fruit crops" data={latestRun?.metrics?.segmentation} accent="segment" /><p className="confidence-disclaimer">Confidence is model certainty, not measured accuracy.</p></div></div></section>

      <section className="inspections-section" id="inspections"><div className="section-heading"><div><span className="eyebrow">04 / INSPECTIONS</span><h2>Recent fruit <span>and surface maps</span></h2></div><span className="section-count">{formatNumber(filtered.length)} shown in history</span></div><div className="panel inspection-panel"><div className="inspection-toolbar"><div className="filter-tabs" role="group" aria-label="Filter fruit by class">{['All fruit', 'Class 1', 'Class 2', 'Class 3', 'Needs review'].map((name) => <button key={name} type="button" className={filter === name ? 'selected' : ''} onClick={() => { setFilter(name); setShown(6) }}>{name}</button>)}</div><label className="search-box"><Icon name="search" size={17} /><input value={search} onChange={(event) => { setSearch(event.target.value); setShown(6) }} placeholder="Search fruit or video" aria-label="Search fruit or video" /></label></div><div className="inspection-table"><div className="table-head"><span>FRUIT / SOURCE</span><span>CLASS</span><span>OBSERVED</span><span>DEFECTS</span><span>SURFACE MAP</span><span /></div>{visible.length ? visible.map((fruit) => <button type="button" className="fruit-row" key={`${fruit.job_id}-${fruit.track_id}`} onClick={() => setSelectedFruit(fruit)}><span className="fruit-identity"><span className="fruit-avatar">{fruit.surface_map ? <img src={fruit.surface_map} alt="" /> : <Icon name="file" size={19} />}</span><span><strong>Fruit {String(fruit.track_id).padStart(3, '0')}</strong><small>{fruit.source_name || 'Recorded video'} · {formatTime(fruit.created_at)}</small></span></span><span><span className={`grade-pill ${gradeClass(fruit)}`}>{gradeText(fruit)}</span></span><span className="table-number">{formatPercent(fruit.observed_surface_pct)}</span><span className="table-number">{formatPercent(fruit.defect_pct_of_observed)}</span><span className="map-cell">{fruit.surface_map ? 'View map' : 'Unavailable'}</span><Icon name="arrow" size={17} /></button>) : <div className="inspection-empty"><span className="empty-symbol"><Icon name="layers" size={25} /></span><strong>{fruits.length ? 'No fruit match this view' : 'No inspections recorded yet'}</strong><span>{fruits.length ? 'Try another class or search term.' : 'Analyze a video or start live inspection above.'}</span></div>}</div>{filtered.length > shown && <div className="table-footer"><button type="button" onClick={() => setShown(shown + 6)}>Show more inspections <Icon name="arrow" size={16} /></button></div>}</div></section><footer className="app-footer"><span>Citrusvision · Naartjie quality monitoring</span><span>Results update during live inspection and after video analysis.</span></footer></main>{selectedFruit && <FruitDetail fruit={selectedFruit} onClose={() => setSelectedFruit(null)} />}</div>
}
