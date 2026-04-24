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
    <div className="min-h-full flex items-center justify-center bg-[#0a0a0a] px-4">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="flex flex-col items-center gap-3 mb-8">
          <div className="w-10 h-10 bg-violet-600 rounded-xl flex items-center justify-center">
            <Bot className="w-5 h-5 text-white" />
          </div>
          <div className="text-center">
            <h1 className="text-lg font-semibold text-white">Welcome back</h1>
            <p className="text-sm text-[#6b6b6b] mt-0.5">Sign in to your account</p>
          </div>
        </div>

        {/* Card */}
        <div className="bg-[#111111] border border-white/[0.08] rounded-xl p-6 space-y-4">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-[#a3a3a3]">Email</label>
              <input
                type="email"
                value={form.email}
                onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                placeholder="you@example.com"
                required
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2.5 text-sm text-white
                           placeholder-[#3f3f3f] outline-none transition-colors
                           focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/30"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-[#a3a3a3]">Password</label>
              <input
                type="password"
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                placeholder="••••••••"
                required
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2.5 text-sm text-white
                           placeholder-[#3f3f3f] outline-none transition-colors
                           focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/30"
              />
            </div>

            {error && (
              <div className="bg-red-500/8 border border-red-500/20 rounded-lg px-3 py-2">
                <p className="text-xs text-red-400">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-violet-600 hover:bg-violet-500 disabled:opacity-50
                         text-white text-sm font-medium py-2.5 rounded-lg transition-colors cursor-pointer"
            >
              {loading ? 'Signing in…' : 'Sign In'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-[#525252] mt-4">
          Don't have an account?{' '}
          <Link to="/register" className="text-violet-400 hover:text-violet-300 transition-colors">
            Create one
          </Link>
        </p>
      </div>
    </div>
  )
}
