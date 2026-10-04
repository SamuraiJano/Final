import { spawn } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const python = join(root, 'backend', 'venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const vite = join(root, 'node_modules', 'vite', 'bin', 'vite.js')
const healthUrl = 'http://127.0.0.1:8000/api/health'
const refreshToken = randomUUID()

if (!existsSync(python)) {
  console.error(`Backend Python is missing: ${python}\nSet it up using the commands in README.md.`)
  process.exit(1)
}
if (!existsSync(vite)) {
  console.error('Vite is missing. Run npm install first.')
  process.exit(1)
}

let api
let dashboard
let stopping = false
let refreshing = false

async function backendReady() {
  try {
    const response = await fetch(healthUrl, { signal: AbortSignal.timeout(2000) })
    return response.ok && (await response.json()).status === 'ok'
  } catch {
    return false
  }
}

function stopChild(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return
  if (process.platform === 'win32') {
    const stopper = spawn(python, [join(root, 'scripts', 'stop_process_tree.py'), String(child.pid)], {
      stdio: ['ignore', 'ignore', 'inherit'], windowsHide: true,
    })
    stopper.on('error', (error) => console.error(`Could not stop managed process: ${error.message}`))
  } else {
    child.kill('SIGTERM')
  }
}

function shutdown(code = 0) {
  if (stopping) return
  stopping = true
  stopChild(dashboard)
  stopChild(api)
  process.exitCode = code
}

process.on('SIGINT', () => shutdown())
process.on('SIGTERM', () => shutdown())

function startApi() {
  const child = spawn(python, ['-m', 'uvicorn', 'main:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', '8000'], {
    cwd: root,
    stdio: 'inherit',
    windowsHide: true,
    env: { ...process.env, FRUIT_REFRESH_TOKEN: refreshToken },
  })
  api = child
  child.on('error', (error) => {
    console.error(`Could not start inference API: ${error.message}`)
    if (!refreshing) shutdown(1)
  })
  child.on('exit', (code) => {
    if (!stopping && !refreshing) {
      console.error(`Inference API exited${code == null ? '' : ` with code ${code}`}.`)
      shutdown(1)
    }
  })
  return child
}

async function waitForBackend() {
  const deadline = Date.now() + 60000
  while (!stopping && Date.now() < deadline && !(await backendReady())) {
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  return !stopping && await backendReady()
}

if (await backendReady()) {
  console.log('Inference API is already running.')
} else {
  console.log('Starting inference API…')
  startApi()
  const ready = await waitForBackend()
  if (stopping) process.exit(1)
  if (!ready) {
    console.error('Inference API did not become ready within 60 seconds.')
    shutdown(1)
    process.exit(1)
  }
  console.log('Inference API ready.')
}

async function refreshBackend() {
  if (!api) throw new Error('The backend was started outside this app. Restart it from its own terminal.')
  if (refreshing) throw new Error('Backend refresh is already in progress.')
  let response
  try {
    response = await fetch('http://127.0.0.1:8000/api/backend/prepare-refresh', {
      method: 'POST', signal: AbortSignal.timeout(5000),
      headers: { 'X-Backend-Refresh-Token': refreshToken },
    })
  } catch (error) {
    await fetch('http://127.0.0.1:8000/api/backend/cancel-refresh', {
      method: 'POST', signal: AbortSignal.timeout(2000),
      headers: { 'X-Backend-Refresh-Token': refreshToken },
    }).catch(() => {})
    throw error
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Backend refused refresh (${response.status}).`)
  }
  refreshing = true
  try {
    const oldApi = api
    const exited = new Promise((resolve) => oldApi.once('exit', resolve))
    stopChild(oldApi)
    await Promise.race([
      exited,
      new Promise((_, reject) => setTimeout(() => reject(new Error('Backend did not stop within 15 seconds.')), 15000)),
    ])
    startApi()
    if (!(await waitForBackend())) throw new Error('Backend did not become ready within 60 seconds.')
    console.log('Inference API refreshed and ready for a new run.')
  } catch (error) {
    if (await backendReady()) {
      await fetch('http://127.0.0.1:8000/api/backend/cancel-refresh', {
        method: 'POST', headers: { 'X-Backend-Refresh-Token': refreshToken },
      }).catch(() => {})
    }
    throw error
  } finally {
    refreshing = false
  }
}

dashboard = spawn(process.execPath, [vite], {
  cwd: root, stdio: ['inherit', 'inherit', 'inherit', 'ipc'], windowsHide: true,
})
dashboard.on('message', async (message) => {
  if (message?.type !== 'backend-control' || !dashboard.connected) return
  if (message.action === 'status') {
    dashboard.send({ type: 'backend-control-result', id: message.id, managed: !!api, refreshing })
    return
  }
  if (message.action !== 'refresh') return
  try {
    await refreshBackend()
    if (dashboard.connected) dashboard.send({ type: 'backend-control-result', id: message.id, ok: true })
  } catch (error) {
    if (dashboard.connected) dashboard.send({ type: 'backend-control-result', id: message.id, ok: false, error: error.message })
  }
})
dashboard.on('error', (error) => {
  console.error(`Could not start dashboard: ${error.message}`)
  shutdown(1)
})
dashboard.on('exit', (code) => shutdown(code || 0))
