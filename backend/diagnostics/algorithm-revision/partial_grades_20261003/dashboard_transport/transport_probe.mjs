// Run from the repository root with the API already listening on port 8000:
// node backend/diagnostics/algorithm-revision/dashboard_transport_20261003/transport_probe.mjs
// This reproduction helper was prepared after the captured experiments.
// It creates only temporary Vite proxies and performs GET requests; no inference.
import { createServer } from 'vite'
import http from 'node:http'
import { createHash } from 'node:crypto'

const target = 'http://127.0.0.1:8000'
const route = '/api/dashboard'
const sha256 = (body) => createHash('sha256').update(body).digest('hex')

async function fetchProbe(url, headers = {}, timeout = 5000) {
  const started = Date.now()
  let bytes = 0
  const chunks = []
  try {
    const response = await fetch(url, { headers, signal: AbortSignal.timeout(timeout) })
    for await (const chunk of response.body) {
      const buffer = Buffer.from(chunk)
      bytes += buffer.length
      chunks.push(buffer)
    }
    const body = Buffer.concat(chunks)
    return { status: response.status, advertised_bytes: Number(response.headers.get('content-length')), bytes, elapsed_ms: Date.now() - started, sha256: sha256(body), records: JSON.parse(body).recent_fruits.length }
  } catch (error) {
    return { bytes_before_error: bytes, elapsed_ms: Date.now() - started, error: error.message }
  }
}

async function nativeHttpProbe(url) {
  return new Promise((resolve) => {
    const started = Date.now()
    let bytes = 0
    const chunks = []
    const request = http.get(url, { headers: { connection: 'close' } }, (response) => {
      response.on('data', (chunk) => { bytes += chunk.length; chunks.push(chunk) })
      response.on('end', () => {
        const body = Buffer.concat(chunks)
        resolve({ status: response.statusCode, advertised_bytes: Number(response.headers['content-length']), bytes, elapsed_ms: Date.now() - started, sha256: sha256(body), records: JSON.parse(body).recent_fruits.length })
      })
      response.on('error', (error) => resolve({ bytes_before_error: bytes, elapsed_ms: Date.now() - started, error: error.message }))
    })
    request.setTimeout(5000, () => { request.destroy(); resolve({ bytes_before_error: bytes, elapsed_ms: Date.now() - started, error: 'socket timeout' }) })
    request.on('error', (error) => resolve({ bytes_before_error: bytes, elapsed_ms: Date.now() - started, error: error.message }))
  })
}

for (const headers of [{}, { connection: 'close' }, { connection: 'keep-alive' }]) {
  console.log(JSON.stringify({ transport: 'direct fetch', headers, ...await fetchProbe(target + route, headers, 3500) }))
}

for (const mode of ['fetch only', 'native keep-alive']) {
  const agent = mode === 'native keep-alive' ? new http.Agent({ keepAlive: true }) : null
  const options = mode === 'fetch only' ? { target, fetch: globalThis.fetch } : { target, agent, headers: { connection: 'keep-alive' } }
  const server = await createServer({ configFile: false, logLevel: 'warn', server: { host: '127.0.0.1', port: 0, strictPort: true, watch: { ignored: ['**/backend/**'] }, proxy: { [route]: options, '/api': target } } })
  try {
    await server.listen()
    const address = server.httpServer.address()
    const url = `http://127.0.0.1:${address.port}${route}`
    console.log(JSON.stringify({ transport: mode + ' / Node HTTP client', ...await nativeHttpProbe(url) }))
    console.log(JSON.stringify({ transport: mode + ' / fetch client', ...await fetchProbe(url) }))
  } finally {
    await server.close()
    agent?.destroy()
    console.log(JSON.stringify({ temporary_proxy_closed: true, mode }))
  }
}
