export default function DashboardPage() {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      flexDirection: 'column',
      gap: '0.5rem',
      color: '#555',
      userSelect: 'none',
    }}>
      <p style={{ fontSize: '1.1rem' }}>Select a conversation</p>
      <p style={{ fontSize: '0.825rem' }}>or click "+ New Chat" to get started</p>
    </div>
  )
}
