import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Eye, EyeOff, Layers, Lock, Play, Star, User, Users } from 'lucide-react'
import toast from 'react-hot-toast'
import { login } from '../api/auth'
import useStore from '../store/useStore'

const demoUsers = [
  { username: 'vaibhav', password: 'admin123', role: 'admin' },
  { username: 'rohit', password: 'admin123', role: 'admin' },
  { username: 'manager1', password: 'mgr123', role: 'manager' },
  { username: 'employee1', password: 'emp123', role: 'employee' },
]

const roleBadgeStyles = {
  admin: 'border-blue-200 bg-blue-50 text-blue-700',
  manager: 'border-violet-200 bg-violet-50 text-violet-700',
  employee: 'border-emerald-200 bg-emerald-50 text-emerald-700',
}

const roleAvatarStyles = {
  admin: 'bg-blue-50 text-blue-700',
  manager: 'bg-violet-50 text-violet-700',
  employee: 'bg-emerald-50 text-emerald-700',
}

const roleIcons = {
  admin: Star,
  manager: Users,
  employee: User,
}

export default function Login() {
  const navigate = useNavigate()
  const { setUser } = useStore()

  const [form, setForm] = useState({ username: '', password: '' })
  const [showPw, setShowPw] = useState(false)
  const [rememberMe, setRememberMe] = useState(false)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState({})

  const validate = () => {
    const nextErrors = {}
    if (!form.username.trim()) nextErrors.username = 'Username is required'
    if (!form.password) nextErrors.password = 'Password is required'
    return nextErrors
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const nextErrors = validate()
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors)
      return
    }

    setErrors({})
    setLoading(true)

    try {
      const data = await login(form.username.trim(), form.password)
      setUser(data.user || { username: form.username, name: form.username, role: 'employee' })
      toast.success(`Welcome back, ${data.user?.name || form.username}!`)
      navigate('/dashboard', { replace: true })
    } catch (error) {
      const message = error.response?.data?.error || error.response?.data?.message || 'Invalid credentials'
      toast.error(message)
      setErrors({ form: message })
    } finally {
      setLoading(false)
    }
  }

  const fillDemo = (user) => {
    setForm({ username: user.username, password: user.password })
    setErrors({})
  }

  const quickDemoFill = () => {
    fillDemo(demoUsers[0])
    toast.success('Demo credentials filled')
  }

  return (
    <div className="flex w-full min-h-screen items-start justify-center overflow-y-auto bg-[linear-gradient(135deg,#0f7a5a_0%,#0f6e9e_50%,#1a3fa8_100%)] p-0 sm:p-5 md:items-center">
      <div className="flex h-auto w-[min(980px,97vw)] overflow-hidden rounded-none border border-white/10 bg-transparent shadow-[0_40px_90px_rgba(0,0,0,0.4),0_0_0_1px_rgba(255,255,255,0.1)] sm:rounded-[22px] md:h-[min(620px,94vh)]">
        <section
          className="relative hidden flex-[1.15] overflow-hidden md:block"
          style={{
            background:
              'linear-gradient(180deg, #0a1628 0%, #0d2a5e 18%, #1a4a8a 32%, #2160a8 42%, #e8923a 58%, #e85d1a 65%, #c0392b 72%, #7b1c1c 80%, #3d0e0e 100%)',
          }}
        >
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              backgroundImage: `
                radial-gradient(1px 1px at 12% 8%, rgba(255,255,255,.9) 0%, transparent 100%),
                radial-gradient(1px 1px at 28% 5%, rgba(255,255,255,.7) 0%, transparent 100%),
                radial-gradient(1.5px 1.5px at 45% 10%, rgba(255,255,255,.8) 0%, transparent 100%),
                radial-gradient(1px 1px at 60% 6%, rgba(255,255,255,.6) 0%, transparent 100%),
                radial-gradient(1px 1px at 75% 12%, rgba(255,255,255,.7) 0%, transparent 100%),
                radial-gradient(1px 1px at 88% 4%, rgba(255,255,255,.9) 0%, transparent 100%),
                radial-gradient(1px 1px at 18% 18%, rgba(255,255,255,.5) 0%, transparent 100%),
                radial-gradient(1px 1px at 55% 20%, rgba(255,255,255,.6) 0%, transparent 100%)
              `,
            }}
          />

          <div className="absolute right-[18%] top-[12%] h-[42px] w-[42px] rounded-full bg-[radial-gradient(circle_at_38%_38%,#fff8e1,#ffd54f)] shadow-[0_0_20px_6px_rgba(255,220,80,0.3),0_0_60px_20px_rgba(255,200,50,0.1)]" />
          <div className="absolute bottom-[28%] left-1/2 h-[60px] w-[200px] -translate-x-1/2 rounded-full bg-[radial-gradient(ellipse,rgba(255,140,50,.6)_0%,rgba(255,100,20,.3)_40%,transparent_70%)] blur-[8px]" />

          <svg className="pointer-events-none absolute inset-x-0 bottom-0 w-full" viewBox="0 0 520 220" preserveAspectRatio="xMidYMax meet">
            <rect x="0" y="160" width="520" height="60" fill="rgba(15,45,100,0.75)" />
            <line x1="0" y1="172" x2="520" y2="172" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
            <line x1="0" y1="182" x2="520" y2="182" stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
            <line x1="0" y1="194" x2="520" y2="194" stroke="rgba(255,255,255,0.05)" strokeWidth="1" />

            <rect x="0" y="120" width="18" height="40" fill="#0a1628" />
            <rect x="20" y="105" width="22" height="55" fill="#0c1e3a" />
            <rect x="44" y="115" width="14" height="45" fill="#0a1628" />
            <rect x="60" y="90" width="28" height="70" fill="#0d2244" />
            <rect x="90" y="108" width="18" height="52" fill="#0a1830" />
            <rect x="110" y="95" width="20" height="65" fill="#0c2040" />
            <rect x="130" y="70" width="32" height="90" fill="#0e2650" />
            <rect x="164" y="82" width="24" height="78" fill="#0d2244" />
            <polygon points="192,40 196,82 188,82" fill="#0e2650" />
            <rect x="188" y="82" width="16" height="78" fill="#0e2650" />
            <rect x="206" y="78" width="28" height="82" fill="#0c1e40" />
            <rect x="236" y="62" width="36" height="98" fill="#102860" />
            <ellipse cx="272" cy="62" rx="18" ry="10" fill="#0e2650" />
            <rect x="254" y="62" width="36" height="98" fill="#0e2650" />
            <rect x="292" y="75" width="26" height="85" fill="#0c2244" />
            <polygon points="322,28 326,75 318,75" fill="#0a1e44" />
            <rect x="318" y="75" width="14" height="85" fill="#0c2040" />
            <rect x="334" y="88" width="30" height="72" fill="#0d2244" />
            <rect x="366" y="72" width="22" height="88" fill="#0c1e40" />
            <rect x="390" y="80" width="28" height="80" fill="#0a1830" />
            <rect x="420" y="65" width="34" height="95" fill="#0e2650" />
            <polygon points="454,30 458,65 450,65" fill="#0c2040" />
            <rect x="450" y="65" width="16" height="95" fill="#0c2040" />
            <rect x="468" y="85" width="20" height="75" fill="#0a1628" />
            <rect x="490" y="72" width="30" height="88" fill="#0d2244" />
          </svg>

          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[30%] bg-gradient-to-b from-[rgba(30,80,150,0.6)] to-[rgba(15,40,90,0.8)]" />

          <div className="absolute left-[26px] right-[26px] top-[26px] z-10">
            <h2 className="font-heading text-[1.3rem] font-bold leading-[1.25] text-white">
              Welcome Back,
              <br />
              Adventurer.
            </h2>
            <p className="mt-1 text-[0.78rem] text-white/75">Your next business journey awaits.</p>
          </div>

          <div className="absolute bottom-[22px] left-[22px] right-[22px] z-10 rounded-[14px] border border-white/20 bg-white/10 p-[16px_18px] backdrop-blur-xl">
            <h3 className="font-heading text-[1rem] font-bold text-white">Plan. Book. Travel.</h3>
            <p className="mt-1 text-[0.75rem] leading-[1.5] text-white/75">
              AI-powered corporate travel - flights, hotels, expenses and live weather in one place.
            </p>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {['Amadeus API', 'Gemini AI', 'OCR Receipts', 'Live Weather'].map((item) => (
                <span
                  key={item}
                  className="rounded-full border border-white/20 bg-white/15 px-2.5 py-1 text-[0.68rem] font-semibold tracking-[0.03em] text-white"
                >
                  {item}
                </span>
              ))}
            </div>
          </div>
        </section>

        <section className="w-full overflow-y-auto bg-[#fff] p-6 sm:p-7 md:w-[380px] md:min-w-[380px] md:p-[34px_36px]">
          <div className="mb-5 flex items-center gap-[10px]">
            <div className="flex h-10 w-10 items-center justify-center rounded-[10px] bg-[linear-gradient(135deg,#1a56db,#0891b2)] text-white shadow-md">
              <Layers size={18} />
            </div>
            <div>
              <div className="text-[0.95rem] font-bold leading-[1.2] text-gray-900">TravelSync Pro</div>
              <div className="text-[0.62rem] uppercase tracking-[0.08em] text-gray-500">Corporate Travel</div>
            </div>
          </div>

          <h1 className="text-[1.35rem] font-bold leading-tight tracking-[-0.01em] text-gray-900">
            Sign in to your account
          </h1>
          <p className="mt-1 text-[0.79rem] text-gray-500">Welcome back - enter your credentials below</p>

          {!!errors.form && (
            <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[0.76rem] text-red-700">
              {errors.form}
            </div>
          )}

          <form onSubmit={handleSubmit} className="mt-4">
            <div className="mb-3">
              <label htmlFor="username" className="mb-[5px] block text-[0.73rem] font-semibold text-gray-700">
                Username
              </label>
              <div className={`relative flex items-center rounded-lg border-[1.5px] ${errors.username ? 'border-red-300' : 'border-gray-200'} bg-gray-50 focus-within:border-blue-600 focus-within:bg-white focus-within:shadow-[0_0_0_3px_rgba(26,86,219,0.1)]`}>
                <User size={14} className="pointer-events-none absolute left-3 text-gray-400" />
                <input
                  id="username"
                  type="text"
                  value={form.username}
                  onChange={(event) => setForm((prev) => ({ ...prev, username: event.target.value }))}
                  placeholder="Enter username"
                  autoComplete="username"
                  autoFocus
                  className="h-[41px] w-full rounded-lg border-0 bg-transparent pl-[38px] pr-3 text-[0.83rem] text-gray-900 outline-none placeholder:text-[#b0bac5]"
                />
              </div>
              {!!errors.username && <p className="mt-1 text-[0.72rem] text-red-600">{errors.username}</p>}
            </div>

            <div className="mb-3">
              <label htmlFor="password" className="mb-[5px] block text-[0.73rem] font-semibold text-gray-700">
                Password
              </label>
              <div className={`relative flex items-center rounded-lg border-[1.5px] ${errors.password ? 'border-red-300' : 'border-gray-200'} bg-gray-50 focus-within:border-blue-600 focus-within:bg-white focus-within:shadow-[0_0_0_3px_rgba(26,86,219,0.1)]`}>
                <Lock size={14} className="pointer-events-none absolute left-3 text-gray-400" />
                <input
                  id="password"
                  type={showPw ? 'text' : 'password'}
                  value={form.password}
                  onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
                  placeholder="Enter password"
                  autoComplete="current-password"
                  className="h-[41px] w-full rounded-lg border-0 bg-transparent pl-[38px] pr-10 text-[0.83rem] text-gray-900 outline-none placeholder:text-[#b0bac5]"
                />
                <button
                  type="button"
                  onClick={() => setShowPw((current) => !current)}
                  className="absolute right-[11px] p-1 text-gray-400 transition-colors hover:text-gray-600"
                  aria-label={showPw ? 'Hide password' : 'Show password'}
                >
                  {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              {!!errors.password && <p className="mt-1 text-[0.72rem] text-red-600">{errors.password}</p>}
            </div>

            <div className="mb-4 mt-1 flex items-center justify-between">
              <label className="flex cursor-pointer items-center gap-2 text-[0.75rem] text-gray-500">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(event) => setRememberMe(event.target.checked)}
                  className="h-[14px] w-[14px] rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                Remember me
              </label>
              <button type="button" className="text-[0.75rem] font-semibold text-blue-700 hover:text-blue-800">
                Forgot password?
              </button>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="h-[43px] w-full rounded-lg bg-[#111827] text-[0.875rem] font-semibold text-white transition-all hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? 'Signing in…' : 'Sign In'}
            </button>
          </form>

          <button
            type="button"
            onClick={quickDemoFill}
            className="mt-[9px] flex h-[38px] w-full items-center justify-center gap-2 rounded-lg border-[1.5px] border-gray-200 bg-gray-50 text-[0.78rem] font-semibold text-gray-700 transition-all hover:border-blue-600 hover:bg-blue-50 hover:text-blue-700"
          >
            <Play size={14} />
            Quick Demo Login
          </button>

          <div className="mt-[10px] overflow-hidden rounded-[10px] border border-gray-200">
            <div className="border-b border-gray-200 bg-gray-50 px-3 py-2 text-[0.62rem] font-bold uppercase tracking-[0.09em] text-gray-400">
              Demo credentials - click to fill
            </div>
            {demoUsers.map((user, index) => (
              <button
                key={user.username}
                type="button"
                onClick={() => fillDemo(user)}
                className={`flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-gray-100 ${index < demoUsers.length - 1 ? 'border-b border-gray-200' : ''}`}
              >
                <div className={`flex h-6 w-6 items-center justify-center rounded-md ${roleAvatarStyles[user.role]}`}>
                  {(() => {
                    const Icon = roleIcons[user.role]
                    return <Icon size={12} />
                  })()}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[0.76rem] font-semibold text-gray-900">{user.username}</div>
                  <div className="truncate text-[0.67rem] text-gray-500">{user.password}</div>
                </div>
                <span className={`rounded-full border px-2 py-[2px] text-[0.58rem] font-bold uppercase tracking-[0.04em] ${roleBadgeStyles[user.role]}`}>
                  {user.role}
                </span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
