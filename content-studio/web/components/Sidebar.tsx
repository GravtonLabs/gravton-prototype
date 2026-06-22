'use client'
import { useState, useEffect, useCallback } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { listSessions, createSession, Session } from '@/lib/api'
import { logout, getUsername } from '@/lib/auth'

const PHASES: Record<string, string> = {
  intent: 'Intent',
  workplan: 'Workplan',
  outline: 'Outline',
  draft: 'Draft',
  editor: 'Editor',
  done: 'Done',
}

const PHASE_COLOR: Record<string, string> = {
  intent: 'var(--dim)',
  workplan: 'var(--acc)',
  outline: 'var(--acc)',
  draft: 'var(--warn)',
  editor: 'var(--ok)',
  done: '#5a9a6e',
}

export default function Sidebar() {
  const router = useRouter()
  const pathname = usePathname()
  const [sessions, setSessions] = useState<Session[]>([])
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const data = await listSessions()
      setSessions(data)
    } catch (e: unknown) {
      if ((e as Error).message === 'unauthorized') {
        router.replace('/login')
      }
    }
  }, [router])

  useEffect(() => {
    load()
    const t = setInterval(load, 8000)
    return () => clearInterval(t)
  }, [load])

  async function handleNew() {
    setCreating(true)
    setError('')
    try {
      const id = await createSession()
      await load()
      router.push(`/sessions/${id}`)
    } catch {
      setError('Could not create session.')
    } finally {
      setCreating(false)
    }
  }

  function handleLogout() {
    logout()
    router.replace('/login')
  }

  const [username, setUsername] = useState<string | null>(null)
  useEffect(() => { setUsername(getUsername()) }, [])

  const currentId = pathname.split('/sessions/')[1]?.split('/')[0]

  return (
    <aside style={styles.sidebar}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.logo}>
          <span style={styles.logoMark}>✦</span>
          <span style={styles.logoText}>Content Studio</span>
        </div>
        {username && <span style={styles.user}>{username}</span>}
      </div>

      {/* New session button */}
      <div style={styles.newWrap}>
        <button onClick={handleNew} disabled={creating} style={styles.newBtn}>
          {creating ? 'Creating…' : '+ New session'}
        </button>
        {error && <span style={styles.err}>{error}</span>}
      </div>

      {/* Session list */}
      <nav style={styles.nav}>
        {sessions.length === 0 ? (
          <p style={styles.empty}>No sessions yet.</p>
        ) : (
          sessions.map(s => (
            <button
              key={s.id}
              onClick={() => router.push(`/sessions/${s.id}`)}
              style={{
                ...styles.item,
                ...(s.id === currentId ? styles.itemActive : {}),
              }}
            >
              <span style={styles.title} title={s.title}>{s.title}</span>
              <span
                style={{
                  ...styles.phase,
                  color: PHASE_COLOR[s.phase] ?? 'var(--dim)',
                }}
              >
                {PHASES[s.phase] ?? s.phase}
              </span>
            </button>
          ))
        )}
      </nav>

      {/* Footer */}
      <div style={styles.footer}>
        <button onClick={handleLogout} style={styles.logoutBtn}>Sign out</button>
      </div>
    </aside>
  )
}

const styles: Record<string, React.CSSProperties> = {
  sidebar: {
    width: 240,
    minWidth: 240,
    background: 'var(--sidebar)',
    borderRight: '1px solid var(--line)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  header: {
    padding: '16px 14px 12px',
    borderBottom: '1px solid var(--line)',
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    marginBottom: 4,
  },
  logoMark: {
    fontSize: 16,
    color: 'var(--acc)',
  },
  logoText: {
    font: '600 14px/1 ui-serif, Georgia, serif',
    color: 'var(--ink)',
    letterSpacing: '.2px',
  },
  user: {
    fontSize: 11,
    color: 'var(--dim)',
    marginTop: 2,
    display: 'block',
    paddingLeft: 24,
  },
  newWrap: {
    padding: '10px 10px 6px',
  },
  newBtn: {
    width: '100%',
    padding: '8px 0',
    borderRadius: 8,
    border: '1px solid #2a3848',
    background: '#1a2030',
    color: 'var(--ink)',
    fontSize: 13,
    fontWeight: 500,
    cursor: 'pointer',
    letterSpacing: '.01em',
  },
  err: {
    fontSize: 11,
    color: 'var(--fail)',
    display: 'block',
    marginTop: 4,
    paddingLeft: 4,
  },
  nav: {
    flex: 1,
    overflowY: 'auto',
    padding: '4px 6px',
  },
  empty: {
    fontSize: 12,
    color: 'var(--dim)',
    padding: '12px 8px',
    margin: 0,
  },
  item: {
    width: '100%',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    gap: 3,
    padding: '9px 10px',
    borderRadius: 8,
    border: 'none',
    background: 'transparent',
    cursor: 'pointer',
    textAlign: 'left',
    marginBottom: 2,
  },
  itemActive: {
    background: '#1d2436',
    border: '1px solid #2a3040',
  },
  title: {
    fontSize: 13,
    color: 'var(--ink)',
    fontWeight: 500,
    maxWidth: '100%',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    display: 'block',
  },
  phase: {
    fontSize: 11,
    letterSpacing: '.04em',
    textTransform: 'uppercase',
    fontWeight: 500,
  },
  footer: {
    padding: '10px 10px 14px',
    borderTop: '1px solid var(--line)',
  },
  logoutBtn: {
    width: '100%',
    padding: '7px 0',
    borderRadius: 7,
    border: '1px solid #242833',
    background: 'transparent',
    color: 'var(--dim)',
    fontSize: 12,
    cursor: 'pointer',
  },
}
