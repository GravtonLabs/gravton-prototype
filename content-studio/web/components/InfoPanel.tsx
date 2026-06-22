'use client'
import { SessionState, downloadExport } from '@/lib/api'

const PHASES = ['intent', 'workplan', 'outline', 'draft', 'editor', 'done']
const BLOCK_LABELS: Record<string, string> = {
  topic: 'Topic', goal: 'Goal', audience: 'Audience',
  content_type: 'Content type', length: 'Length',
  primary_keyword: 'Primary keyword', secondary_keywords: 'Secondary keywords',
  prompts: 'Prompts', guardrails: 'Guardrails',
  sources: 'Sources', competitive_refs: 'Competitive refs',
}

interface Props {
  state: SessionState
  sessionId: string
}

function blockValue(v: unknown): string | null {
  if (v === null || v === undefined || v === '' || v === false) return null
  if (Array.isArray(v)) return v.length ? v.join(', ') : null
  return String(v)
}

export default function InfoPanel({ state, sessionId }: Props) {
  const phaseIdx = PHASES.indexOf(state.phase)
  const blocks = state.blocks as Record<string, unknown>
  const done = new Set(state.completed_blocks)
  const bg = state.background
  const draft = state.current_draft

  return (
    <div style={styles.panel}>
      {/* Stage rail */}
      <section style={styles.section}>
        <h3 style={styles.sectionTitle}>Stage</h3>
        <div style={styles.rail}>
          {PHASES.map((p, i) => (
            <div key={p} style={styles.step}>
              <span
                style={{
                  ...styles.dot,
                  background: i < phaseIdx ? 'var(--ok)' : i === phaseIdx ? 'var(--acc)' : '#2c3342',
                  boxShadow: i === phaseIdx ? '0 0 0 3px #c8a24a22' : undefined,
                }}
              />
              <span style={{ color: i <= phaseIdx ? 'var(--ink)' : 'var(--dim)', fontSize: 13 }}>
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Brief blocks */}
      <section style={styles.section}>
        <h3 style={styles.sectionTitle}>Brief</h3>
        {Object.entries(BLOCK_LABELS).map(([k, label]) => {
          const val = blockValue(blocks[k])
          if (!val) return null
          return (
            <div key={k} style={styles.block}>
              <span style={{ ...styles.blockKey, color: done.has(k) ? 'var(--ok)' : 'var(--acc)' }}>
                {label}:
              </span>{' '}
              <span style={styles.blockVal}>{val}</span>
            </div>
          )
        })}
        {Object.keys(BLOCK_LABELS).every(k => !blockValue(blocks[k])) && (
          <small style={styles.dim}>No brief filled yet.</small>
        )}
      </section>

      {/* Background agents */}
      <section style={styles.section}>
        <h3 style={styles.sectionTitle}>Background</h3>
        <div>
          {(['reference_grader', 'authority_sources', 'draft_builder'] as const).map(k => {
            const st = bg[k]
            const color = st === 'complete' ? 'var(--ok)' : st === 'failed' ? 'var(--fail)' : st === 'running' ? 'var(--warn)' : 'var(--dim)'
            return (
              <span key={k} style={{ ...styles.pill, color }}>
                {k.replace(/_/g, ' ')}: {st}
              </span>
            )
          })}
        </div>
        {bg.messages.slice(-5).map((m, i) => (
          <small key={i} style={{ ...styles.dim, display: 'block', marginTop: 2 }}>{m}</small>
        ))}
      </section>

      {/* Rubric */}
      {draft && (
        <section style={styles.section}>
          <h3 style={styles.sectionTitle}>Rubric</h3>
          <div style={styles.score}>{draft.rubric.pct}%</div>
          <small style={styles.dim}>{draft.rubric.passed}/{draft.rubric.total} checks passed</small>
          <div style={{ marginTop: 8 }}>
            {draft.rubric.checks
              .filter(c => c.result === 'fail')
              .slice(0, 8)
              .map((c, i) => (
                <div
                  key={i}
                  style={{
                    ...styles.annot,
                    borderColor: c.severity === 'blocker' ? 'var(--fail)' : 'var(--warn)',
                  }}
                >
                  <strong>{c.category}</strong>: {c.rule}
                  {c.detail ? ` — ${c.detail}` : ''}
                </div>
              ))}
          </div>
        </section>
      )}

      {/* Export */}
      {draft && (
        <section style={styles.section}>
          <h3 style={styles.sectionTitle}>Export</h3>
          <div style={styles.exportRow}>
            {(['md', 'html', 'txt'] as const).map(fmt => (
              <button
                key={fmt}
                onClick={() => downloadExport(sessionId, fmt)}
                style={styles.exportBtn}
              >
                {fmt.toUpperCase()}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Ruleset */}
      {state.ruleset_name && (
        <div style={{ padding: '0 14px 12px', fontSize: 11, color: 'var(--dim)' }}>
          ruleset: {state.ruleset_name}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
    width: 300,
    minWidth: 300,
    borderLeft: '1px solid var(--line)',
    background: 'var(--panel)',
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: 0,
  },
  section: {
    padding: '14px 14px 10px',
    borderBottom: '1px solid var(--line)',
  },
  sectionTitle: {
    margin: '0 0 8px',
    font: '600 10px/1 ui-sans-serif',
    letterSpacing: '.08em',
    textTransform: 'uppercase',
    color: 'var(--dim)',
  },
  rail: {
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  },
  step: {
    display: 'flex',
    alignItems: 'center',
    gap: 9,
    padding: '4px 0',
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    flex: 'none',
    transition: 'background .3s',
  },
  block: {
    fontSize: 13,
    padding: '3px 0',
    borderBottom: '1px solid #1b1f29',
  },
  blockKey: {
    fontWeight: 600,
    fontSize: 12,
  },
  blockVal: {
    color: 'var(--ink)',
  },
  pill: {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 999,
    fontSize: 11,
    marginRight: 6,
    marginBottom: 4,
    border: '1px solid #2a3040',
  },
  score: {
    font: '600 22px/1 ui-serif, Georgia, serif',
    color: 'var(--ink)',
    marginBottom: 2,
  },
  annot: {
    fontSize: 12,
    borderLeft: '3px solid var(--warn)',
    padding: '4px 8px',
    marginTop: 4,
    background: '#1b1a12',
  },
  exportRow: {
    display: 'flex',
    gap: 6,
  },
  exportBtn: {
    padding: '5px 10px',
    borderRadius: 7,
    border: '1px solid #2a3040',
    background: 'transparent',
    color: '#9fb2e0',
    fontSize: 12,
    cursor: 'pointer',
  },
  dim: {
    color: 'var(--dim)',
    fontSize: 12,
  },
}
