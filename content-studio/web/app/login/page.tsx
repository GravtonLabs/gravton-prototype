'use client'
import { useState, FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { login } from '@/lib/auth'

export default function LoginPage() {
  const router = useRouter()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!username || !password) return
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      router.replace('/sessions')
    } catch {
      setError('Invalid username or password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <div style={styles.logo}>
          <span style={styles.logoMark}>✦</span>
          <span style={styles.logoText}>Content Studio</span>
        </div>
        <p style={styles.sub}>Sign in to your workspace</p>

        <form onSubmit={handleSubmit} style={styles.form}>
          <label style={styles.label}>Username</label>
          <input
            style={styles.input}
            value={username}
            onChange={e => setUsername(e.target.value)}
            placeholder="alice"
            autoComplete="username"
            autoFocus
          />

          <label style={{ ...styles.label, marginTop: 14 }}>Password</label>
          <input
            type="password"
            style={styles.input}
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="••••••••"
            autoComplete="current-password"
          />

          {error && <p style={styles.error}>{error}</p>}

          <button type="submit" style={styles.btn} disabled={loading}>
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    height: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--bg)',
  },
  card: {
    width: 360,
    padding: '36px 32px',
    background: 'var(--panel)',
    border: '1px solid var(--line)',
    borderRadius: 14,
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    gap: 9,
    marginBottom: 6,
  },
  logoMark: {
    fontSize: 22,
    color: 'var(--acc)',
  },
  logoText: {
    font: '600 18px/1 ui-serif, Georgia, serif',
    color: 'var(--ink)',
    letterSpacing: '.2px',
  },
  sub: {
    color: 'var(--dim)',
    fontSize: 13,
    margin: '0 0 28px',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
  },
  label: {
    fontSize: 12,
    fontWeight: 500,
    color: 'var(--dim)',
    marginBottom: 6,
    letterSpacing: '.04em',
    textTransform: 'uppercase',
  },
  input: {
    padding: '10px 12px',
    borderRadius: 8,
    border: '1px solid #2a3040',
    background: '#0b0d12',
    color: 'var(--ink)',
    fontSize: 14,
    outline: 'none',
  },
  error: {
    fontSize: 13,
    color: 'var(--fail)',
    margin: '10px 0 0',
  },
  btn: {
    marginTop: 22,
    padding: '11px 0',
    borderRadius: 9,
    border: 'none',
    background: 'var(--acc)',
    color: '#0e1014',
    fontWeight: 600,
    fontSize: 14,
    cursor: 'pointer',
    letterSpacing: '.02em',
  },
}
