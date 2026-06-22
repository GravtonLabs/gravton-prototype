'use client'
import { useState, useEffect, useRef, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { getSessionState, sendAction, resetSession, SessionState, streamMessage } from '@/lib/api'
import InfoPanel from './InfoPanel'

interface Message {
  role: 'user' | 'assistant'
  content: string
  isThinking?: boolean
}

function mdToHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br>')
}

interface Props {
  sessionId: string
}

export default function ChatArea({ sessionId }: Props) {
  const router = useRouter()
  const [state, setState] = useState<SessionState | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const logRef = useRef<HTMLDivElement>(null)
  const cancelRef = useRef<(() => void) | null>(null)
  const shownDraftRef = useRef<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const scrollToBottom = () => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }

  const loadState = useCallback(async () => {
    try {
      const s = await getSessionState(sessionId)
      setState(s)
      // show new draft card when draft appears for the first time
      if (s.current_draft && s.current_draft.built_at !== shownDraftRef.current) {
        shownDraftRef.current = s.current_draft.built_at
        setMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: `**Draft ready** · ${s.current_draft!.word_count} words · *${s.current_draft!.title}*\n\n${s.current_draft!.markdown}`,
          },
        ])
        setTimeout(scrollToBottom, 50)
      }
    } catch (e: unknown) {
      if ((e as Error).message === 'unauthorized') router.replace('/login')
    }
  }, [sessionId, router])

  // Initial load — reconstruct history
  useEffect(() => {
    ;(async () => {
      try {
        const s = await getSessionState(sessionId)
        setState(s)
        const hist = (s.history as Array<{ role: string; content: string }>) ?? []
        const msgs: Message[] = hist.map(h => ({
          role: h.role as 'user' | 'assistant',
          content: h.content,
        }))
        if (msgs.length === 0) {
          msgs.push({ role: 'assistant', content: 'What would you like to create today?' })
        }
        setMessages(msgs)
        setTimeout(scrollToBottom, 50)
      } catch (e: unknown) {
        if ((e as Error).message === 'unauthorized') router.replace('/login')
      }
    })()
  }, [sessionId, router])

  // Poll for background job state updates
  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(loadState, 3000)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [loadState])

  async function send() {
    const raw = input.trim()
    if (!raw || busy) return

    let text = raw
    let urls: string[] = []
    if (raw.includes('|')) {
      const [t, u] = raw.split('|')
      text = t.trim()
      urls = u.split(',').map(s => s.trim()).filter(Boolean)
    }

    setInput('')
    setError('')
    setBusy(true)

    setMessages(prev => [
      ...prev,
      { role: 'user', content: raw },
      { role: 'assistant', content: '', isThinking: true },
    ])
    setTimeout(scrollToBottom, 20)

    let botContent = ''
    let firstToken = true

    const cancel = streamMessage(
      sessionId,
      text,
      urls,
      (token) => {
        botContent += token
        if (firstToken) {
          firstToken = false
          setMessages(prev => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            if (last?.isThinking) updated[updated.length - 1] = { role: 'assistant', content: botContent }
            return updated
          })
        } else {
          setMessages(prev => {
            const updated = [...prev]
            updated[updated.length - 1] = { role: 'assistant', content: botContent }
            return updated
          })
        }
        scrollToBottom()
      },
      () => {
        // separator: start new bubble
        botContent = ''
        setMessages(prev => [...prev, { role: 'assistant', content: '' }])
      },
      (newState) => {
        setState(newState)
        setBusy(false)
        cancelRef.current = null
      },
      (err) => {
        setError(`Stream error: ${err}`)
        setBusy(false)
        setMessages(prev => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (last?.isThinking || last?.content === '') {
            updated[updated.length - 1] = { role: 'assistant', content: `*(Something went wrong: ${err})*` }
          }
          return updated
        })
      },
    )

    cancelRef.current = cancel
  }

  async function handleAction(action: string) {
    if (busy) return
    setBusy(true)
    try {
      const result = await sendAction(sessionId, action)
      setState(result.state)
      setMessages(prev => [...prev, { role: 'assistant', content: result.reply }])
      setTimeout(scrollToBottom, 50)
    } catch {
      setError('Action failed.')
    } finally {
      setBusy(false)
    }
  }

  async function handleReset() {
    if (!confirm('Reset this session? All progress will be lost.')) return
    setBusy(true)
    try {
      const newState = await resetSession(sessionId)
      setState(newState)
      shownDraftRef.current = null
      setMessages([{ role: 'assistant', content: 'What would you like to create today?' }])
    } catch {
      setError('Reset failed.')
    } finally {
      setBusy(false)
    }
  }

  const phase = state?.phase ?? 'intent'

  return (
    <div style={styles.wrap}>
      {/* Chat column */}
      <div style={styles.chat}>
        {/* Header */}
        <div style={styles.header}>
          <h1 style={styles.h1}>Aqiira</h1>
          <small style={styles.subtitle}>Content Studio</small>
          <span style={{ flex: 1 }} />
          <button onClick={handleReset} style={styles.resetBtn} disabled={busy}>
            Reset
          </button>
        </div>

        {/* Message log */}
        <div ref={logRef} style={styles.log}>
          {messages.map((m, i) => (
            <div
              key={i}
              style={{
                ...styles.bubble,
                ...(m.role === 'user' ? styles.userBubble : styles.botBubble),
              }}
            >
              {m.isThinking ? (
                <div className="thinking">
                  <span /><span /><span />
                </div>
              ) : m.role === 'assistant' ? (
                <span dangerouslySetInnerHTML={{ __html: mdToHtml(m.content) }} />
              ) : (
                m.content
              )}
            </div>
          ))}
          {error && <p style={styles.errMsg}>{error}</p>}
        </div>

        {/* Action buttons */}
        {phase === 'workplan' && (
          <div style={styles.actions}>
            <button
              style={styles.actionBtn}
              onClick={() => handleAction('approve_workplan')}
              disabled={busy}
            >
              Approve workplan →
            </button>
          </div>
        )}
        {phase === 'outline' && (
          <div style={styles.actions}>
            <button
              style={styles.actionBtn}
              onClick={() => handleAction('accept_outline')}
              disabled={busy}
            >
              Accept outline →
            </button>
          </div>
        )}
        {phase === 'editor' && (
          <div style={styles.actions}>
            <button
              style={styles.actionBtn}
              onClick={() => handleAction('mark_done')}
              disabled={busy}
            >
              Mark done ✓
            </button>
          </div>
        )}

        {/* Composer */}
        <div style={styles.composer}>
          <input
            style={styles.input}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder={
              phase === 'intent'
                ? 'Describe what you want to create… (add URLs after |)'
                : phase === 'draft'
                ? 'Draft is building — hang tight…'
                : 'Type a message…'
            }
            disabled={busy || phase === 'draft'}
          />
          <button
            style={{ ...styles.sendBtn, opacity: busy ? 0.5 : 1 }}
            onClick={send}
            disabled={busy}
          >
            Send
          </button>
        </div>
      </div>

      {/* Info panel */}
      {state && <InfoPanel state={state} sessionId={sessionId} />}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  wrap: {
    display: 'flex',
    height: '100%',
    overflow: 'hidden',
  },
  chat: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    borderRight: '1px solid var(--line)',
  },
  header: {
    padding: '14px 20px',
    borderBottom: '1px solid var(--line)',
    display: 'flex',
    alignItems: 'baseline',
    gap: 10,
  },
  h1: {
    margin: 0,
    font: '600 15px/1 ui-serif, Georgia, serif',
    color: 'var(--ink)',
    letterSpacing: '.2px',
  },
  subtitle: {
    color: 'var(--dim)',
    fontSize: 12,
  },
  resetBtn: {
    padding: '5px 10px',
    borderRadius: 7,
    border: '1px solid #2a3040',
    background: 'transparent',
    color: 'var(--dim)',
    fontSize: 12,
    cursor: 'pointer',
  },
  log: {
    flex: 1,
    overflowY: 'auto',
    padding: '20px',
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
  bubble: {
    maxWidth: '78%',
    padding: '9px 13px',
    borderRadius: 13,
    fontSize: 14,
    lineHeight: 1.6,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
  userBubble: {
    marginLeft: 'auto',
    background: '#283150',
    color: 'var(--ink)',
  },
  botBubble: {
    background: '#191d27',
    color: 'var(--ink)',
  },
  errMsg: {
    color: 'var(--fail)',
    fontSize: 13,
    margin: '4px 0',
  },
  actions: {
    padding: '0 20px 10px',
    display: 'flex',
    gap: 8,
  },
  actionBtn: {
    padding: '9px 16px',
    borderRadius: 9,
    border: '1px solid var(--acc)',
    background: 'transparent',
    color: 'var(--acc)',
    fontSize: 13,
    fontWeight: 500,
    cursor: 'pointer',
    letterSpacing: '.02em',
  },
  composer: {
    display: 'flex',
    gap: 8,
    padding: 14,
    borderTop: '1px solid var(--line)',
  },
  input: {
    flex: 1,
    padding: '11px 13px',
    borderRadius: 9,
    border: '1px solid #2a3040',
    background: '#0b0d12',
    color: 'var(--ink)',
    fontSize: 14,
    outline: 'none',
  },
  sendBtn: {
    padding: '10px 16px',
    borderRadius: 9,
    border: '1px solid #36405c',
    background: '#1d2436',
    color: '#dce3f5',
    fontSize: 14,
    cursor: 'pointer',
    fontWeight: 500,
  },
}
