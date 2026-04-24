import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { useAuthStore } from '../store/authStore'

export default function LoginPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore(s => s.setAuth)
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const data = await authApi.login(form.email, form.password)
      setAuth(data.access_token, data.user)
      navigate('/', { replace: true })
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? 'Login failed'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card" style={{ maxWidth: 400, marginInline: 'auto', marginTop: '4rem' }}>
      <h1 style={{ marginBottom: '1.5rem' }}>Sign In</h1>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <input
          type="email"
          placeholder="Email"
          value={form.email}
          onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
          required
          style={inputStyle}
        />
        <input
          type="password"
          placeholder="Password"
          value={form.password}
          onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
          required
          style={inputStyle}
        />

        {error && <p style={{ color: '#ef4444', margin: 0 }}>{error}</p>}

        <button type="submit" disabled={loading} style={{ marginTop: '0.5rem' }}>
          {loading ? 'Signing in…' : 'Sign In'}
        </button>
      </form>

      <p style={{ marginTop: '1rem', fontSize: '0.875rem' }}>
        No account?{' '}
        <Link to="/register" style={{ color: '#646cff' }}>Register</Link>
      </p>
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  padding: '0.5rem 0.75rem',
  borderRadius: '6px',
  border: '1px solid #555',
  background: '#1a1a1a',
  color: '#fff',
  fontSize: '1rem',
  width: '100%',
  boxSizing: 'border-box',
}
