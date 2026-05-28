import { useState, useEffect, useCallback } from 'react'
import {
  Building2, Users, FileText, Receipt, Shield, Globe, ChevronDown,
  TrendingUp, AlertTriangle, CheckCircle, XCircle, Pause, Play, Eye, X,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import toast from 'react-hot-toast'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Spinner from '../components/ui/Spinner'
import Modal from '../components/ui/Modal'
import {
  getPlatformStats, getAllOrgs, getOrgDetail, updateOrg,
  activateOrg, deactivateOrg, suspendOrg, getPlans,
} from '../api/admin'

const STATUS_CONFIG = {
  active:    { color: 'green',  icon: CheckCircle, label: 'Active' },
  inactive:  { color: 'gray',   icon: Pause,       label: 'Inactive' },
  suspended: { color: 'red',    icon: XCircle,     label: 'Suspended' },
  trial:     { color: 'blue',   icon: TrendingUp,  label: 'Trial' },
}

const PLAN_COLORS = { free: 'gray', starter: 'blue', pro: 'green', enterprise: 'amber' }

const PIE_COLORS = ['#3B82F6', '#8B5CF6', '#10B981', '#F59E0B', '#EF4444', '#6366F1']

function StatCard({ icon: Icon, label, value, sub, color = 'blue', delay = 0 }) {
  const bg = { blue: 'from-blue-500 to-cyan-500', green: 'from-green-500 to-emerald-500', amber: 'from-amber-500 to-orange-500', red: 'from-red-500 to-rose-500', purple: 'from-purple-500 to-violet-500' }
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
      className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 flex items-center gap-4 hover:shadow-md transition-shadow"
    >
      <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${bg[color] || bg.blue} text-white shadow-lg`}>
        <Icon size={22} />
      </div>
      <div>
        <p className="text-2xl font-bold text-gray-900 dark:text-white">{value ?? '—'}</p>
        <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
        {sub && <p className="text-[10px] text-gray-400 mt-0.5">{sub}</p>}
      </div>
    </motion.div>
  )
}

function OrgRow({ org, onView, onAction }) {
  const st = STATUS_CONFIG[org.status] || STATUS_CONFIG.active
  const StIcon = st.icon
  const [acting, setActing] = useState(false)

  const handleAction = async (action) => {
    setActing(true)
    await onAction(org.id, action)
    setActing(false)
  }

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 px-5 py-4">
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-cyan-500 text-white font-bold text-sm">
          {(org.name || '?')[0].toUpperCase()}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-gray-900 dark:text-white truncate">{org.name}</span>
            <Badge variant={PLAN_COLORS[org.plan] || 'gray'}>{(org.plan || 'free').toUpperCase()}</Badge>
            <span className={`flex items-center gap-1 text-xs text-${st.color}-600`}>
              <StIcon size={12} /> {st.label}
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-400 mt-0.5">
            <span>{org.member_count || 0} members</span>
            <span>{org.request_count || 0} requests</span>
            <span>{org.expense_count || 0} expenses</span>
            {org.owner && <span>Owner: {org.owner.full_name}</span>}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <button onClick={() => onView(org.id)} className="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center gap-1">
          <Eye size={13} /> View
        </button>
        {org.status === 'active' && (
          <button onClick={() => handleAction('deactivate')} disabled={acting}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-50 text-amber-700 hover:bg-amber-100 flex items-center gap-1">
            {acting ? <Spinner size="xs" /> : <Pause size={13} />} Deactivate
          </button>
        )}
        {org.status === 'inactive' && (
          <button onClick={() => handleAction('activate')} disabled={acting}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-green-50 text-green-700 hover:bg-green-100 flex items-center gap-1">
            {acting ? <Spinner size="xs" /> : <Play size={13} />} Activate
          </button>
        )}
        {org.status === 'suspended' && (
          <button onClick={() => handleAction('activate')} disabled={acting}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-green-50 text-green-700 hover:bg-green-100 flex items-center gap-1">
            {acting ? <Spinner size="xs" /> : <Play size={13} />} Reactivate
          </button>
        )}
        {org.status !== 'suspended' && (
          <button onClick={() => handleAction('suspend')} disabled={acting}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-red-50 text-red-700 hover:bg-red-100 flex items-center gap-1">
            {acting ? <Spinner size="xs" /> : <XCircle size={13} />} Suspend
          </button>
        )}
      </div>
    </div>
  )
}

function OrgDetailModal({ orgId, onClose, onRefresh }) {
  const [org, setOrg] = useState(null)
  const [loading, setLoading] = useState(true)
  const [plans, setPlans] = useState({})
  const [selectedPlan, setSelectedPlan] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    Promise.all([getOrgDetail(orgId), getPlans()])
      .then(([orgData, planData]) => {
        setOrg(orgData.organization)
        setSelectedPlan(orgData.organization?.plan || 'free')
        setPlans(planData.plans || {})
      })
      .catch(() => toast.error('Failed to load org detail'))
      .finally(() => setLoading(false))
  }, [orgId])

  const handlePlanChange = async () => {
    if (selectedPlan === org?.plan) return
    setSaving(true)
    try {
      const data = await updateOrg(orgId, { plan: selectedPlan })
      if (data.success) {
        toast.success(`Plan updated to ${selectedPlan.toUpperCase()}`)
        onRefresh()
        setOrg(prev => ({ ...prev, plan: selectedPlan }))
      } else {
        toast.error(data.error)
      }
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to update plan')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Modal open onClose={onClose} title="Organization Detail"><div className="flex justify-center py-12"><Spinner size="lg" /></div></Modal>
  if (!org) return null

  const st = STATUS_CONFIG[org.status] || STATUS_CONFIG.active
  const features = org.plan_features || {}

  return (
    <Modal open onClose={onClose} title="">
      <div className="px-1">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">{org.name}</h2>
            <p className="text-sm text-gray-500">{org.slug} &middot; Created {(org.created_at || '').slice(0, 10)}</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={PLAN_COLORS[org.plan] || 'gray'}>{(org.plan || 'free').toUpperCase()}</Badge>
            <Badge variant={st.color}>{st.label}</Badge>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
          <div className="text-center p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <p className="text-lg font-bold text-gray-900 dark:text-white">{org.member_count}</p>
            <p className="text-[10px] text-gray-500">Members</p>
          </div>
          <div className="text-center p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <p className="text-lg font-bold text-gray-900 dark:text-white">{org.request_count}</p>
            <p className="text-[10px] text-gray-500">Requests</p>
          </div>
          <div className="text-center p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <p className="text-lg font-bold text-gray-900 dark:text-white">{org.expense_count}</p>
            <p className="text-[10px] text-gray-500">Expenses</p>
          </div>
          <div className="text-center p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <p className="text-lg font-bold text-gray-900 dark:text-white">Rs.{(org.total_spend || 0).toLocaleString()}</p>
            <p className="text-[10px] text-gray-500">Total Spend</p>
          </div>
        </div>

        {/* Plan Management */}
        <div className="mb-5 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
          <h3 className="text-sm font-bold text-gray-800 dark:text-white mb-2 flex items-center gap-2">
            <Shield size={15} className="text-blue-500" /> Plan Management
          </h3>
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <label className="text-xs text-gray-500 mb-1 block">Plan</label>
              <select value={selectedPlan} onChange={e => setSelectedPlan(e.target.value)}
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white">
                {Object.keys(plans).map(p => (
                  <option key={p} value={p}>{p.toUpperCase()} — {plans[p]?.max_members} members, {plans[p]?.max_requests_month}/mo requests</option>
                ))}
              </select>
            </div>
            <Button onClick={handlePlanChange} loading={saving} disabled={selectedPlan === org.plan} variant="primary" className="shrink-0">
              Update Plan
            </Button>
          </div>
          {features && (
            <div className="flex flex-wrap gap-2 mt-3">
              {Object.entries(features).filter(([k]) => !['max_members', 'max_requests_month', 'name'].includes(k)).map(([k, v]) => (
                <span key={k} className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${v ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-400 line-through'}`}>
                  {k.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Members */}
        <div className="mb-4">
          <h3 className="text-sm font-bold text-gray-800 dark:text-white mb-2 flex items-center gap-2">
            <Users size={15} className="text-purple-500" /> Members ({org.members?.length || 0})
          </h3>
          <div className="max-h-48 overflow-y-auto space-y-1.5">
            {(org.members || []).map(m => (
              <div key={m.user_id} className="flex items-center justify-between text-sm px-3 py-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-cyan-500 text-white text-[10px] font-bold flex items-center justify-center">
                    {m.avatar_initials || '?'}
                  </div>
                  <div>
                    <span className="font-medium text-gray-800 dark:text-white">{m.full_name}</span>
                    <span className="text-xs text-gray-400 ml-2">{m.email}</span>
                  </div>
                </div>
                <Badge variant={m.org_role === 'org_owner' ? 'amber' : m.org_role === 'org_admin' ? 'blue' : 'gray'}>
                  {(m.org_role || 'member').replace('org_', '')}
                </Badge>
              </div>
            ))}
          </div>
        </div>

        {/* Policies */}
        {org.policies?.length > 0 && (
          <div>
            <h3 className="text-sm font-bold text-gray-800 dark:text-white mb-2">Travel Policy</h3>
            {org.policies.map(p => (
              <div key={p.id} className="text-xs text-gray-600 dark:text-gray-400 grid grid-cols-2 gap-1 bg-gray-50 dark:bg-gray-700/50 p-3 rounded-lg">
                <span>Flight: {p.flight_class}</span>
                <span>Hotel: Rs.{p.hotel_budget_per_night}/night</span>
                <span>Per Diem: Rs.{p.per_diem_inr}/day</span>
                <span>Monthly: Rs.{(p.monthly_budget_inr || 0).toLocaleString()}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Modal>
  )
}

export default function PlatformAdmin() {
  const [stats, setStats] = useState(null)
  const [orgs, setOrgs] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [planFilter, setPlanFilter] = useState('')
  const [viewOrgId, setViewOrgId] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [statsData, orgsData] = await Promise.all([
        getPlatformStats(),
        getAllOrgs({ search, status: statusFilter, plan: planFilter }),
      ])
      setStats(statsData.stats)
      setOrgs(orgsData.organizations || [])
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to load admin data')
    } finally {
      setLoading(false)
    }
  }, [search, statusFilter, planFilter])

  useEffect(() => { load() }, [load])

  const handleAction = async (orgId, action) => {
    try {
      const fn = { activate: activateOrg, deactivate: deactivateOrg, suspend: suspendOrg }[action]
      if (!fn) return
      const data = await fn(orgId)
      if (data.success) {
        toast.success(data.message)
        load()
      } else {
        toast.error(data.error)
      }
    } catch (err) {
      toast.error(err.response?.data?.error || `Failed to ${action}`)
    }
  }

  if (loading && !stats) {
    return <div className="flex items-center justify-center min-h-[50vh]"><Spinner size="lg" /></div>
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Globe className="text-blue-500" size={24} /> Platform Administration
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
          Manage all organizations, plans, and platform-wide settings
        </p>
      </div>

      {/* KPI Cards */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <StatCard icon={Building2} label="Organizations" value={stats.total_orgs} sub={`${stats.active_orgs} active`} color="blue" delay={0} />
          <StatCard icon={Users} label="Total Users" value={stats.total_users} sub={`${stats.verified_users} verified`} color="purple" delay={0.05} />
          <StatCard icon={FileText} label="Travel Requests" value={stats.total_requests} color="green" delay={0.1} />
          <StatCard icon={Receipt} label="Expenses" value={stats.total_expenses} color="amber" delay={0.15} />
          <StatCard icon={TrendingUp} label="Total Spend" value={`Rs.${(stats.total_expense_amount || 0).toLocaleString()}`} color="red" delay={0.2} />
        </div>
      )}

      {/* Charts Row */}
      {stats && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.25 }}
          className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Users by Role */}
          {stats.users_by_role && Object.keys(stats.users_by_role).length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
              <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 mb-3">Users by Role</h3>
              <div className="flex items-center gap-4">
                <ResponsiveContainer width={120} height={120}>
                  <PieChart>
                    <Pie data={Object.entries(stats.users_by_role).map(([name, value]) => ({ name, value }))}
                      cx="50%" cy="50%" innerRadius={30} outerRadius={55} paddingAngle={3} dataKey="value">
                      {Object.keys(stats.users_by_role).map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex-1 space-y-1.5">
                  {Object.entries(stats.users_by_role).map(([role, count], i) => (
                    <div key={role} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }} />
                        <span className="text-gray-600 dark:text-gray-400 capitalize">{role.replace('_', ' ')}</span>
                      </div>
                      <span className="font-semibold text-gray-800 dark:text-white">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Requests by Status */}
          {stats.requests_by_status && Object.keys(stats.requests_by_status).length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
              <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 mb-3">Requests by Status</h3>
              <div className="flex items-center gap-4">
                <ResponsiveContainer width={120} height={120}>
                  <PieChart>
                    <Pie data={Object.entries(stats.requests_by_status).map(([name, value]) => ({ name, value }))}
                      cx="50%" cy="50%" innerRadius={30} outerRadius={55} paddingAngle={3} dataKey="value">
                      {Object.keys(stats.requests_by_status).map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex-1 space-y-1.5">
                  {Object.entries(stats.requests_by_status).map(([status, count], i) => (
                    <div key={status} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }} />
                        <span className="text-gray-600 dark:text-gray-400 capitalize">{status.replace('_', ' ')}</span>
                      </div>
                      <span className="font-semibold text-gray-800 dark:text-white">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </motion.div>
      )}

      {/* Filters */}
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <input type="text" placeholder="Search orgs..." value={search} onChange={e => setSearch(e.target.value)}
            className="flex-1 min-w-[180px] px-3 py-2 rounded-lg border border-gray-300 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-400" />
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            className="px-3 py-2 rounded-lg border border-gray-300 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white">
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="suspended">Suspended</option>
            <option value="trial">Trial</option>
          </select>
          <select value={planFilter} onChange={e => setPlanFilter(e.target.value)}
            className="px-3 py-2 rounded-lg border border-gray-300 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white">
            <option value="">All Plans</option>
            <option value="free">Free</option>
            <option value="starter">Starter</option>
            <option value="pro">Pro</option>
            <option value="enterprise">Enterprise</option>
          </select>
        </div>
      </Card>

      {/* Org List */}
      <div>
        <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-3">
          Organizations ({orgs.length})
        </h2>
        {orgs.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <Building2 size={40} className="mx-auto mb-3 opacity-30" />
            <p>No organizations found.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {orgs.map(org => (
              <OrgRow key={org.id} org={org} onView={setViewOrgId} onAction={handleAction} />
            ))}
          </div>
        )}
      </div>

      {/* Detail Modal */}
      {viewOrgId && (
        <OrgDetailModal orgId={viewOrgId} onClose={() => setViewOrgId(null)} onRefresh={load} />
      )}
    </div>
  )
}
