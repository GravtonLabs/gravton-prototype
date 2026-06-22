import { getToken } from './auth'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ''

function authHeaders() {
  const token = getToken()
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

export interface Session {
  id: string
  title: string
  phase: string
  created_at: string | null
  updated_at: string | null
}

export interface SessionState {
  session_id: string
  phase: string
  blocks: Record<string, unknown>
  completed_blocks: string[]
  pending_required_block: string | null
  pending_soft_block: string | null
  history: Array<{ role: string; content: string }>
  workplan: unknown
  outline: unknown
  background: {
    reference_grader: string
    authority_sources: string
    draft_builder: string
    messages: string[]
  }
  current_draft: {
    title: string
    markdown: string
    word_count: number
    target_words: number
    rubric: { pct: number; passed: number; total: number; checks: RubricCheck[] }
    ai_signals: Array<{ signal: string; example?: string; fix?: string }>
    annotations: RubricCheck[]
    built_at: string
  } | null
  ruleset_name: string | null
}

export interface RubricCheck {
  id: string
  category: string
  rule: string
  result: 'pass' | 'fail' | 'na'
  detail?: string
  severity?: string
}

export async function listSessions(): Promise<Session[]> {
  const res = await fetch(`${API_URL}/api/sessions`, { headers: authHeaders() })
  if (res.status === 401) throw new Error('unauthorized')
  if (!res.ok) throw new Error('failed to list sessions')
  return res.json()
}

export async function createSession(): Promise<string> {
  const res = await fetch(`${API_URL}/api/sessions`, {
    method: 'POST',
    headers: authHeaders(),
  })
  if (res.status === 401) throw new Error('unauthorized')
  if (!res.ok) throw new Error('failed to create session')
  const { session_id } = await res.json()
  return session_id
}

export async function getSessionState(id: string): Promise<SessionState> {
  const res = await fetch(`${API_URL}/api/sessions/${id}/state`, {
    headers: authHeaders(),
  })
  if (res.status === 401) throw new Error('unauthorized')
  if (!res.ok) throw new Error('failed to get state')
  return res.json()
}

export async function sendAction(id: string, action: string): Promise<{ reply: string; state: SessionState }> {
  const res = await fetch(`${API_URL}/api/sessions/${id}/action`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ action }),
  })
  if (!res.ok) throw new Error('failed to send action')
  return res.json()
}

export async function resetSession(id: string): Promise<SessionState> {
  const res = await fetch(`${API_URL}/api/sessions/${id}/reset`, {
    method: 'POST',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error('failed to reset')
  const { state } = await res.json()
  return state
}

export function exportUrl(id: string, fmt: 'md' | 'html' | 'txt'): string {
  const token = getToken()
  // For downloads, we open directly — token passed via header isn't possible for <a> links.
  // Instead the backend should allow this, or we fetch and trigger download manually.
  return `${API_URL}/api/sessions/${id}/export?fmt=${fmt}&token=${token ?? ''}`
}

export async function downloadExport(id: string, fmt: 'md' | 'html' | 'txt'): Promise<void> {
  const res = await fetch(`${API_URL}/api/sessions/${id}/export?fmt=${fmt}`, {
    headers: authHeaders(),
  })
  if (!res.ok) return
  const blob = await res.blob()
  const disposition = res.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="([^"]+)"/)
  const filename = match ? match[1] : `export.${fmt}`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function streamMessage(
  id: string,
  text: string,
  urls: string[],
  onDelta: (token: string) => void,
  onSeparator: () => void,
  onDone: (state: SessionState) => void,
  onError: (err: string) => void,
): () => void {
  let cancelled = false

  ;(async () => {
    try {
      const token = getToken()
      const res = await fetch(`${API_URL}/api/sessions/${id}/message`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ text, urls }),
      })

      if (!res.ok || !res.body) {
        onError(`HTTP ${res.status}`)
        return
      }

      const reader = res.body.getReader()
      const dec = new TextDecoder()
      let buf = ''

      while (!cancelled) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() ?? ''
        for (const part of parts) {
          if (!part.startsWith('data: ')) continue
          try {
            const ev = JSON.parse(part.slice(6))
            if (ev.type === 'delta') onDelta(ev.text)
            else if (ev.type === 'separator') onSeparator()
            else if (ev.type === 'done') { onDone(ev.state); return }
          } catch {
            // malformed event — skip
          }
        }
      }
    } catch (e) {
      if (!cancelled) onError(String(e))
    }
  })()

  return () => { cancelled = true }
}
