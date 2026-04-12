import { useEffect, useState, useCallback } from 'react'
import {
  Plane, Hotel, Receipt, Clock, MapPin, Calendar, Users, ArrowRight,
  Sparkles, Brain, AlertTriangle, Info, X, Shield, BarChart3,
  ChevronRight, Wallet, Leaf, Moon,
  CheckSquare, XCircle, Navigation, TrendingUp, TrendingDown,
} from 'lucide-react'
import { BarChart, Bar, Cell, ResponsiveContainer, Tooltip as ReTooltip } from 'recharts'
import { format } from 'date-fns'
import toast from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'
import useStore from '../store/useStore'
import { getDashboardStats, getAlerts, getSpendAnalysis, getCarbonAnalytics } from '../api/analytics'
import { getApprovals, approveRequest, rejectRequest } from '../api/approvals'
import { getTrips } from '../api/trips'
import { SkeletonRow } from '../components/ui/Skeleton'
import useAutoRefresh from '../hooks/useAutoRefresh'

// ── Status config ──────────────────────────────────────────────
const STATUS = {
  approved:    { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200' },
  pending:     { bg: 'bg-amber-50',   text: 'text-amber-700',   border: 'border-amber-200'   },
  rejected:    { bg: 'bg-red-50',     text: 'text-red-700',     border: 'border-red-200'     },
  completed:   { bg: 'bg-gray-50',    text: 'text-gray-500',    border: 'border-gray-200'    },
  booked:      { bg: 'bg-sky-50',     text: 'text-sky-700',     border: 'border-sky-200'     },
  in_progress: { bg: 'bg-blue-50',    text: 'text-blue-700',    border: 'border-blue-200'    },
  draft:       { bg: 'bg-gray-50',    text: 'text-gray-500',    border: 'border-gray-200'    },
}
const tripStatus = (s) => STATUS[(s || 'draft').toLowerCase()] || STATUS.draft

function budgetColor(pct) {
  if (pct >= 90) return { bar: 'bg-red-500',    text: 'text-red-400'    }
  if (pct >= 75) return { bar: 'bg-amber-500',  text: 'text-amber-400'  }
  return              { bar: 'bg-emerald-500', text: 'text-emerald-400' }
}

function getTimeOfDay() {
  const h = new Date().getHours()
  return h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening'
}

// ─────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const { auth }  = useStore()
  const navigate  = useNavigate()
  const user      = auth.user
  const isManager = ['manager', 'admin', 'super_admin'].includes(user?.role)

  const [stats,   setStats]   = useState(null)
  const [trips,   setTrips]   = useState([])
  const [loading, setLoading] = useState(true)
  const [alerts,  setAlerts]  = useState([])
  const [dismissed, setDismissed] = useState(new Set())
  const [spendData,  setSpendData]  = useState(null)
  const [carbonData, setCarbonData] = useState(null)
  const [pendingApprovals, setPending]     = useState([])
  const [approvingId,      setApprovingId] = useState(null)

  const load = useCallback(async () => {
    try {
      const calls = [
        getDashboardStats(), getTrips(), getAlerts(),
        getSpendAnalysis(), getCarbonAnalytics(),
      ]
      if (isManager) calls.push(getApprovals())
      const [sR, tR, aR, spR, cR, apR] = await Promise.allSettled(calls)

      if (sR.status  === 'fulfilled') setStats(sR.value)
      if (tR.status  === 'fulfilled') {
        const d = tR.value; setTrips(Array.isArray(d) ? d : d.trips || [])
      }
      if (aR.status  === 'fulfilled') setAlerts(aR.value?.alerts || [])
      if (spR.status === 'fulfilled') setSpendData(spR.value)
      if (cR.status  === 'fulfilled') setCarbonData(cR.value)
      if (isManager && apR?.status === 'fulfilled') {
        const raw = apR.value
        const list = Array.isArray(raw) ? raw : raw?.approvals || []
        setPending(list.filter((a) => a.status === 'pending').slice(0, 4))
      }
    } catch { toast.error('Failed to load dashboard') }
    finally  { setLoading(false) }
  }, [isManager])

  useEffect(() => { load() }, [load])
  useAutoRefresh('requests',  load)
  useAutoRefresh('analytics', load)

  const recentTrips   = trips.slice(0, 5)
  const visibleAlerts = alerts.filter((a) => !dismissed.has(a.title))
  const trend         = spendData?.monthly_trend || []
  const nextTrip      = stats?.next_trip
  const activeTrip    = stats?.active_trip
  const budgetPct     = stats?.budget_utilization_pct ?? 0
  const monthlyBudget = stats?.monthly_budget ?? 0
  const monthlySpend  = stats?.monthly_spend ?? 0
  const nightsAway    = stats?.nights_away_30d ?? 0
  const bc              = budgetColor(budgetPct)
  const todayMeetings   = stats?.today_meetings   ?? 0
  const expensesPending = stats?.expenses_pending ?? 0

  const handleApprove = async (id) => {
    setApprovingId(id)
    try   { await approveRequest(id); toast.success('Approved'); await load() }
    catch { toast.error('Failed') }
    finally { setApprovingId(null) }
  }
  const handleReject = async (id) => {
    setApprovingId(id)
    try   { await rejectRequest(id, 'Rejected from dashboard'); toast.success('Rejected'); await load() }
    catch { toast.error('Failed') }
    finally { setApprovingId(null) }
  }

  return (
    <div className="mx-auto w-full max-w-7xl space-y-4">

      {/* ══════════════  HERO  ════════════════════════════════════ */}
      <section className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-[#0a1628] via-[#0d2a5e] to-[#1a4a8a] shadow-navy">
        {/* bg layers */}
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(76,201,240,0.14),transparent_55%)]" />
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_left,rgba(139,92,246,0.07),transparent_55%)]" />
        <div className="pointer-events-none absolute inset-0" style={{ backgroundImage: `
          radial-gradient(1px 1px at 12% 18%,rgba(255,255,255,.65) 0%,transparent 100%),
          radial-gradient(1px 1px at 30% 8%,rgba(255,255,255,.45) 0%,transparent 100%),
          radial-gradient(1.5px 1.5px at 50% 22%,rgba(255,255,255,.55) 0%,transparent 100%),
          radial-gradient(1px 1px at 68% 6%,rgba(255,255,255,.35) 0%,transparent 100%),
          radial-gradient(1px 1px at 84% 14%,rgba(255,255,255,.45) 0%,transparent 100%)` }}
        />
        {/* plane trail */}
        <svg className="pointer-events-none absolute right-6 top-3 w-28 h-28 opacity-[0.05] sm:w-40 sm:h-40" viewBox="0 0 200 200" fill="none">
          <path d="M20 180 Q60 120 100 100 Q140 80 180 20" stroke="white" strokeWidth="1.5" strokeDasharray="6 4"/>
          <path d="M175 15 L180 20 L185 10 Z" fill="white"/>
          <circle cx="100" cy="100" r="3" fill="rgba(76,201,240,.5)"/>
          <circle cx="60"  cy="140" r="2" fill="rgba(76,201,240,.3)"/>
        </svg>
        <div className="pointer-events-none absolute -right-10 -bottom-10 h-44 w-44 rounded-full border border-white/[0.04]" />
        <div className="pointer-events-none absolute bottom-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-brand-cyan/25 to-transparent" />

        <div className="relative px-5 pt-5 pb-4 sm:px-7 sm:pt-6">
          {/* top row */}
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="flex h-5 w-5 items-center justify-center rounded bg-brand-cyan/20">
                  <Sparkles size={10} className="text-brand-cyan" />
                </div>
                <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-brand-cyan">
                  AI-Powered Dashboard
                </span>
                {activeTrip && (
                  <span className="flex items-center gap-1.5 rounded-full border border-emerald-400/30 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                    <span className="relative flex h-1.5 w-1.5">
                      <span className="animate-ping absolute inset-0 rounded-full bg-emerald-400 opacity-75" />
                      <span className="relative rounded-full h-1.5 w-1.5 bg-emerald-400" />
                    </span>
                    Live · {activeTrip.destination}
                  </span>
                )}
              </div>
              <h2 className="mt-1.5 font-heading text-xl font-bold tracking-tight text-white sm:text-2xl">
                Good {getTimeOfDay()}, {user?.name?.split(' ')[0] || 'Traveler'}
              </h2>
              <div className="mt-0.5 flex items-center gap-3">
                <p className="text-xs text-brand-muted">{format(new Date(), 'EEEE, MMMM d, yyyy')}</p>
                {nightsAway > 0 && (
                  <span className="flex items-center gap-1 text-[10px] text-white/40">
                    <Moon size={9} />
                    {nightsAway}n away
                    {nightsAway >= 15 && <span className="text-amber-400 font-medium">· fatigue risk</span>}
                  </span>
                )}
              </div>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => navigate('/planner')}
                className="flex items-center gap-1.5 rounded-xl border border-white/15 bg-white/[0.07] px-3.5 py-2 text-xs font-medium text-white backdrop-blur-sm transition-all hover:bg-white/14"
              >
                <MapPin size={13} /> Plan Trip
              </button>
              <button
                onClick={() => navigate('/chat')}
                className="flex items-center gap-1.5 rounded-xl bg-brand-cyan px-3.5 py-2 text-xs font-semibold text-brand-dark transition-all hover:bg-brand-cyan/90"
              >
                <Brain size={13} /> AI Assistant
              </button>
            </div>
          </div>

        </div>
      </section>

      {/* ══════════════  ALERTS  ══════════════════════════════════ */}
      {visibleAlerts.length > 0 && (
        <section className="space-y-1.5">
          {visibleAlerts.map((a, i) => (
            <AlertCard key={i} alert={a}
              onDismiss={() => setDismissed((p) => new Set([...p, a.title]))}
              onAction={() => a.action?.target && navigate(a.action.target)}
            />
          ))}
        </section>
      )}

      {/* ══════════════  KPI STRIP  ═══════════════════════════════ */}
      <section className="grid grid-cols-2 gap-3 xl:grid-cols-4">

        {/* Total Trips */}
        <KpiCard
          onClick={() => navigate('/requests')}
          icon={<Plane size={15} />}
          iconClass="bg-blue-50 text-blue-600"
          value={loading ? '—' : (stats?.total_trips ?? 0)}
          label="Total Trips"
          footer={<span className="text-gray-600">View all <ChevronRight size={10} className="inline" /></span>}
        />

        {/* Budget */}
        <button
          onClick={() => navigate('/expenses')}
          className="group text-left rounded-xl border border-gray-200 bg-white shadow-card p-4 transition-all hover:shadow-md"
        >
          {loading ? <KpiSkeleton /> : (
            <div className="flex flex-col h-full">
              <div className="flex items-center justify-between mb-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-50 border border-emerald-100">
                  <Wallet size={14} className="text-emerald-600" />
                </div>
                {monthlyBudget > 0 && (
                  <span className={`text-[11px] font-semibold ${bc.text}`}>{budgetPct}%</span>
                )}
              </div>
              <div className="text-xl font-bold text-gray-900 leading-tight">
                ₹{Number(monthlyBudget > 0 ? monthlySpend : (stats?.total_expenses ?? 0)).toLocaleString('en-IN')}
              </div>
              <div className="text-[11px] text-gray-700 mt-0.5">
                {monthlyBudget > 0 ? 'Spent This Month' : 'Total Expenses'}
              </div>
              {monthlyBudget > 0 && (
                <div className="mt-2.5">
                  <div className="h-1 w-full rounded-full bg-gray-100 overflow-hidden">
                    <div className={`h-full rounded-full transition-all duration-700 ${bc.bar}`} style={{ width: `${budgetPct}%` }} />
                  </div>
                  <div className="mt-1 text-[10px] text-gray-500">
                    of ₹{Number(monthlyBudget).toLocaleString('en-IN')}
                  </div>
                </div>
              )}
            </div>
          )}
        </button>

        {/* Pending Approvals */}
        <KpiCard
          onClick={() => navigate('/approvals')}
          icon={<Clock size={15} />}
          iconClass="bg-amber-50 text-amber-600"
          value={loading ? '—' : (stats?.pending_approvals ?? 0)}
          label="Pending Approvals"
          footer={<span className="text-gray-600">Review <ChevronRight size={10} className="inline" /></span>}
          highlight={!loading && (stats?.pending_approvals ?? 0) > 0}
        />

        {/* Compliance */}
        <KpiCard
          onClick={() => navigate('/analytics')}
          icon={<Shield size={15} />}
          iconClass="bg-sky-50 text-sky-600"
          value={loading ? '—' : (stats?.compliance_score != null ? `${stats.compliance_score}%` : '—')}
          label="Compliance Score"
          footer={
            !loading && stats?.compliance_score != null ? (
              stats.compliance_score >= 80
                ? <span className="text-emerald-500 flex items-center gap-0.5"><TrendingUp size={10} /> On track</span>
                : stats.compliance_score < 60
                  ? <span className="text-red-400 flex items-center gap-0.5"><TrendingDown size={10} /> Needs attention</span>
                  : <span className="text-amber-400">Moderate</span>
            ) : null
          }
        />
      </section>

      {/* ══════════════  TODAY STRIP  ════════════════════════════ */}
      {!loading && (activeTrip || nextTrip?.days_until === 0 || todayMeetings > 0 || expensesPending > 0) && (
        <div className="flex flex-wrap items-center gap-2">
          {activeTrip && (
            <span className="flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold text-emerald-700">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inset-0 rounded-full bg-emerald-400 opacity-75" />
                <span className="relative rounded-full h-1.5 w-1.5 bg-emerald-400" />
              </span>
              On trip · {activeTrip.destination}
            </span>
          )}
          {!activeTrip && nextTrip?.days_until === 0 && (
            <span className="flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-[11px] font-semibold text-blue-700">
              <Navigation size={10} />
              Departing today · {nextTrip.destination}
            </span>
          )}
          {todayMeetings > 0 && (
            <span
              onClick={() => navigate('/meetings')}
              className="flex cursor-pointer items-center gap-1.5 rounded-full border border-violet-200 bg-violet-50 px-3 py-1 text-[11px] font-semibold text-violet-700 hover:bg-violet-100 transition-colors"
            >
              <Calendar size={10} />
              {todayMeetings} meeting{todayMeetings !== 1 ? 's' : ''} today
            </span>
          )}
          {expensesPending > 0 && (
            <span
              onClick={() => navigate('/expenses')}
              className="flex cursor-pointer items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-[11px] font-semibold text-amber-700 hover:bg-amber-100 transition-colors"
            >
              <Receipt size={10} />
              {expensesPending} expense{expensesPending !== 1 ? 's' : ''} pending
            </span>
          )}
        </div>
      )}

      {/* ══════════════  MAIN GRID  ═══════════════════════════════ */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">

        {/* ── LEFT (2/3) ──────────────────────────────────────── */}
        <div className="lg:col-span-2 flex flex-col gap-4">

          {/* Next Trip + Spend Sparkline — sparkline goes full-width when no next trip */}
          <div className={`grid grid-cols-1 gap-3 ${loading || nextTrip ? 'sm:grid-cols-2' : ''}`}>

            {/* Next Trip — hidden when no upcoming trip and not loading */}
            {(loading || nextTrip) && <section className="rounded-xl border border-gray-200 bg-white shadow-card overflow-hidden">
              <div className="flex items-center gap-2 border-b border-gray-100 px-4 py-3">
                <div className="flex h-6 w-6 items-center justify-center rounded-md bg-blue-50">
                  <Navigation size={12} className="text-blue-600" />
                </div>
                <h3 className="text-xs font-semibold text-gray-900">Next Trip</h3>
              </div>
              {loading ? (
                <div className="px-4 py-4 space-y-2">
                  <div className="skeleton h-5 w-28" />
                  <div className="skeleton h-3.5 w-40" />
                  <div className="skeleton h-3.5 w-20 mt-1" />
                </div>
              ) : nextTrip ? (
                <div className="px-4 py-3.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-0.5">Destination</p>
                      <p className="text-base font-bold text-gray-900 truncate leading-tight">{nextTrip.destination}</p>
                      {nextTrip.origin && (
                        <p className="text-[11px] text-gray-600 truncate">from {nextTrip.origin}</p>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      {nextTrip.days_until === 0
                        ? <span className="text-sm font-bold text-emerald-500">Today</span>
                        : <><div className="text-2xl font-black text-brand-cyan leading-none">{nextTrip.days_until}</div>
                           <div className="text-[10px] text-gray-600">day{nextTrip.days_until !== 1 ? 's' : ''}</div></>
                      }
                    </div>
                  </div>
                  <div className="mt-3 flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <Calendar size={10} className="text-gray-500" />
                      <span className="text-[11px] text-gray-700">{nextTrip.start_date}</span>
                    </div>
                    <StatusPill status={nextTrip.status} />
                  </div>
                  <button
                    onClick={() => navigate('/requests')}
                    className="mt-3 flex w-full items-center justify-center gap-1 rounded-lg border border-gray-200 py-1.5 text-[11px] font-medium text-gray-700 transition-colors hover:bg-gray-50"
                  >
                    View request <ArrowRight size={10} />
                  </button>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center px-4 py-6 text-center">
                  <Plane size={20} className="mb-1.5 text-gray-300" />
                  <p className="text-xs text-gray-400">No upcoming trips</p>
                  <button onClick={() => navigate('/planner')} className="mt-2 text-[11px] font-medium text-brand-cyan hover:underline">
                    Plan one →
                  </button>
                </div>
              )}
            </section>}

            {/* Spend Sparkline */}
            <section className="rounded-xl border border-gray-200 bg-white shadow-card overflow-hidden">
              <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
                <div className="flex items-center gap-2">
                  <div className="flex h-6 w-6 items-center justify-center rounded-md bg-amber-50">
                    <BarChart3 size={12} className="text-amber-600" />
                  </div>
                  <h3 className="text-xs font-semibold text-gray-900">Spend Trend</h3>
                </div>
                <button onClick={() => navigate('/analytics')} className="text-[10px] font-medium text-gray-600 hover:text-brand-cyan transition-colors">
                  Full →
                </button>
              </div>
              <div className="px-3 pt-3 pb-2">
                {loading || trend.length === 0 ? (
                  <div className="flex items-end gap-1 h-16">
                    {[40, 60, 35, 70, 50, 85].map((h, i) => (
                      <div key={i} className="skeleton flex-1 rounded-sm" style={{ height: `${h}%` }} />
                    ))}
                  </div>
                ) : (
                  <>
                    <ResponsiveContainer width="100%" height={68}>
                      <BarChart data={trend} barCategoryGap="20%" margin={{ top: 2, right: 2, left: 2, bottom: 0 }}>
                        <ReTooltip
                          formatter={(v) => [`₹${Number(v).toLocaleString('en-IN')}`, '']}
                          labelFormatter={(l) => trend.find((m) => m.month === l || m.label === l)?.label || l}
                          contentStyle={{ fontSize: 11, borderRadius: 8, border: '1px solid #e5e7eb', padding: '4px 8px' }}
                          cursor={{ fill: 'rgba(0,0,0,0.03)' }}
                        />
                        <Bar dataKey="amount" radius={[3, 3, 0, 0]}>
                          {trend.map((_, i) => (
                            <Cell key={i} fill={i === trend.length - 1 ? '#4CC9F0' : 'rgba(76,201,240,0.2)'} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                    <div className="flex mt-0.5">
                      {trend.map((m, i) => (
                        <span key={i} className={`flex-1 text-center text-[9px] ${i === trend.length - 1 ? 'font-semibold text-brand-cyan' : 'text-gray-500'}`}>
                          {(m.label || m.month || '').slice(0, 3)}
                        </span>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </section>
          </div>

          {/* Recent Trips */}
          <section className="flex-1 rounded-xl border border-gray-200 bg-white shadow-card">
            <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3.5">
              <div>
                <h3 className="text-sm font-semibold text-gray-900">Recent Trips</h3>
                <p className="text-[11px] text-gray-600">Your latest travel requests</p>
              </div>
              <button onClick={() => navigate('/requests')} className="flex items-center gap-1 text-[11px] font-medium text-gray-600 hover:text-brand-cyan transition-colors">
                View all <ArrowRight size={11} />
              </button>
            </div>
            {loading ? (
              <div className="divide-y divide-gray-100">
                {Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)}
              </div>
            ) : recentTrips.length === 0 ? (
              <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
                <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-50 to-cyan-50">
                  <Plane size={20} className="text-brand-cyan" />
                </div>
                <p className="text-sm font-semibold text-gray-800">No trips yet</p>
                <p className="mt-0.5 text-xs text-gray-500">Plan your first AI-powered trip</p>
                <button onClick={() => navigate('/planner')}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  <Sparkles size={11} className="text-brand-cyan" /> Plan a Trip
                </button>
              </div>
            ) : (
              <div className="divide-y divide-gray-100">
                {recentTrips.map((trip, i) => <TripRow key={trip.id || i} trip={trip} />)}
              </div>
            )}
          </section>
        </div>

        {/* ── RIGHT (1/3) ─────────────────────────────────────── */}
        <div className="flex flex-col gap-3">

          {/* Manager Approvals */}
          {isManager && pendingApprovals.length > 0 && (
            <section className="rounded-xl border border-amber-200 bg-amber-50/50 shadow-card overflow-hidden">
              <div className="flex items-center gap-2 border-b border-amber-200/50 px-4 py-3">
                <div className="flex h-6 w-6 items-center justify-center rounded-md bg-amber-100">
                  <Clock size={12} className="text-amber-700" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-xs font-semibold text-amber-900">Pending Approvals</h3>
                  <p className="text-[10px] text-amber-700">{pendingApprovals.length} need action</p>
                </div>
                <button onClick={() => navigate('/approvals')} className="text-[10px] font-medium text-amber-700 hover:text-amber-900">All →</button>
              </div>
              <div className="divide-y divide-amber-100/60">
                {pendingApprovals.map((ap) => (
                  <ApprovalRow key={ap.id} approval={ap} busy={approvingId === ap.id}
                    onApprove={() => handleApprove(ap.id)}
                    onReject={() => handleReject(ap.id)}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Shortcuts — 2×2 tile grid */}
          <section className="rounded-xl border border-gray-200 bg-white shadow-card p-4">
            <h3 className="mb-3 text-xs font-semibold text-gray-900">Shortcuts</h3>
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: 'New Trip',  icon: Plane,   to: '/planner',       c: 'bg-blue-50    text-blue-600'    },
                { label: 'Expense',   icon: Receipt, to: '/expenses',      c: 'bg-emerald-50 text-emerald-600' },
                { label: 'Hotel',     icon: Hotel,   to: '/accommodation', c: 'bg-violet-50  text-violet-600'  },
                { label: 'Meeting',   icon: Users,   to: '/meetings',      c: 'bg-amber-50   text-amber-600'   },
              ].map((a) => (
                <button key={a.label} onClick={() => navigate(a.to)}
                  className="group flex flex-col items-center gap-1.5 rounded-xl border border-gray-100 py-3.5 transition-all hover:border-gray-200 hover:bg-gray-50"
                >
                  <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${a.c}`}>
                    <a.icon size={15} />
                  </div>
                  <span className="text-[11px] font-semibold text-gray-700 group-hover:text-gray-900">{a.label}</span>
                </button>
              ))}
            </div>
          </section>

          {/* Carbon Widget */}
          {carbonData?.success && (
            <section className="flex-1 rounded-xl border border-emerald-200 bg-emerald-50/40 shadow-card p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="flex h-6 w-6 items-center justify-center rounded-md bg-emerald-100">
                    <Leaf size={12} className="text-emerald-700" />
                  </div>
                  <h3 className="text-xs font-semibold text-emerald-900">Carbon Footprint</h3>
                </div>
                <button onClick={() => navigate('/analytics')} className="text-[10px] font-medium text-emerald-700 hover:text-emerald-900">View →</button>
              </div>
              <div className="flex items-end justify-between">
                <div>
                  <div className="text-xl font-black text-emerald-800 leading-none">
                    {carbonData.total_co2_kg?.toFixed(1) ?? '0'}<span className="text-xs font-medium ml-0.5">kg CO₂</span>
                  </div>
                  <div className="text-[10px] text-emerald-600 mt-0.5">total emissions</div>
                </div>
                <div className="text-right">
                  <div className="text-base font-bold text-emerald-700">{carbonData.trees_to_offset ?? 0}</div>
                  <div className="text-[10px] text-emerald-600">trees to offset</div>
                </div>
              </div>
              {carbonData.greener_suggestions?.length > 0 && (
                <p className="mt-2.5 text-[10px] text-emerald-700 bg-emerald-100/60 rounded-lg px-2.5 py-1.5">
                  <Sparkles size={9} className="inline mr-1" />
                  {carbonData.greener_suggestions[0].saving_pct}% savings possible on {carbonData.greener_suggestions[0].route}
                </p>
              )}
            </section>
          )}

        </div>
      </div>

    </div>
  )
}

// ── Reusable KPI Card ──────────────────────────────────────────
function KpiCard({ onClick, icon, iconClass, value, label, footer, highlight }) {
  return (
    <button
      onClick={onClick}
      className={`group text-left rounded-xl border bg-white shadow-card p-4 transition-all hover:shadow-md ${highlight ? 'border-amber-200' : 'border-gray-200'}`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className={`flex h-7 w-7 items-center justify-center rounded-lg border ${iconClass} ${highlight ? 'border-amber-100' : 'border-transparent'}`}>
          {icon}
        </div>
      </div>
      <div className="text-xl font-bold text-gray-900 leading-tight">{value}</div>
      <div className="text-[11px] text-gray-700 mt-0.5 mb-2">{label}</div>
      <div className="text-[11px]">{footer}</div>
    </button>
  )
}

function KpiSkeleton() {
  return (
    <div className="space-y-2">
      <div className="skeleton h-7 w-7 rounded-lg" />
      <div className="skeleton h-6 w-20 mt-2" />
      <div className="skeleton h-3.5 w-28" />
    </div>
  )
}

// ── Trip Row ───────────────────────────────────────────────────
function TripRow({ trip }) {
  return (
    <div className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-gray-50/60">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-blue-50 border border-blue-100">
        <Plane size={13} className="text-blue-600" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="truncate text-sm font-medium text-gray-900">
          {trip.from_city || trip.source || '—'} → {trip.to_city || trip.destination}
        </p>
        <p className="text-[11px] text-gray-500 mt-0.5">
          {trip.travel_date || trip.departure_date || 'Date TBD'}
          {trip.return_date && ` – ${trip.return_date}`}
          {trip.estimated_budget ? ` · ₹${Number(trip.estimated_budget).toLocaleString('en-IN')}` : ''}
        </p>
      </div>
      <StatusPill status={trip.status} />
    </div>
  )
}

// ── Status Pill ────────────────────────────────────────────────
function StatusPill({ status }) {
  const s = tripStatus(status)
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold capitalize ${s.bg} ${s.text} ${s.border}`}>
      <span className="h-1 w-1 rounded-full bg-current" />
      {(status || 'draft').replace(/_/g, ' ')}
    </span>
  )
}

// ── Alert Card ─────────────────────────────────────────────────
function AlertCard({ alert, onDismiss, onAction }) {
  const S = {
    info:     { card: 'border-blue-200  bg-blue-50/80',  icon: 'text-blue-500',  text: 'text-blue-900'  },
    warning:  { card: 'border-amber-200 bg-amber-50/80', icon: 'text-amber-500', text: 'text-amber-900' },
    critical: { card: 'border-red-200   bg-red-50/80',   icon: 'text-red-500',   text: 'text-red-900'   },
  }
  const st = S[alert.severity] || S.info
  const Icon = alert.severity === 'info' ? Info : AlertTriangle
  return (
    <div className={`flex items-start gap-3 rounded-xl border px-4 py-2.5 ${st.card}`}>
      <Icon size={14} className={`mt-0.5 shrink-0 ${st.icon}`} />
      <div className={`min-w-0 flex-1 ${st.text}`}>
        <p className="text-xs font-semibold">{alert.title}</p>
        <p className="text-[11px] opacity-75">{alert.message}</p>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {alert.action?.target && (
          <button onClick={onAction} className="rounded px-2 py-0.5 text-[11px] font-medium hover:bg-black/5">View</button>
        )}
        <button onClick={onDismiss} className="rounded p-1 hover:bg-black/5" aria-label="Dismiss"><X size={12} /></button>
      </div>
    </div>
  )
}

// ── Approval Row ───────────────────────────────────────────────
function ApprovalRow({ approval, busy, onApprove, onReject }) {
  return (
    <div className="flex items-center gap-3 px-4 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-semibold text-amber-900 truncate">
          {approval.employee_name || approval.requester_name || 'Employee'}
        </p>
        <p className="text-[10px] text-amber-700 truncate">
          {approval.destination || 'Trip'}
          {(approval.travel_date || approval.start_date) && ` · ${approval.travel_date || approval.start_date}`}
        </p>
      </div>
      <div className="flex gap-1.5 shrink-0">
        <button onClick={onApprove} disabled={busy}
          className="flex h-6 w-6 items-center justify-center rounded-md bg-emerald-100 text-emerald-700 hover:bg-emerald-200 disabled:opacity-40"
          title="Approve"
        ><CheckSquare size={11} /></button>
        <button onClick={onReject} disabled={busy}
          className="flex h-6 w-6 items-center justify-center rounded-md bg-red-100 text-red-700 hover:bg-red-200 disabled:opacity-40"
          title="Reject"
        ><XCircle size={11} /></button>
      </div>
    </div>
  )
}
