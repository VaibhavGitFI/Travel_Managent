import { useEffect, useState } from 'react'
import {
  Plane, Hotel, Receipt, TrendingUp, Clock, CheckCircle,
  MapPin, Calendar, Users, Activity, ArrowRight, Zap,
} from 'lucide-react'
import { format } from 'date-fns'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import { getDashboardStats } from '../api/analytics'
import { getTrips } from '../api/trips'
import StatCard from '../components/ui/StatCard'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Spinner from '../components/ui/Spinner'
import { useNavigate } from 'react-router-dom'

export default function Dashboard() {
  const { auth, apiHealth } = useStore()
  const navigate  = useNavigate()
  const user      = auth.user

  const [stats,  setStats]  = useState(null)
  const [trips,  setTrips]  = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const [statsData, tripsData] = await Promise.allSettled([
          getDashboardStats(),
          getTrips(),
        ])
        if (statsData.status === 'fulfilled') setStats(statsData.value)
        if (tripsData.status === 'fulfilled') {
          const td = tripsData.value
          setTrips(Array.isArray(td) ? td : td.trips || [])
        }
      } catch (err) {
        toast.error('Failed to load dashboard data')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const statCards = [
    {
      icon: <Plane size={20} />,
      value: loading ? '—' : (stats?.total_trips ?? trips.length ?? 0),
      label: 'Total Trips',
      trend: null,
      accentColor: 'corporate',
    },
    {
      icon: <Receipt size={20} />,
      value: loading ? '—' : (stats?.total_expenses
        ? `₹${Number(stats.total_expenses).toLocaleString('en-IN')}`
        : '₹0'),
      label: 'Total Expenses',
      trend: null,
      accentColor: 'corporate',
    },
    {
      icon: <CheckCircle size={20} />,
      value: loading ? '—' : (stats?.pending_approvals ?? 0),
      label: 'Pending Approvals',
      trend: null,
      accentColor: 'corporate',
    },
    {
      icon: <TrendingUp size={20} />,
      value: loading ? '—' : (stats?.compliance_score
        ? `${stats.compliance_score}%`
        : '—'),
      label: 'Compliance Score',
      trend: null,
      accentColor: 'corporate',
    },
  ]

  const recentTrips = trips.slice(0, 5)
  const healthEntries = Object.entries(apiHealth?.services || {})
  const systemStatus = healthEntries.map(([key, value]) => ({
    label: formatServiceName(key),
    ok: value === true || value === 'ok' || value?.configured === true || value?.status === 'ok',
  }))
  const cardSurfaceClass =
    'rounded-xl border border-[#d2dae4] bg-white shadow-[0_12px_24px_rgba(27,38,59,0.08)]'
  const quickStatSurfaceClass =
    'flex items-center gap-3 rounded-xl border border-[#d2dae4] bg-white px-4 py-3 shadow-[0_6px_16px_rgba(27,38,59,0.05)]'

  return (
    <div className="mx-auto w-full max-w-7xl space-y-4 rounded-3xl border border-[#cdd6e0] bg-[radial-gradient(circle_at_top_left,#f6f9fc_0%,transparent_38%),linear-gradient(180deg,#edf1f5_0%,#E0E1DD_100%)] px-3 pb-6 pt-4 sm:space-y-6 sm:px-5 md:px-6 md:pb-8">
      {/* ── Welcome banner ─────────────────────────── */}
      <div className="relative overflow-hidden rounded-2xl border border-[#d2dae4] bg-[linear-gradient(135deg,#ffffff_0%,#f2f6fb_56%,#e7edf4_100%)] p-4 shadow-[0_14px_30px_rgba(27,38,59,0.1)] sm:p-6 md:p-8">
        <div className="relative flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#4CC9F0]">
              Dashboard overview
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight text-[#1B263B] font-heading sm:text-3xl">
              Good {getTimeOfDay()}, {user?.name?.split(' ')[0] || 'Traveler'}
            </h2>
            <p className="mt-1.5 text-sm text-[#44566f] sm:text-base">
              {format(new Date(), 'EEEE, MMMM d, yyyy')} — Here's your travel overview
            </p>
          </div>

          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<MapPin size={15} />}
              className="w-full justify-center border border-[#c7d1dd] bg-white text-[#1B263B] hover:bg-[#f8fbff] sm:w-auto"
              onClick={() => navigate('/planner')}
            >
              Plan New Trip
            </Button>
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<Zap size={15} />}
              className="w-full justify-center border border-[#4CC9F0] bg-[#4CC9F0] text-[#1B263B] hover:bg-[#35bee9] sm:w-auto"
              onClick={() => navigate('/chat')}
            >
              AI Assistant
            </Button>
          </div>
        </div>

        {/* Quick stats bar */}
        <div className="relative mt-5 grid grid-cols-1 gap-2.5 sm:grid-cols-2 md:mt-6 xl:grid-cols-4">
          {[
            { label: 'Upcoming trips',  value: stats?.upcoming_trips ?? '—',  icon: Calendar },
            { label: 'Active requests', value: stats?.active_requests ?? '—', icon: Clock },
            { label: 'Team members',    value: stats?.team_size ?? '—',       icon: Users },
            { label: 'Cities visited',  value: stats?.cities_visited ?? '—',  icon: MapPin },
          ].map((s) => (
            <div key={s.label} className={quickStatSurfaceClass}>
              <s.icon size={16} className="shrink-0 text-[#778DA9]" />
              <div>
                <div className="text-lg font-bold leading-tight text-[#1B263B]">{s.value}</div>
                <div className="text-xs text-[#778DA9]">{s.label}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Stat cards ─────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {statCards.map((s) => (
          <StatCard
            key={s.label}
            icon={s.icon}
            value={s.value}
            label={s.label}
            trend={s.trend}
            trendLabel={s.trendLabel}
            accentColor={s.accentColor}
            className={cardSurfaceClass}
            loading={loading}
          />
        ))}
      </div>

      {/* ── Bottom grid ───────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3 lg:gap-6">
        {/* Recent trips */}
        <div className={`lg:col-span-2 ${cardSurfaceClass}`}>
          <div className="flex items-center justify-between border-b border-[#d7dee7] px-4 py-4 sm:px-6">
            <div>
              <h3 className="text-base font-semibold text-[#1B263B] font-heading">Recent Trips</h3>
              <p className="mt-0.5 text-xs text-[#778DA9]">Your latest travel requests</p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              rightIcon={<ArrowRight size={14} />}
              onClick={() => navigate('/planner')}
            >
              View all
            </Button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-10 sm:py-12">
              <Spinner size="md" color="accent" />
            </div>
          ) : recentTrips.length === 0 ? (
            <div className="px-4 py-10 text-center sm:py-12">
              <Plane size={32} className="mx-auto mb-3 text-[#9cc8db]" />
              <p className="font-medium text-[#44566f]">No trips yet</p>
              <p className="mt-1 text-sm text-[#778DA9]">Plan your first trip to get started</p>
              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={() => navigate('/planner')}
              >
                Plan a Trip
              </Button>
            </div>
          ) : (
            <div className="divide-y divide-[#e0e6ee]">
              {recentTrips.map((trip, i) => (
                <TripRow key={trip.id || i} trip={trip} />
              ))}
            </div>
          )}
        </div>

        {/* Quick actions */}
        <div className="space-y-4">
          <div className={`${cardSurfaceClass} p-4 sm:p-5`}>
            <h3 className="mb-4 text-base font-semibold text-[#1B263B] font-heading">Quick Actions</h3>
            <div className="space-y-2">
              {[
                { label: 'New Trip',           icon: Plane,   to: '/planner' },
                { label: 'Submit Expense',     icon: Receipt, to: '/expenses' },
                { label: 'Book Accommodation', icon: Hotel,   to: '/accommodation' },
                { label: 'Schedule Meeting',   icon: Users,   to: '/meetings' },
              ].map((a) => (
                <button
                  key={a.label}
                  onClick={() => navigate(a.to)}
                  className="group flex w-full items-center gap-3 rounded-xl border border-[#d6dee7] bg-white p-3 transition-all hover:border-[#4CC9F0]/65 hover:bg-[#f5fbff]"
                >
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#eef8fd] text-[#1B263B]">
                    <a.icon size={16} />
                  </div>
                  <span className="text-sm font-medium text-[#2c3d57] group-hover:text-[#1B263B]">{a.label}</span>
                  <ArrowRight size={14} className="ml-auto text-[#9aabbe] transition-colors group-hover:text-[#4CC9F0]" />
                </button>
              ))}
            </div>
          </div>

          {/* Activity */}
          <div className={`${cardSurfaceClass} p-4 sm:p-5`}>
            <div className="flex items-center gap-2 mb-4">
              <Activity size={16} className="text-[#1B263B]" />
              <h3 className="text-base font-semibold text-[#1B263B] font-heading">System Status</h3>
            </div>
            {systemStatus.length === 0 ? (
              <p className="text-sm text-[#778DA9]">Health data is not available yet.</p>
            ) : (
              <div className="space-y-3">
                {systemStatus.map((s) => (
                  <div key={s.label} className="flex items-center justify-between">
                    <span className="text-sm text-[#44566f]">{s.label}</span>
                    <div className="flex items-center gap-1.5">
                      <span className={`status-dot ${s.ok ? 'online' : 'offline'}`} />
                      <span className={`text-xs font-medium ${s.ok ? 'text-success-600' : 'text-red-500'}`}>
                        {s.ok ? 'Operational' : 'Unavailable'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function TripRow({ trip }) {
  const statusMap = {
    approved:   'green',
    pending:    'orange',
    rejected:   'red',
    completed:  'gray',
    planning:   'sky',
  }
  const statusVariant = statusMap[trip.status?.toLowerCase()] || 'gray'

  return (
    <div className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-[#f4f8fc] sm:gap-4 sm:px-6 sm:py-4">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-[#d2e4ef] bg-[#eef8fd]">
        <Plane size={15} className="text-[#1B263B]" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="truncate text-sm font-semibold text-[#1B263B]">
          {trip.from_city || trip.source} → {trip.to_city || trip.destination}
        </p>
        <p className="mt-0.5 text-xs text-[#778DA9]">
          {trip.travel_date || trip.departure_date || 'Date TBD'}
          {trip.return_date && ` – ${trip.return_date}`}
        </p>
      </div>
      <Badge variant={statusVariant} dot>
        {trip.status || 'Draft'}
      </Badge>
    </div>
  )
}

function getTimeOfDay() {
  const h = new Date().getHours()
  if (h < 12) return 'morning'
  if (h < 17) return 'afternoon'
  return 'evening'
}

function formatServiceName(key) {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}
