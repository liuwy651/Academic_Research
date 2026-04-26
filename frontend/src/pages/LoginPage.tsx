import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Bot } from 'lucide-react'
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
        ?.response?.data?.detail ?? 'Invalid email or password'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-full flex items-center justify-center px-4" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="flex flex-col items-center gap-3 mb-8">
          <div className="w-10 h-10 bg-violet-600 rounded-xl flex items-center justify-center">
            <Bot className="w-5 h-5 text-white" />
          </div>
          <div className="text-center">
            <h1 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>Welcome back</h1>
            <p className="text-sm mt-0.5" style={{ color: 'var(--text-tertiary)' }}>Sign in to your account</p>
          </div>
        </div>

        {/* Card */}
        <div className="border rounded-xl p-6 space-y-4" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-color)' }}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="block text-xs font-medium" style={{ color: 'var(--text-tertiary)' }}>Email</label>
              <input
                type="email"
                value={form.email}
                onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                placeholder="you@example.com"
                required
                className="w-full rounded-lg px-3 py-2.5 text-sm outline-none transition-colors"
                style={{
                  backgroundColor: 'var(--input-bg)',
                  color: 'var(--text-primary)',
                  borderColor: 'var(--input-border)',
                  border: `1px solid var(--input-border)`,
                }}
                onFocus={(e) => {
                  e.currentTarget.style.borderColor = '#8b5cf6'
                  e.currentTarget.style.boxShadow = '0 0 0 1px rgba(139, 92, 246, 0.3)'
                }}
                onBlur={(e) => {
                  e.currentTarget.style.borderColor = 'var(--input-border)'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs font-medium" style={{ color: 'var(--text-tertiary)' }}>Password</label>
              <input
                type="password"
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                placeholder="••••••••"
                required
                className="w-full rounded-lg px-3 py-2.5 text-sm outline-none transition-colors"
                style={{
                  backgroundColor: 'var(--input-bg)',
                  color: 'var(--text-primary)',
                  borderColor: 'var(--input-border)',
                  border: `1px solid var(--input-border)`,
                }}
                onFocus={(e) => {
                  e.currentTarget.style.borderColor = '#8b5cf6'
                  e.currentTarget.style.boxShadow = '0 0 0 1px rgba(139, 92, 246, 0.3)'
                }}
                onBlur={(e) => {
                  e.currentTarget.style.borderColor = 'var(--input-border)'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              />
            </div>

            {error && (
              <div className="rounded-lg px-3 py-2" style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', borderColor: 'rgba(239, 68, 68, 0.2)', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
                <p className="text-xs" style={{ color: '#ef4444' }}>{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full text-white text-sm font-medium py-2.5 rounded-lg transition-colors cursor-pointer disabled:opacity-50 bg-violet-600 hover:bg-violet-500"
            >
              {loading ? 'Signing in…' : 'Sign In'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs mt-4" style={{ color: 'var(--text-muted)' }}>
          Don't have an account?{' '}
          <Link to="/register" className="text-violet-500 hover:text-violet-600 transition-colors">
            Create one
          </Link>
        </p>
      </div>
    </div>
  )
}
