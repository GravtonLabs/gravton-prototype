export default function SessionsHome() {
  return (
    <div style={styles.empty}>
      <span style={styles.mark}>✦</span>
      <p style={styles.msg}>Select a session from the sidebar,<br />or create a new one.</p>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  empty: {
    flex: 1,
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 14,
    color: 'var(--dim)',
  },
  mark: {
    fontSize: 32,
    color: '#2a3040',
  },
  msg: {
    textAlign: 'center',
    fontSize: 14,
    lineHeight: 1.7,
    margin: 0,
  },
}
