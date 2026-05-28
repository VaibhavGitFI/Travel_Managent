import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Eye, EyeOff, Layers, Lock, Mail, ArrowLeft, Building, User } from 'lucide-react'
import toast from 'react-hot-toast'
import { login, register, verifyEmail, forgotPassword, resetPassword } from '../api/auth'
import { getMyOrganization } from '../api/organizations'
import useStore from '../store/useStore'


// Input component — defined outside Login to prevent re-creation on every render
function FormInput({ id, label, icon: Icon, type = 'text', value, onChange, placeholder, error, autoComplete, autoFocus, showToggle, showPwState, setShowPwState }) {
  return (
    <div className="mb-3">
      <label htmlFor={id} className="mb-[5px] block text-[0.73rem] font-semibold text-gray-700">
        {label || id.replace(/([A-Z])/g, ' $1').replace(/^./, s => s.toUpperCase())}
      </label>
      <div className={`relative flex items-center rounded-lg border-[1.5px] ${error ? 'border-red-300' : 'border-gray-200'} bg-gray-50 focus-within:border-blue-600 focus-within:bg-white focus-within:shadow-[0_0_0_3px_rgba(26,86,219,0.1)]`}>
        <Icon size={14} className="pointer-events-none absolute left-3 text-gray-400" />
        <input
          id={id}
          type={showToggle ? (showPwState ? 'text' : 'password') : type}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
          className="h-[41px] w-full rounded-lg border-0 bg-transparent pl-[38px] pr-10 text-[0.83rem] text-gray-900 outline-none placeholder:text-gray-400"
        />
        {showToggle && (
          <button type="button" onClick={() => setShowPwState(v => !v)} className="absolute right-[11px] p-1 text-gray-400 transition-colors hover:text-gray-600">
            {showPwState ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        )}
      </div>
      {error && <p className="mt-1 text-[0.72rem] text-red-600">{error}</p>}
    </div>
  )
}

export default function Login() {
  const navigate = useNavigate()
  const { setUser } = useStore()

  // View: 'login' | 'register' | 'verify' | 'forgot' | 'reset'
  const [view, setView] = useState('login')
  const [verifyCode, setVerifyCode] = useState('')

  // Login form
  const [form, setForm] = useState({ username: '', password: '' })
  const [showPw, setShowPw] = useState(false)
  const [rememberMe, setRememberMe] = useState(false)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState({})

  // Register form
  const [regForm, setRegForm] = useState({ fullName: '', email: '', password: '', department: '' })
  const [regShowPw, setRegShowPw] = useState(false)

  // Forgot password
  const [forgotEmail, setForgotEmail] = useState('')

  // Reset password
  const [resetForm, setResetForm] = useState({ code: '', newPassword: '' })

  const handleLogin = async (event) => {
    event.preventDefault()
    const nextErrors = {}
    if (!form.username.trim()) nextErrors.username = 'Email or username is required'
    if (!form.password) nextErrors.password = 'Password is required'
    if (Object.keys(nextErrors).length) { setErrors(nextErrors); return }

    setErrors({})
    setLoading(true)
    try {
      const data = await login(form.username.trim(), form.password)
      if (data.needs_verification) {
        toast('Please verify your email first', { icon: '📧' })
        setView('verify')
        return
      }
      const u = data.user || { id: 0, username: form.username, name: form.username, role: 'employee' }
      if (!u.name && u.full_name) u.name = u.full_name
      setUser(u)
      // Load org context after login
      try {
        const orgData = await getMyOrganization()
        useStore.getState().setOrg(orgData.organization || null)
      } catch { /* no org yet — that's fine */ }
      toast.success(`Welcome back, ${data.user?.name || form.username}!`)
      navigate('/dashboard', { replace: true })
    } catch (error) {
      const resp = error.response?.data
      if (resp?.needs_verification) {
        toast('Please verify your email first', { icon: '📧' })
        setView('verify')
        return
      }
      const message = resp?.error || 'Invalid credentials'
      toast.error(message)
      setErrors({ form: message })
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async (event) => {
    event.preventDefault()
    const nextErrors = {}
    if (!regForm.fullName.trim()) nextErrors.fullName = 'Full name is required'
    if (!regForm.email.trim()) nextErrors.email = 'Email is required'
    if (!regForm.email.includes('@')) nextErrors.email = 'Invalid email'
    if (!regForm.password) nextErrors.password = 'Password is required'
    else if (regForm.password.length < 8) nextErrors.password = 'Min 8 characters'
    else if (!/[A-Z]/.test(regForm.password)) nextErrors.password = 'Needs an uppercase letter'
    else if (!/[a-z]/.test(regForm.password)) nextErrors.password = 'Needs a lowercase letter'
    else if (!/\d/.test(regForm.password)) nextErrors.password = 'Needs a number'
    if (Object.keys(nextErrors).length) { setErrors(nextErrors); return }

    setErrors({})
    setLoading(true)
    try {
      const data = await register(regForm.fullName.trim(), regForm.email.trim(), regForm.password, regForm.department.trim())
      if (data.success && data.needs_verification) {
        toast.success('Verification code sent to your email!')
        setView('verify')
      } else if (data.success && data.user) {
        const u = data.user
        if (!u.name && u.full_name) u.name = u.full_name
        setUser(u)
        toast.success(`Welcome, ${u.name}!`)
        navigate('/dashboard', { replace: true })
      } else {
        toast.error(data.error || 'Registration failed')
        setErrors({ form: data.error })
      }
    } catch (error) {
      const message = error.response?.data?.error || 'Registration failed'
      toast.error(message)
      setErrors({ form: message })
    } finally {
      setLoading(false)
    }
  }

  const handleForgotPassword = async (event) => {
    event.preventDefault()
    if (!forgotEmail.trim()) { setErrors({ email: 'Email is required' }); return }

    setErrors({})
    setLoading(true)
    try {
      await forgotPassword(forgotEmail.trim())
      toast.success('Reset code sent to your email!')
      setView('reset')
    } catch (error) {
      toast.error(error.response?.data?.error || 'Failed to send reset code')
    } finally {
      setLoading(false)
    }
  }

  const handleResetPassword = async (event) => {
    event.preventDefault()
    const nextErrors = {}
    if (!resetForm.code.trim()) nextErrors.code = 'Reset code is required'
    if (!resetForm.newPassword) nextErrors.newPassword = 'New password is required'
    if (resetForm.newPassword.length < 6) nextErrors.newPassword = 'Min 6 characters'
    if (Object.keys(nextErrors).length) { setErrors(nextErrors); return }

    setErrors({})
    setLoading(true)
    try {
      const data = await resetPassword(resetForm.code.trim(), resetForm.newPassword)
      if (data.success) {
        toast.success('Password reset! You can now sign in.')
        setView('login')
        setResetForm({ code: '', newPassword: '' })
      } else {
        toast.error(data.error || 'Reset failed')
        setErrors({ form: data.error })
      }
    } catch (error) {
      const message = error.response?.data?.error || 'Reset failed'
      toast.error(message)
      setErrors({ form: message })
    } finally {
      setLoading(false)
    }
  }

  const switchView = (v) => { setView(v); setErrors({}) }

  return (
    <div className="flex w-full min-h-screen items-start justify-center overflow-y-auto bg-gradient-to-br from-brand-dark via-navy-800 to-brand-dark p-0 sm:p-5 md:items-center">
      <div className="flex h-auto w-[min(980px,97vw)] overflow-hidden rounded-none border border-white/10 bg-transparent shadow-[0_40px_90px_rgba(0,0,0,0.4)] sm:rounded-2xl md:h-[min(660px,94vh)]">
        {/* Left artwork panel */}
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
              Welcome Back,<br />Adventurer.
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
                <span key={item} className="rounded-full border border-white/20 bg-white/15 px-2.5 py-1 text-[0.68rem] font-semibold tracking-[0.03em] text-white">
                  {item}
                </span>
              ))}
            </div>
          </div>
        </section>

        {/* Right form panel */}
        <section className="w-full overflow-y-auto bg-white p-6 sm:p-7 md:w-[400px] md:min-w-[400px] md:p-[28px_36px]">
          {/* Logo */}
          <div className="mb-4 flex items-center gap-[10px]">
            <div className="flex h-10 w-10 items-center justify-center rounded-[10px] bg-[linear-gradient(135deg,#1a56db,#0891b2)] text-white shadow-md">
              <Layers size={18} />
            </div>
            <div>
              <div className="text-[0.95rem] font-bold leading-[1.2] text-gray-900">TravelSync Pro</div>
              <div className="text-[0.62rem] uppercase tracking-[0.08em] text-gray-500">Corporate Travel</div>
            </div>
          </div>

          {/* ── LOGIN VIEW ── */}
          {view === 'login' && (
            <>
              <h1 className="text-[1.25rem] font-bold leading-tight text-gray-900">Sign in to your account</h1>
              <p className="mt-1 text-[0.79rem] text-gray-500">Enter your email or username below</p>

              {errors.form && (
                <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[0.76rem] text-red-700">{errors.form}</div>
              )}

              <form onSubmit={handleLogin} className="mt-4">
                <FormInput id="username" label="Email or Username" icon={Mail} value={form.username}
                  onChange={e => setForm(p => ({ ...p, username: e.target.value }))}
                  placeholder="Email or username" error={errors.username} autoComplete="username" autoFocus />

                <FormInput id="password" icon={Lock} value={form.password}
                  onChange={e => setForm(p => ({ ...p, password: e.target.value }))}
                  placeholder="Enter password" error={errors.password} autoComplete="current-password"
                  showToggle showPwState={showPw} setShowPwState={setShowPw} />

                <div className="mb-4 mt-1 flex items-center justify-between">
                  <label className="flex cursor-pointer items-center gap-2 text-[0.75rem] text-gray-500">
                    <input type="checkbox" checked={rememberMe} onChange={e => setRememberMe(e.target.checked)}
                      className="h-[14px] w-[14px] rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                    Remember me
                  </label>
                  <button type="button" onClick={() => switchView('forgot')}
                    className="text-[0.75rem] font-semibold text-blue-700 hover:text-blue-800">
                    Forgot password?
                  </button>
                </div>

                <button type="submit" disabled={loading}
                  className="h-[43px] w-full rounded-lg bg-brand-dark text-[0.875rem] font-semibold text-white transition-all hover:bg-brand-mid disabled:cursor-not-allowed disabled:opacity-60">
                  {loading ? 'Signing in...' : 'Sign In'}
                </button>
              </form>

              <div className="mt-3 text-center">
                <span className="text-[0.79rem] text-gray-500">Don't have an account? </span>
                <button type="button" onClick={() => switchView('register')}
                  className="text-[0.79rem] font-semibold text-blue-700 hover:text-blue-800">
                  Create account
                </button>
              </div>

            </>
          )}

          {/* ── REGISTER VIEW ── */}
          {view === 'register' && (
            <>
              <button type="button" onClick={() => switchView('login')}
                className="mb-3 flex items-center gap-1 text-[0.79rem] text-gray-500 hover:text-gray-700">
                <ArrowLeft size={14} /> Back to sign in
              </button>

              <h1 className="text-[1.25rem] font-bold leading-tight text-gray-900">Create your account</h1>
              <p className="mt-1 text-[0.79rem] text-gray-500">Join TravelSync Pro to manage your business travel</p>

              {errors.form && (
                <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[0.76rem] text-red-700">{errors.form}</div>
              )}

              <form onSubmit={handleRegister} className="mt-4">
                <FormInput id="fullName" label="Full Name" icon={User} value={regForm.fullName}
                  onChange={e => setRegForm(p => ({ ...p, fullName: e.target.value }))}
                  placeholder="John Doe" error={errors.fullName} autoComplete="name" autoFocus />

                <FormInput id="regEmail" label="Email" icon={Mail} type="email" value={regForm.email}
                  onChange={e => setRegForm(p => ({ ...p, email: e.target.value }))}
                  placeholder="john@company.com" error={errors.email} autoComplete="email" />

                <FormInput id="department" label="Department" icon={Building} value={regForm.department}
                  onChange={e => setRegForm(p => ({ ...p, department: e.target.value }))}
                  placeholder="e.g. Sales, Engineering (optional)" error={errors.department} />

                <FormInput id="regPassword" label="Password" icon={Lock} value={regForm.password}
                  onChange={e => setRegForm(p => ({ ...p, password: e.target.value }))}
                  placeholder="Min 6 characters" error={errors.password} autoComplete="new-password"
                  showToggle showPwState={regShowPw} setShowPwState={setRegShowPw} />

                <button type="submit" disabled={loading}
                  className="mt-1 h-[43px] w-full rounded-lg bg-brand-dark text-[0.875rem] font-semibold text-white transition-all hover:bg-brand-mid disabled:cursor-not-allowed disabled:opacity-60">
                  {loading ? 'Creating account...' : 'Create Account'}
                </button>
              </form>

              <div className="mt-3 text-center">
                <span className="text-[0.79rem] text-gray-500">Already have an account? </span>
                <button type="button" onClick={() => switchView('login')}
                  className="text-[0.79rem] font-semibold text-blue-700 hover:text-blue-800">
                  Sign in
                </button>
              </div>
            </>
          )}

          {/* ── FORGOT PASSWORD VIEW ── */}
          {view === 'forgot' && (
            <>
              <button type="button" onClick={() => switchView('login')}
                className="mb-3 flex items-center gap-1 text-[0.79rem] text-gray-500 hover:text-gray-700">
                <ArrowLeft size={14} /> Back to sign in
              </button>

              <h1 className="text-[1.25rem] font-bold leading-tight text-gray-900">Reset your password</h1>
              <p className="mt-1 text-[0.79rem] text-gray-500">Enter your email and we'll send a reset code</p>

              <form onSubmit={handleForgotPassword} className="mt-4">
                <FormInput id="email" icon={Mail} type="email" value={forgotEmail}
                  onChange={e => setForgotEmail(e.target.value)}
                  placeholder="Enter your email" error={errors.email} autoComplete="email" autoFocus />

                <button type="submit" disabled={loading}
                  className="mt-1 h-[43px] w-full rounded-lg bg-brand-dark text-[0.875rem] font-semibold text-white transition-all hover:bg-brand-mid disabled:cursor-not-allowed disabled:opacity-60">
                  {loading ? 'Sending...' : 'Send Reset Code'}
                </button>
              </form>
            </>
          )}

          {/* ── VERIFY EMAIL VIEW ── */}
          {view === 'verify' && (
            <>
              <button type="button" onClick={() => switchView('login')}
                className="mb-3 flex items-center gap-1 text-[0.79rem] text-gray-500 hover:text-gray-700">
                <ArrowLeft size={14} /> Back to sign in
              </button>

              <h1 className="text-[1.25rem] font-bold leading-tight text-gray-900">Verify your email</h1>
              <p className="mt-1 text-[0.79rem] text-gray-500">
                We sent a 6-digit code to <strong>{regForm.email || 'your email'}</strong>. Enter it below.
              </p>

              {errors.form && (
                <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[0.76rem] text-red-700">{errors.form}</div>
              )}

              <form onSubmit={async (e) => {
                e.preventDefault()
                if (!verifyCode.trim()) { setErrors({ code: 'Enter the 6-digit code' }); return }
                setErrors({})
                setLoading(true)
                try {
                  const data = await verifyEmail(verifyCode.trim())
                  if (data.success && data.user) {
                    const u = data.user
                    if (!u.name && u.full_name) u.name = u.full_name
                    setUser(u)
                    toast.success(`Email verified! Welcome, ${u.name}!`)
                    navigate('/dashboard', { replace: true })
                  } else {
                    toast.error(data.error || 'Verification failed')
                    setErrors({ form: data.error })
                  }
                } catch (error) {
                  const message = error.response?.data?.error || 'Invalid code'
                  toast.error(message)
                  setErrors({ form: message })
                } finally {
                  setLoading(false)
                }
              }} className="mt-4">
                <FormInput id="verifyCode" label="Verification Code" icon={Mail} value={verifyCode}
                  onChange={e => setVerifyCode(e.target.value)}
                  placeholder="Enter 6-digit code" error={errors.code} autoFocus />

                <button type="submit" disabled={loading}
                  className="mt-1 h-[43px] w-full rounded-lg bg-brand-dark text-[0.875rem] font-semibold text-white transition-all hover:bg-brand-mid disabled:cursor-not-allowed disabled:opacity-60">
                  {loading ? 'Verifying...' : 'Verify & Sign In'}
                </button>
              </form>

              <p className="mt-3 text-center text-[0.75rem] text-gray-400">
                Didn't receive the code? Check spam or <button type="button" onClick={() => switchView('register')} className="text-blue-600 hover:text-blue-700 font-medium">try again</button>
              </p>
            </>
          )}

          {/* ── RESET PASSWORD VIEW ── */}
          {view === 'reset' && (
            <>
              <button type="button" onClick={() => switchView('forgot')}
                className="mb-3 flex items-center gap-1 text-[0.79rem] text-gray-500 hover:text-gray-700">
                <ArrowLeft size={14} /> Back
              </button>

              <h1 className="text-[1.25rem] font-bold leading-tight text-gray-900">Enter reset code</h1>
              <p className="mt-1 text-[0.79rem] text-gray-500">Check your email for the 6-digit code</p>

              {errors.form && (
                <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[0.76rem] text-red-700">{errors.form}</div>
              )}

              <form onSubmit={handleResetPassword} className="mt-4">
                <FormInput id="code" icon={Mail} value={resetForm.code}
                  onChange={e => setResetForm(p => ({ ...p, code: e.target.value }))}
                  placeholder="6-digit code" error={errors.code} autoFocus />

                <FormInput id="newPassword" icon={Lock} value={resetForm.newPassword}
                  onChange={e => setResetForm(p => ({ ...p, newPassword: e.target.value }))}
                  placeholder="New password (min 6 chars)" error={errors.newPassword} autoComplete="new-password"
                  showToggle showPwState={showPw} setShowPwState={setShowPw} />

                <button type="submit" disabled={loading}
                  className="mt-1 h-[43px] w-full rounded-lg bg-brand-dark text-[0.875rem] font-semibold text-white transition-all hover:bg-brand-mid disabled:cursor-not-allowed disabled:opacity-60">
                  {loading ? 'Resetting...' : 'Reset Password'}
                </button>
              </form>
            </>
          )}
        </section>
      </div>
    </div>
  )
}
