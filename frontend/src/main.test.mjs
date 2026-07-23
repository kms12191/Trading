import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const source = readFileSync(resolve(__dirname, 'main.jsx'), 'utf8')

assert.match(
  source,
  /\{import\.meta\.env\.PROD\s*\?\s*<Analytics\s*\/>\s*:\s*null\}/,
  '로컬 개발 환경에서는 Analytics가 렌더링되어 React 앱을 중단시키면 안 됩니다.',
)
