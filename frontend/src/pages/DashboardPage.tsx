import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

export default function DashboardPage() {
  const navigate = useNavigate()
  const { user, clearAuth } = useAuthStore()

  const handleLogout = () => {
    clearAuth()
    navigate('/login', { replace: true })
  }

  return (
    <div className="card" style={{ maxWidth: 500, marginInline: 'auto', marginTop: '4rem' }}>
      <h1>Agent 对话系统</h1>
      <p style={{ color: '#888', marginBottom: '1.5rem' }}>Welcome back</p>

      {user && (
        <table style={{ marginInline: 'auto', borderSpacing: '1rem 0.4rem', textAlign: 'left' }}>
          <tbody>
            <tr>
              <td style={{ color: '#888' }}>Name</td>
              <td>{user.full_name ?? '—'}</td>
            </tr>
            <tr>
              <td style={{ color: '#888' }}>Email</td>
              <td>{user.email}</td>
            </tr>
            <tr>
              <td style={{ color: '#888' }}>ID</td>
              <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{user.id}</td>
            </tr>
          </tbody>
        </table>
      )}

      <button onClick={handleLogout} style={{ marginTop: '2rem', background: '#333' }}>
        Sign Out
      </button>
    </div>
  )
}
