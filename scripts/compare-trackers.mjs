import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const python = path.join(root, 'backend', 'venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
if (!existsSync(python)) {
  console.error('The backend virtual environment is missing. Follow the README setup instructions first.')
  process.exit(1)
}
const child = spawn(python, [path.join(root, 'backend', 'tracker_comparison.py'), ...process.argv.slice(2)], {
  cwd: root,
  stdio: 'inherit',
  shell: false,
})
child.on('error', error => {
  console.error(`Cannot start tracker comparison: ${error.message}`)
  process.exitCode = 1
})
child.on('exit', (code, signal) => {
  process.exitCode = code ?? (signal ? 1 : 0)
})
