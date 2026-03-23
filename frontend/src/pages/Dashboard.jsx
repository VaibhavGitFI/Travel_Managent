import { useEffect, useState, useCallback } from 'react'
import {
  Plane, Hotel, Receipt, TrendingUp, Clock, CheckCircle,
  MapPin, Calendar, Users, ArrowRight, Sparkles, Brain,
  AlertTriangle, Info, X, Zap, Shield, BarChart3, MessageSquare,
  ChevronRight, Globe, Wallet,
} from 'lucide-react'
import { format } from 'date-fns'
import toast from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'
import useStore from '../store/useStore'
import { getDashboardStats, getAlerts } from '../api/analytics'
import { getTrips } from '../api/trips'
import StatCard from '../components/ui/StatCard'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import { SkeletonRow } from '../components/ui/Skeleton'
import useAutoRefresh from '../hooks/useAutoRefresh'

// ── Status config ─────────────────────────────────────────────
const STATUS = {
  approved:    { color: 'green',  bg: 'bg-emerald-50',  text: 'text-emerald-700', border: 'border-emerald-200' },
  pending:     { color: 'orange', bg: 'bg-amber-50',    text: 'text-amber-700',   border: 'border-amber-200' },
  rejected:    { color: 'red',    bg: 'bg-red-50',      text: 'text-red-700',     border: 'border-red-200' },
  completed:   { color: 'gray',   bg: 'bg-gray-50',     text: 'text-gray-600',    border: 'border-gray-200' },
  booked:      { color: 'sky',    bg: 'bg-sky-50',      text: 'text-sky-700',     border: 'border-sky-200' },
  in_progress: { color: 'blue',   bg: 'bg-blue-50',     text: 'text-blue-700',    border: 'border-blue-200' },
  draft:       { color: 'gray',   bg: 'bg-gray-50',     text: 'text-gray-500',    border: 'border-gray-200' },
}

