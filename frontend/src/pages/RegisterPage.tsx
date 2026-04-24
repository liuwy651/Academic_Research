import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { useAuthStore } from '../store/authStore'

export default function RegisterPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore(s => s.setAuth)
  const [form, setForm] = useState({ email: '', password: '', full_name: '' })
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const data = await authApi.register(form.email, form.password, form.full_name || undefined)
      setAuth(data.access_token, data.user)
      navigate('/', { replace: true })
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })
        ?.response?.data?.detail
      const msg = Array.isArray(detail)
        ? detail.map((d: { msg?: string }) => d.msg).join(', ')
        : (detail as string | undefined) ?? 'Registration failed'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card" style={{ maxWidth: 400, marginInline: 'auto', marginTop: '4rem' }}>
      <h1 style={{ marginBottom: '1.5rem' }}>Create Account</h1>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <input
          type="text"
          placeholder="Full name (optional)"
          value={form.full_name}
          onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
          style={inputStyle}
        />
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
          placeholder="Password (min 8 chars)"
          value={form.password}
          onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
          required
          style={inputStyle}
        />

        {error && <p style={{ color: '#ef4444', margin: 0 }}>{error}</p>}

        <button type="submit" disabled={loading} style={{ marginTop: '0.5rem' }}>
          {loading ? 'Creating account…' : 'Register'}
        </button>
      </form>

      <p style={{ marginTop: '1rem', fontSize: '0.875rem' }}>
        Already have an account?{' '}
        <Link to="/login" style={{ color: '#646cff' }}>Sign In</Link>
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
