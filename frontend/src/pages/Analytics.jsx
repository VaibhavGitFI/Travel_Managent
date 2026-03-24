import { useState, useEffect, useCallback } from 'react'
import {
  TrendingUp, IndianRupee, MapPin, Users, Wallet,
  CheckCircle, XCircle, BarChart3, Activity, Calendar, Brain, Shield,
  Plane, ArrowUpRight, ArrowDownRight,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { getDashboardStats, getSpendAnalysis, getComplianceScorecard } from '../api/analytics'
import useAutoRefresh from '../hooks/useAutoRefresh'
import StatCard from '../components/ui/StatCard'
import Spinner from '../components/ui/Spinner'
import { Skeleton } from '../components/ui/Skeleton'
import { cn } from '../lib/cn'

const fmt = (v) => `₹${Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`

const CAT_COLORS = [
  { bar: 'bg-blue-500',    bg: 'bg-blue-50',    text: 'text-blue-700',    border: 'border-blue-100' },
  { bar: 'bg-violet-500',  bg: 'bg-violet-50',  text: 'text-violet-700',  border: 'border-violet-100' },
  { bar: 'bg-emerald-500', bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-100' },
  { bar: 'bg-amber-500',   bg: 'bg-amber-50',   text: 'text-amber-700',   border: 'border-amber-100' },
  { bar: 'bg-rose-500',    bg: 'bg-rose-50',    text: 'text-rose-700',    border: 'border-rose-100' },
  { bar: 'bg-sky-500',     bg: 'bg-sky-50',     text: 'text-sky-700',     border: 'border-sky-100' },
]

export default function Analytics() {
  const [stats, setStats] = useState(null)
  const [spend, setSpend] = useState(null)
  const [compliance, setCompliance] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const [s, sp, c] = await Promise.allSettled([getDashboardStats(), getSpendAnalysis(), getComplianceScorecard()])
      if (s.status === 'fulfilled') setStats(s.value)
      if (sp.status === 'fulfilled') setSpend(sp.value)
      if (c.status === 'fulfilled') setCompliance(c.value)
    } catch { toast.error('Failed to load analytics') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])
  useAutoRefresh('analytics', load)

  if (loading) return <LoadingSkeleton />

  const categories = spend?.by_category || []
  const topCities = spend?.top_cities || []
  const monthly = spend?.monthly_trend || []
  const maxCat = Math.max(...categories.map(c => c.amount || c.total || 0), 1)
  const totalSpend = categories.reduce((s, c) => s + (c.amount || c.total || 0), 0)

  return (
    <div className="mx-auto w-full max-w-7xl space-y-5">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-purple-600">
              <BarChart3 size={14} className="text-white" />
            </div>
            <h1 className="font-heading text-xl font-bold text-gray-900">Analytics</h1>
            <span className="rounded-full bg-violet-50 border border-violet-200 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-violet-600">
              AI Insights
            </span>
          </div>
          <p className="mt-1 text-sm text-gray-500">Travel spend insights, compliance scoring, and trend analysis</p>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-gray-50 border border-gray-200 px-3 py-1.5">
          <Calendar size={13} className="text-gray-400" />
          <span className="text-xs font-medium text-gray-500">Last 12 months</span>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        <StatCard icon={<Wallet size={20} />} value={fmt(stats?.total_expenses)} label="Total Spend" accentColor="blue" className="rounded-xl border border-gray-200 bg-white shadow-card" />
        <StatCard icon={<Plane size={20} />} value={stats?.total_trips ?? 0} label="Total Trips" accentColor="sky" className="rounded-xl border border-gray-200 bg-white shadow-card" />
        <StatCard icon={<Users size={20} />} value={stats?.team_size ?? 0} label="Active Travelers" accentColor="green" className="rounded-xl border border-gray-200 bg-white shadow-card" />
        <StatCard icon={<Shield size={20} />} value={`${stats?.compliance_score ?? 0}%`} label="Compliance Score" accentColor="orange" className="rounded-xl border border-gray-200 bg-white shadow-card" />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Spend by Category */}
        <div className="lg:col-span-2 rounded-xl border border-gray-200 bg-white shadow-card overflow-hidden">
          <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
            <div className="flex items-center gap-2">
              <BarChart3 size={15} className="text-violet-500" />
              <h3 className="text-sm font-semibold text-gray-900">Spend by Category</h3>
            </div>
            {totalSpend > 0 && <span className="text-xs text-gray-400">Total: {fmt(totalSpend)}</span>}
          </div>
          <div className="p-5">
            {categories.length > 0 ? (
              <div className="space-y-4">
                {categories.map((cat, i) => {
                  const val = cat.amount || cat.total || 0
                  const pct = Math.round((val / maxCat) * 100)
                  const c = CAT_COLORS[i % CAT_COLORS.length]
                  const share = totalSpend > 0 ? Math.round((val / totalSpend) * 100) : 0
                  return (
                    <div key={i}>
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-2">
                          <span className={cn('h-2.5 w-2.5 rounded-full', c.bar)} />
                          <span className="text-sm font-medium text-gray-700 capitalize">{cat.category || cat.name}</span>
                          <span className="text-[10px] text-gray-400">{share}%</span>
                        </div>
                        <span className="text-sm font-bold text-gray-900">{fmt(val)}</span>
                      </div>
                      <div className="h-2.5 rounded-full bg-gray-100 overflow-hidden">
                        <div className={cn('h-full rounded-full transition-all duration-700', c.bar)} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : (
              <p className="text-sm text-gray-400 text-center py-6">No spend data available yet</p>
            )}
          </div>
        </div>

        {/* Top Destinations */}
        <div className="rounded-xl border border-gray-200 bg-white shadow-card overflow-hidden">
          <div className="flex items-center gap-2 border-b border-gray-100 px-5 py-4">
            <MapPin size={15} className="text-sky-500" />
            <h3 className="text-sm font-semibold text-gray-900">Top Destinations</h3>
          </div>
          <div className="p-5">
            {topCities.length > 0 ? (
              <div className="space-y-3">
                {topCities.slice(0, 6).map((city, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <span className={cn(
                        'flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold',
                        i === 0 ? 'bg-amber-100 text-amber-700' : i === 1 ? 'bg-gray-100 text-gray-600' : i === 2 ? 'bg-orange-50 text-orange-600' : 'bg-gray-50 text-gray-500'
                      )}>
                        {i + 1}
                      </span>
                      <span className="text-sm text-gray-700">{city.city || city.name}</span>
                    </div>
                    <span className="rounded-full bg-sky-50 border border-sky-200 px-2 py-0.5 text-[10px] font-bold text-sky-700">
                      {city.trips || city.count} trips
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400 text-center py-6">No destination data yet</p>
            )}
          </div>
        </div>
      </div>

      {/* Monthly Trend */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-card overflow-hidden">
        <div className="flex items-center gap-2 border-b border-gray-100 px-5 py-4">
          <TrendingUp size={15} className="text-emerald-500" />
          <h3 className="text-sm font-semibold text-gray-900">Monthly Spend Trend</h3>
        </div>
        <div className="p-5">
          {monthly.length > 0 ? <MonthlyChart data={monthly} /> : (
            <p className="text-sm text-gray-400 text-center py-6">No monthly data yet</p>
          )}
        </div>
      </div>

      {/* Compliance Scorecard */}
      {compliance && (
        <div className="rounded-xl border border-gray-200 bg-white shadow-card overflow-hidden">
          <div className="flex items-center gap-2 border-b border-gray-100 px-5 py-4">
            <Brain size={15} className="text-amber-500" />
            <h3 className="text-sm font-semibold text-gray-900">AI Policy Compliance</h3>
          </div>
          <div className="p-5">
            <ComplianceCard compliance={compliance} />
          </div>
        </div>
      )}
    </div>
  )
}

// ── KPI Card ────────────────────────────────────────────
function KpiCard({ icon: Icon, label, value, color, iconColor }) {
  return (
    <div className={cn('rounded-xl border p-4', color)}>
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} className={iconColor} />
        <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">{label}</span>
      </div>
      <p className="text-xl font-bold text-gray-900">{value}</p>
    </div>
  )
}

// ── Monthly Bar Chart ───────────────────────────────────
function MonthlyChart({ data }) {
  const max = Math.max(...data.map(d => d.amount || d.total || 0), 1)
  const [hovered, setHovered] = useState(null)

  return (
    <div className="space-y-2">
      <div className="flex items-end gap-1.5 h-36">
        {data.slice(0, 12).map((d, i) => {
          const val = d.amount || d.total || 0
          const h = Math.max((val / max) * 100, 2)
          const isHovered = hovered === i
          return (
            <div key={i} className="flex-1 flex flex-col items-center gap-1"
              onMouseEnter={() => setHovered(i)} onMouseLeave={() => setHovered(null)}>
              {isHovered && (
                <div className="text-[10px] font-bold text-gray-900 whitespace-nowrap">{fmt(val)}</div>
              )}
              <div className={cn(
                'w-full rounded-t-md transition-all duration-200 cursor-pointer',
                isHovered ? 'bg-violet-500' : 'bg-violet-400/70'
              )} style={{ height: `${h}%` }} />
            </div>
          )
        })}
      </div>
      <div className="flex gap-1.5">
        {data.slice(0, 12).map((d, i) => (
          <div key={i} className="flex-1 text-center">
            <span className={cn('text-[9px] font-medium', hovered === i ? 'text-gray-900' : 'text-gray-400')}>
              {(d.month || d.label || '').slice(0, 3)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Compliance Scorecard ────────────────────────────────
function ComplianceCard({ compliance }) {
  const score = compliance.score ?? compliance.overall_score ?? 0
  const checks = compliance.checks || compliance.items || []
  const scoreColor = score >= 80 ? 'text-emerald-600' : score >= 60 ? 'text-amber-600' : 'text-red-600'
  const ringColor = score >= 80 ? 'stroke-emerald-500' : score >= 60 ? 'stroke-amber-500' : 'stroke-red-500'

  // SVG circular progress
  const size = 120, sw = 8, r = (size - sw) / 2, c = 2 * Math.PI * r
  const offset = c - (score / 100) * c

  return (
    <div className="flex flex-col gap-6 md:flex-row md:items-start">
      {/* Score ring */}
      <div className="flex flex-col items-center gap-2 shrink-0 mx-auto md:mx-0">
        <div className="relative" style={{ width: size, height: size }}>
          <svg viewBox={`0 0 ${size} ${size}`} className="w-full h-full -rotate-90">
            <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#f1f5f9" strokeWidth={sw} />
            <circle cx={size/2} cy={size/2} r={r} fill="none" className={ringColor} strokeWidth={sw}
              strokeLinecap="round" strokeDasharray={c} strokeDashoffset={offset}
              style={{ transition: 'stroke-dashoffset 1s ease' }} />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={cn('text-3xl font-bold', scoreColor)}>{score}</span>
            <span className="text-[10px] text-gray-400">/100</span>
          </div>
        </div>
        <span className={cn('text-xs font-semibold', scoreColor)}>
          {score >= 80 ? 'Excellent' : score >= 60 ? 'Needs Improvement' : 'Critical'}
        </span>
      </div>

      {/* Check items */}
      {checks.length > 0 && (
        <div className="flex-1 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {checks.map((c, i) => (
            <div key={i} className={cn(
              'flex items-center gap-2.5 rounded-lg border p-3',
              c.passed ? 'border-emerald-100 bg-emerald-50/50' : 'border-red-100 bg-red-50/50'
            )}>
              {c.passed
                ? <CheckCircle size={14} className="text-emerald-500 shrink-0" />
                : <XCircle size={14} className="text-red-500 shrink-0" />}
              <span className="text-sm text-gray-700 flex-1">{c.label || c.name}</span>
              <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-bold',
                c.passed ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700')}>
                {c.passed ? 'Pass' : 'Fail'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Loading Skeleton ────────────────────────────────────
function LoadingSkeleton() {
  return (
    <div className="mx-auto w-full max-w-7xl space-y-5">
      <Skeleton className="h-6 w-40" />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-xl border border-gray-100 bg-white p-4 space-y-2">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-7 w-24" />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 rounded-xl border border-gray-100 bg-white p-5 space-y-4">
          <Skeleton className="h-5 w-36" />
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="space-y-1.5">
              <div className="flex justify-between"><Skeleton className="h-3 w-20" /><Skeleton className="h-3 w-16" /></div>
              <Skeleton className="h-2.5 w-full rounded-full" />
            </div>
          ))}
        </div>
        <div className="rounded-xl border border-gray-100 bg-white p-5 space-y-3">
          <Skeleton className="h-5 w-32" />
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex justify-between"><Skeleton className="h-4 w-24" /><Skeleton className="h-5 w-14 rounded-full" /></div>
          ))}
        </div>
      </div>
    </div>
  )
}