export default function Dashboard() {
  const { auth } = useStore()
  const navigate = useNavigate()
  const user = auth.user

  const [stats, setStats] = useState(null)
  const [trips, setTrips] = useState([])
  const [loading, setLoading] = useState(true)
  const [alerts, setAlerts] = useState([])
  const [dismissedAlerts, setDismissedAlerts] = useState(new Set())

  const load = useCallback(async () => {
    try {
      const [statsData, tripsData, alertsData] = await Promise.allSettled([
        getDashboardStats(),
        getTrips(),
        getAlerts(),
      ])
      if (statsData.status === 'fulfilled') setStats(statsData.value)
      if (tripsData.status === 'fulfilled') {
        const td = tripsData.value
        setTrips(Array.isArray(td) ? td : td.trips || [])
      }
      if (alertsData.status === 'fulfilled') {
        setAlerts(alertsData.value?.alerts || [])
      }
    } catch {
      toast.error('Failed to load dashboard data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])
  useAutoRefresh('requests', load)
  useAutoRefresh('analytics', load)

  const recentTrips = trips.slice(0, 5)
  const visibleAlerts = alerts.filter((a) => !dismissedAlerts.has(a.title))

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6">

      {/* ── Hero Banner ───────────────────────────────────────── */}
      <section className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-brand-dark via-brand-mid to-[#1a2744] shadow-navy">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(76,201,240,0.12),transparent_60%)]" />
        <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-brand-cyan/30 to-transparent" />

        <div className="relative px-6 pt-6 pb-5 sm:px-8 sm:pt-8">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <div className="flex h-6 w-6 items-center justify-center rounded-md bg-brand-cyan/20">
                  <Sparkles size={12} className="text-brand-cyan" />
                </div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-brand-cyan">
                  AI-Powered Dashboard
                </p>
              </div>
              <h2 className="mt-2 font-heading text-2xl font-bold tracking-tight text-white sm:text-3xl">
                Good {getTimeOfDay()}, {user?.name?.split(' ')[0] || 'Traveler'}
              </h2>
              <p className="mt-1 text-sm text-brand-muted">
                {format(new Date(), 'EEEE, MMMM d, yyyy')}
              </p>
            </div>

            <div className="flex w-full gap-2 sm:w-auto">
              <button
                onClick={() => navigate('/planner')}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/8 px-4 py-2.5 text-sm font-medium text-white backdrop-blur-sm transition-all hover:bg-white/15 sm:flex-initial"
              >
                <MapPin size={15} />
                Plan Trip
              </button>
              <button
                onClick={() => navigate('/chat')}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-brand-cyan px-4 py-2.5 text-sm font-semibold text-brand-dark transition-all hover:bg-brand-cyan/90 sm:flex-initial"
              >
                <Brain size={15} />
                AI Assistant
              </button>
            </div>
          </div>

          {/* Quick stats row */}
          <div className="mt-6 grid grid-cols-2 gap-2 xl:grid-cols-4">
            {[
              { label: 'Upcoming Trips',  value: stats?.upcoming_trips ?? '—',  icon: Calendar },
              { label: 'Active Requests', value: stats?.active_requests ?? '—', icon: Clock },
              { label: 'Team Members',    value: stats?.team_size ?? '—',       icon: Users },
              { label: 'Cities Visited',  value: stats?.cities_visited ?? '—',  icon: Globe },
            ].map((s) => (
              <div key={s.label} className="flex items-center gap-3 rounded-xl border border-white/8 bg-white/[0.05] px-4 py-3 backdrop-blur-sm">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-cyan/10">
                  <s.icon size={16} className="text-brand-cyan/80" />
                </div>
                <div>
                  <div className="text-xl font-bold leading-tight text-white">{s.value}</div>
                  <div className="text-[11px] text-brand-muted">{s.label}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Smart Alerts ──────────────────────────────────────── */}
      {visibleAlerts.length > 0 && (
        <section className="space-y-2">
          {visibleAlerts.map((alert, i) => (
            <AlertCard
              key={i}
              alert={alert}
              onDismiss={() => setDismissedAlerts((prev) => new Set([...prev, alert.title]))}
              onAction={() => alert.action?.target && navigate(alert.action.target)}
            />
          ))}
        </section>
      )}

      {/* ── KPI Cards ─────────────────────────────────────────── */}
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { icon: <Plane size={20} />,       value: loading ? '—' : (stats?.total_trips ?? trips.length ?? 0),                                          label: 'Total Trips',      accent: 'blue' },
          { icon: <Wallet size={20} />,      value: loading ? '—' : (stats?.total_expenses ? `₹${Number(stats.total_expenses).toLocaleString('en-IN')}` : '₹0'), label: 'Total Expenses',    accent: 'green' },
          { icon: <Clock size={20} />,       value: loading ? '—' : (stats?.pending_approvals ?? 0),                                                    label: 'Pending Approvals', accent: 'orange' },
          { icon: <Shield size={20} />,      value: loading ? '—' : (stats?.compliance_score ? `${stats.compliance_score}%` : '—'),                      label: 'Compliance Score',  accent: 'sky' },
        ].map((s) => (
          <StatCard
            key={s.label}
            icon={s.icon}
            value={s.value}
            label={s.label}
            accentColor={s.accent}
            className="rounded-xl border border-gray-200 bg-white shadow-card"
            loading={loading}
          />
        ))}
      </section>

      {/* ── AI Capabilities Showcase ──────────────────────────── */}
      <section className="rounded-xl border border-gray-200 bg-white shadow-card">
        <div className="flex items-center gap-3 border-b border-gray-100 px-5 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-cyan/20 to-blue-100">
            <Zap size={16} className="text-brand-cyan" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-900">AI-Powered Features</h3>
            <p className="text-xs text-gray-500">Intelligent tools to streamline your travel</p>
          </div>
        </div>
        <div className="grid grid-cols-1 divide-y divide-gray-100 sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-4">
          {[
            {
              icon: Brain,     color: 'bg-violet-50 text-violet-600',
              title: 'AI Trip Planner',
              desc: 'Get flights, hotels, weather and transport in seconds',
              to: '/planner',
            },
            {
              icon: MessageSquare, color: 'bg-blue-50 text-blue-600',
              title: 'Travel Chat Assistant',
              desc: 'Ask anything about travel, policies, or bookings',
              to: '/chat',
            },
            {
              icon: Receipt,   color: 'bg-emerald-50 text-emerald-600',
              title: 'Smart Expense OCR',
              desc: 'Scan receipts with AI-powered amount extraction',
              to: '/expenses',
            },
            {
              icon: BarChart3,  color: 'bg-amber-50 text-amber-600',
              title: 'Spend Analytics',
              desc: 'AI compliance scoring and spend insights',
              to: '/analytics',
            },
          ].map((f) => (
            <button
              key={f.title}
              onClick={() => navigate(f.to)}
              className="group flex items-start gap-3 px-5 py-4 text-left transition-colors hover:bg-gray-50"
            >
              <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${f.color}`}>
                <f.icon size={18} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-gray-900 group-hover:text-brand-dark">{f.title}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-gray-500">{f.desc}</p>
              </div>
              <ChevronRight size={16} className="mt-0.5 shrink-0 text-gray-300 transition-transform group-hover:translate-x-0.5 group-hover:text-brand-cyan" />
            </button>
          ))}
        </div>
      </section>

      {/* ── Main Content Grid ─────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">

        {/* Recent Trips */}
        <section className="lg:col-span-2 rounded-xl border border-gray-200 bg-white shadow-card">
          <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">Recent Trips</h3>
              <p className="mt-0.5 text-xs text-gray-500">Your latest travel requests</p>
            </div>
            <button
              onClick={() => navigate('/requests')}
              className="flex items-center gap-1 text-xs font-medium text-gray-500 transition-colors hover:text-brand-cyan"
            >
              View all <ArrowRight size={13} />
            </button>
          </div>

          {loading ? (
            <div className="divide-y divide-gray-100">
              {Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}
            </div>
          ) : recentTrips.length === 0 ? (
            <div className="px-6 py-14 text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-50 to-cyan-50">
                <Plane size={24} className="text-brand-cyan" />
              </div>
              <p className="font-semibold text-gray-800">No trips yet</p>
              <p className="mt-1 text-sm text-gray-500">Plan your first AI-powered trip to get started</p>
              <button
                onClick={() => navigate('/planner')}
                className="mt-4 inline-flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                <Sparkles size={14} className="text-brand-cyan" />
                Plan a Trip
              </button>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {recentTrips.map((trip, i) => <TripRow key={trip.id || i} trip={trip} />)}
            </div>
          )}
        </section>

        {/* Right Column */}
        <div className="space-y-4">
          {/* Quick Actions */}
          <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-card">
            <h3 className="mb-3 text-sm font-semibold text-gray-900">Quick Actions</h3>
            <div className="space-y-1.5">
              {[
                { label: 'New Trip',           icon: Plane,   to: '/planner',       color: 'bg-blue-50 text-blue-600' },
                { label: 'Submit Expense',     icon: Receipt, to: '/expenses',      color: 'bg-emerald-50 text-emerald-600' },
                { label: 'Book Accommodation', icon: Hotel,   to: '/accommodation', color: 'bg-violet-50 text-violet-600' },
                { label: 'Schedule Meeting',   icon: Users,   to: '/meetings',      color: 'bg-amber-50 text-amber-600' },
              ].map((a) => (
                <button
                  key={a.label}
                  onClick={() => navigate(a.to)}
                  className="group flex w-full items-center gap-3 rounded-lg border border-gray-100 bg-white p-2.5 transition-all hover:border-gray-200 hover:shadow-sm"
                >
                  <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${a.color}`}>
                    <a.icon size={16} />
                  </div>
                  <span className="text-sm font-medium text-gray-700 group-hover:text-gray-900">{a.label}</span>
                  <ArrowRight size={14} className="ml-auto text-gray-300 transition-all group-hover:translate-x-0.5 group-hover:text-brand-cyan" />
                </button>
              ))}
            </div>
          </section>

          {/* AI Assistant CTA */}
          <section className="relative overflow-hidden rounded-xl border border-gray-200 bg-gradient-to-br from-brand-dark to-brand-mid p-5 shadow-card">
            <div className="absolute top-0 right-0 h-24 w-24 rounded-full bg-brand-cyan/10 blur-2xl" />
            <div className="relative">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-cyan/15">
                <Brain size={20} className="text-brand-cyan" />
              </div>
              <h3 className="mt-3 text-sm font-semibold text-white">AI Travel Assistant</h3>
              <p className="mt-1 text-xs leading-relaxed text-brand-muted">
                Ask about travel policies, get hotel recommendations, or plan your next trip with AI.
              </p>
              <button
                onClick={() => navigate('/chat')}
                className="mt-4 flex items-center gap-2 rounded-lg bg-brand-cyan px-4 py-2 text-sm font-semibold text-brand-dark transition-all hover:bg-brand-cyan/90"
              >
                Start Conversation
                <ArrowRight size={14} />
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

// ── Trip Row ──────────────────────────────────────────────────
function TripRow({ trip }) {
  const s = STATUS[trip.status?.toLowerCase()] || STATUS.draft
  const statusLabel = (trip.status || 'draft').replace(/_/g, ' ')

  return (
    <div className="flex items-center gap-3 px-5 py-3.5 transition-colors hover:bg-gray-50/50 sm:gap-4">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-50 border border-blue-100">
        <Plane size={15} className="text-blue-600" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="truncate text-sm font-medium text-gray-900">
          {trip.from_city || trip.source || '—'} → {trip.to_city || trip.destination}
        </p>
        <p className="mt-0.5 text-xs text-gray-500">
          {trip.travel_date || trip.departure_date || 'Date TBD'}
          {trip.return_date && ` – ${trip.return_date}`}
          {trip.estimated_budget ? ` • ₹${Number(trip.estimated_budget).toLocaleString('en-IN')}` : ''}
        </p>
      </div>
      <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold capitalize ${s.bg} ${s.text} ${s.border}`}>
        <span className={`h-1.5 w-1.5 rounded-full bg-current`} />
        {statusLabel}
      </span>
    </div>
  )
}

// ── Alert Card ────────────────────────────────────────────────
function AlertCard({ alert, onDismiss, onAction }) {
  const styles = {
    info:     { card: 'border-blue-200 bg-blue-50/80',  icon: 'text-blue-500',  text: 'text-blue-900' },
    warning:  { card: 'border-amber-200 bg-amber-50/80', icon: 'text-amber-500', text: 'text-amber-900' },
    critical: { card: 'border-red-200 bg-red-50/80',    icon: 'text-red-500',   text: 'text-red-900' },
  }
  const st = styles[alert.severity] || styles.info
  const SeverityIcon = alert.severity === 'info' ? Info : AlertTriangle

  return (
    <div className={`flex items-start gap-3 rounded-xl border px-4 py-3 ${st.card}`}>
      <SeverityIcon size={16} className={`mt-0.5 shrink-0 ${st.icon}`} />
      <div className={`min-w-0 flex-1 ${st.text}`}>
        <p className="text-sm font-semibold leading-tight">{alert.title}</p>
        <p className="mt-0.5 text-xs opacity-75">{alert.message}</p>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {alert.action?.target && (
          <button onClick={onAction} className="rounded-lg px-2.5 py-1 text-xs font-medium transition-colors hover:bg-black/5">
            View
          </button>
        )}
        <button onClick={onDismiss} className="rounded-lg p-1 transition-colors hover:bg-black/5" aria-label="Dismiss">
          <X size={14} />
        </button>
      </div>
    </div>
  )
}

function getTimeOfDay() {
  const h = new Date().getHours()
  if (h < 12) return 'morning'
  if (h < 17) return 'afternoon'
  return 'evening'
}
