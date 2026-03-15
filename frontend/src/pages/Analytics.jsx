import { useState, useEffect } from 'react'
import {
  TrendingUp, IndianRupee, MapPin, Users,
  CheckCircle, PieChart, Activity, Calendar,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { getDashboardStats, getSpendAnalysis, getComplianceScorecard } from '../api/analytics'
import StatCard from '../components/ui/StatCard'
import Badge from '../components/ui/Badge'
import Spinner from '../components/ui/Spinner'

export default function Analytics() {
  const [stats,       setStats]       = useState(null)
  const [spendData,   setSpendData]   = useState(null)
  const [compliance,  setCompliance]  = useState(null)
  const [loading,     setLoading]     = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const [s, sp, c] = await Promise.allSettled([
          getDashboardStats(),
          getSpendAnalysis(),
          getComplianceScorecard(),
        ])
        if (s.status  === 'fulfilled') setStats(s.value)
        if (sp.status === 'fulfilled') setSpendData(sp.value)
        if (c.status  === 'fulfilled') setCompliance(c.value)
      } catch { toast.error('Failed to load analytics') }
      finally { setLoading(false) }
    }
    load()
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <Spinner size="lg" color="accent" />
      </div>
    )
  }

  const topStats = [
    { icon: <IndianRupee size={20} />, value: formatCurrency(stats?.total_expenses),       label: 'Total Spend',        accentColor: 'blue',   trend: null },
    { icon: <MapPin size={20} />,      value: stats?.total_trips ?? 0,                      label: 'Total Trips',        accentColor: 'sky',    trend: null },
    { icon: <Users size={20} />,       value: stats?.team_size ?? 0,                        label: 'Active Travelers',   accentColor: 'green',  trend: null },
    { icon: <CheckCircle size={20} />, value: `${stats?.compliance_score ?? 0}%`,           label: 'Compliance Score',   accentColor: 'orange', trend: null },
  ]

  const categories = spendData?.by_category || []
  const topCities  = spendData?.top_cities  || []
  const monthly    = spendData?.monthly_trend || []

  return (
    <div className="mx-auto w-full max-w-7xl space-y-4 rounded-3xl border border-[#cdd6e0] bg-[radial-gradient(circle_at_top_left,#f6f9fc_0%,transparent_38%),linear-gradient(180deg,#edf1f5_0%,#E0E1DD_100%)] px-3 pb-6 pt-4 sm:space-y-5 sm:px-5 md:px-6 md:pb-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900 font-heading">Analytics</h2>
          <p className="text-sm text-gray-500 mt-0.5">Insights into travel spend and compliance</p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-50 border border-gray-100">
          <Calendar size={14} className="text-gray-400" />
          <span className="text-xs text-gray-500 font-medium">Last 12 months</span>
        </div>
      </div>

      {/* Top stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {topStats.map((s) => (
          <StatCard key={s.label} {...s} />
        ))}
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Spend by category */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-100 shadow-card p-6">
          <div className="flex items-center gap-2 mb-5">
            <PieChart size={16} className="text-accent-600" />
            <h3 className="font-semibold text-gray-900 font-heading">Spend by Category</h3>
          </div>

          {categories.length > 0 ? (
            <div className="space-y-3">
              {categories.map((cat, i) => {
                const maxVal = Math.max(...categories.map((c) => c.amount || c.total || 0))
                const val    = cat.amount || cat.total || 0
                const pct    = maxVal ? Math.round((val / maxVal) * 100) : 0
                const colors = ['bg-accent-500', 'bg-sky-500', 'bg-success-500', 'bg-warning-500', 'bg-purple-500', 'bg-red-400']
                return (
                  <div key={i} className="flex items-center gap-3">
                    <span className="text-sm text-gray-600 w-28 truncate capitalize shrink-0">
                      {cat.category || cat.name}
                    </span>
                    <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ${colors[i % colors.length]}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-sm font-semibold text-gray-800 w-24 text-right shrink-0">
                      {formatCurrency(val)}
                    </span>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-sm text-gray-400">No categorized spend data available yet.</p>
          )}
        </div>

        {/* Top cities */}
        <div className="bg-white rounded-xl border border-gray-100 shadow-card p-6">
          <div className="flex items-center gap-2 mb-5">
            <MapPin size={16} className="text-sky-600" />
            <h3 className="font-semibold text-gray-900 font-heading">Top Destinations</h3>
          </div>

          {topCities.length > 0 ? (
            <div className="space-y-3">
              {topCities.slice(0, 6).map((city, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-5 h-5 rounded-full bg-gray-100 flex items-center justify-center text-xs font-bold text-gray-500">
                      {i + 1}
                    </span>
                    <span className="text-sm text-gray-700">{city.city || city.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="sky" size="xs">{city.trips || city.count} trips</Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400">No destination data available yet.</p>
          )}
        </div>
      </div>

      {/* Monthly trend */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-card p-6">
        <div className="flex items-center gap-2 mb-5">
          <TrendingUp size={16} className="text-success-600" />
          <h3 className="font-semibold text-gray-900 font-heading">Monthly Spend Trend</h3>
        </div>
        {monthly.length > 0 ? (
          <MonthlyBarChart data={monthly} />
        ) : (
          <p className="text-sm text-gray-400">No monthly trend data available yet.</p>
        )}
      </div>

      {/* Compliance scorecard */}
      {compliance && (
        <div className="bg-white rounded-xl border border-gray-100 shadow-card p-6">
          <div className="flex items-center gap-2 mb-5">
            <Activity size={16} className="text-warning-600" />
            <h3 className="font-semibold text-gray-900 font-heading">Policy Compliance</h3>
          </div>
          <ComplianceDisplay compliance={compliance} />
        </div>
      )}
    </div>
  )
}

function MonthlyBarChart({ data }) {
  const max = Math.max(...data.map((d) => d.amount || d.total || 0))
  return (
    <div className="flex items-end gap-3 h-32">
      {data.slice(0, 12).map((d, i) => {
        const val = d.amount || d.total || 0
        const h   = max ? (val / max) * 100 : 0
        return (
          <div key={i} className="flex-1 flex flex-col items-center gap-1">
            <div
              className="w-full rounded-t-md bg-accent-500 opacity-80 hover:opacity-100 transition-all"
              style={{ height: `${h}%` }}
              title={`${d.month || d.label}: ${formatCurrency(val)}`}
            />
            <span className="text-xs text-gray-400">{d.month || d.label || ''}</span>
          </div>
        )
      })}
    </div>
  )
}

function ComplianceDisplay({ compliance }) {
  const score  = compliance.score ?? compliance.overall_score ?? 0
  const checks = compliance.checks || compliance.items || []

  const scoreColor =
    score >= 80 ? 'text-success-600' :
    score >= 60 ? 'text-warning-600' :
    'text-red-500'

  return (
    <div className="flex flex-col md:flex-row gap-6">
      <div className="flex items-center justify-center w-32 h-32 rounded-full border-4 border-gray-100 shrink-0 mx-auto md:mx-0">
        <div className="text-center">
          <div className={`text-3xl font-bold font-heading ${scoreColor}`}>{score}</div>
          <div className="text-xs text-gray-400">/ 100</div>
        </div>
      </div>
      {checks.length > 0 && (
        <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-3">
          {checks.map((c, i) => (
            <div key={i} className="flex items-center gap-2 p-3 rounded-lg bg-gray-50">
              <CheckCircle size={14} className={c.passed ? 'text-success-500' : 'text-red-400'} />
              <span className="text-sm text-gray-700">{c.label || c.name}</span>
              <Badge variant={c.passed ? 'green' : 'red'} size="xs" className="ml-auto">
                {c.passed ? 'Pass' : 'Fail'}
              </Badge>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function formatCurrency(val) {
  if (val == null) return '₹0'
  return `₹${Number(val).toLocaleString('en-IN')}`
}
