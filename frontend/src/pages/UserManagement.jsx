import { useState, useEffect } from 'react'
import { Users, Search, Shield, ChevronDown, Loader2, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'
import { getUsers, updateUserRole } from '../api/users'
import useStore from '../store/useStore'
import { cn } from '../lib/cn'
import { format } from 'date-fns'

const ROLES = ['employee', 'manager', 'admin', 'super_admin']

const ROLE_LABELS = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  manager: 'Manager',
  employee: 'Employee',
}

const ROLE_COLORS = {
  super_admin: 'bg-red-50 text-red-700 border-red-200',
  admin: 'bg-blue-50 text-blue-700 border-blue-200',
  manager: 'bg-violet-50 text-violet-700 border-violet-200',
  employee: 'bg-emerald-50 text-emerald-700 border-emerald-200',
}

export default function UserManagement() {
  const { auth, theme } = useStore()
  const dark = theme === 'dark'

  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [confirm, setConfirm] = useState(null) // { userId, userName, newRole }
  const [processing, setProcessing] = useState(false)

  useEffect(() => { loadUsers() }, [])

  const loadUsers = async () => {
    try {
      const params = {}
      if (roleFilter) params.role = roleFilter
      if (search) params.search = search
      const data = await getUsers(params)
      setUsers(data.users || [])
    } catch {}
    finally { setLoading(false) }
  }

  useEffect(() => {
    const timer = setTimeout(() => { setLoading(true); loadUsers() }, 300)
    return () => clearTimeout(timer)
  }, [search, roleFilter])

  const handleRoleChange = (user, newRole) => {
    if (user.id === auth.user?.id) { toast.error("Cannot change your own role"); return }
    if (user.role === newRole) return
    setConfirm({ userId: user.id, userName: user.name || user.username, oldRole: user.role, newRole })
  }

  const confirmRoleChange = async () => {
    if (!confirm) return
    setProcessing(true)
    try {
      const data = await updateUserRole(confirm.userId, confirm.newRole)
      if (data.success) {
        toast.success(data.message || 'Role updated')
        setUsers(prev => prev.map(u => u.id === confirm.userId ? { ...u, role: confirm.newRole } : u))
      } else {
        toast.error(data.error || 'Failed to update role')
      }
    } catch { toast.error('Failed to update role') }
    finally { setProcessing(false); setConfirm(null) }
  }

  const stats = {
    total: users.length,
    admins: users.filter(u => u.role === 'admin' || u.role === 'super_admin').length,
    managers: users.filter(u => u.role === 'manager').length,
    employees: users.filter(u => u.role === 'employee').length,
  }

  return (
    <div className="space-y-5">
      {/* Stats Row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Total Users', value: stats.total, color: 'text-gray-900' },
          { label: 'Admins', value: stats.admins, color: 'text-blue-600' },
          { label: 'Managers', value: stats.managers, color: 'text-violet-600' },
          { label: 'Employees', value: stats.employees, color: 'text-emerald-600' },
        ].map(s => (
          <div key={s.label} className={cn('rounded-xl border p-4 shadow-card', dark ? 'border-navy-700 bg-navy-800' : 'border-gray-200 bg-white')}>
            <p className={cn('text-2xl font-bold', s.color)}>{s.value}</p>
            <p className={cn('text-xs', dark ? 'text-brand-muted' : 'text-gray-500')}>{s.label}</p>
          </div>
        ))}
      </div>

      {/* Search & Filter */}
      <div className={cn('rounded-xl border p-4 shadow-card', dark ? 'border-navy-700 bg-navy-800' : 'border-gray-200 bg-white')}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className={cn('flex flex-1 items-center gap-2 rounded-lg border px-3 py-2', dark ? 'border-navy-600 bg-navy-900' : 'border-gray-200')}>
            <Search size={14} className={dark ? 'text-brand-muted' : 'text-gray-400'} />
            <input
              type="text"
              placeholder="Search by name, email, or username..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className={cn('flex-1 border-0 bg-transparent text-sm focus:outline-none focus:ring-0', dark ? 'text-brand-light placeholder:text-brand-muted/60' : 'text-gray-900 placeholder:text-gray-400')}
            />
          </div>
          <select
            value={roleFilter}
            onChange={e => setRoleFilter(e.target.value)}
            className={cn('rounded-lg border px-3 py-2 text-sm', dark ? 'border-navy-600 bg-navy-900 text-brand-light' : 'border-gray-200 text-gray-700')}
          >
            <option value="">All Roles</option>
            {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
          </select>
        </div>
      </div>

      {/* Users Table */}
      <div className={cn('overflow-hidden rounded-xl border shadow-card', dark ? 'border-navy-700 bg-navy-800' : 'border-gray-200 bg-white')}>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : users.length === 0 ? (
          <div className="py-12 text-center">
            <Users size={24} className={cn('mx-auto mb-2', dark ? 'text-navy-600' : 'text-gray-300')} />
            <p className={cn('text-sm', dark ? 'text-brand-muted' : 'text-gray-400')}>No users found</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={cn('border-b text-left', dark ? 'border-navy-700 bg-navy-900' : 'border-gray-100 bg-gray-50')}>
                  <th className={cn('px-4 py-3 font-semibold', dark ? 'text-brand-muted' : 'text-gray-500')}>User</th>
                  <th className={cn('px-4 py-3 font-semibold', dark ? 'text-brand-muted' : 'text-gray-500')}>Email</th>
                  <th className={cn('px-4 py-3 font-semibold', dark ? 'text-brand-muted' : 'text-gray-500')}>Department</th>
                  <th className={cn('px-4 py-3 font-semibold', dark ? 'text-brand-muted' : 'text-gray-500')}>Role</th>
                  <th className={cn('px-4 py-3 font-semibold', dark ? 'text-brand-muted' : 'text-gray-500')}>Joined</th>
                </tr>
              </thead>
              <tbody className={cn('divide-y', dark ? 'divide-navy-700' : 'divide-gray-100')}>
                {users.map(u => (
                  <tr key={u.id} className={cn('transition-colors', dark ? 'hover:bg-navy-700/30' : 'hover:bg-gray-50/50')}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <div className={cn('flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold overflow-hidden',
                          u.profile_picture ? '' : 'bg-gradient-to-br from-brand-dark to-brand-mid text-white')}>
                          {u.profile_picture
                            ? <img src={`/api/uploads/${u.profile_picture}`} alt="" className="h-full w-full object-cover" />
                            : (u.avatar_initials || u.name?.charAt(0)?.toUpperCase() || 'U')
                          }
                        </div>
                        <div>
                          <p className={cn('font-medium', dark ? 'text-brand-light' : 'text-gray-900')}>{u.name || u.username}</p>
                          <p className={cn('text-xs', dark ? 'text-brand-muted' : 'text-gray-400')}>@{u.username}</p>
                        </div>
                      </div>
                    </td>
                    <td className={cn('px-4 py-3', dark ? 'text-brand-muted' : 'text-gray-600')}>{u.email}</td>
                    <td className={cn('px-4 py-3', dark ? 'text-brand-muted' : 'text-gray-600')}>{u.department || '-'}</td>
                    <td className="px-4 py-3">
                      {u.id === auth.user?.id ? (
                        <span className={cn('rounded-full border px-2.5 py-0.5 text-xs font-semibold', ROLE_COLORS[u.role] || ROLE_COLORS.employee)}>
                          {ROLE_LABELS[u.role] || u.role} (you)
                        </span>
                      ) : (
                        <div className="relative inline-block">
                          <select
                            value={u.role}
                            onChange={e => handleRoleChange(u, e.target.value)}
                            className={cn('appearance-none rounded-full border px-3 py-1 pr-7 text-xs font-semibold cursor-pointer focus:outline-none focus:ring-2 focus:ring-brand-cyan/20',
                              ROLE_COLORS[u.role] || ROLE_COLORS.employee)}
                          >
                            {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                          </select>
                          <ChevronDown size={10} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 opacity-50" />
                        </div>
                      )}
                    </td>
                    <td className={cn('px-4 py-3 text-xs', dark ? 'text-navy-400' : 'text-gray-400')}>
                      {u.created_at ? (() => { try { return format(new Date(u.created_at), 'MMM d, yyyy') } catch { return '-' } })() : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Confirmation Modal */}
      {confirm && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => !processing && setConfirm(null)} />
          <div className={cn('relative w-full max-w-sm rounded-2xl border p-6 shadow-2xl', dark ? 'border-navy-700 bg-navy-800' : 'border-gray-200 bg-white')}>
            <div className="mb-4 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-amber-50">
                <AlertTriangle size={18} className="text-amber-600" />
              </div>
              <div>
                <h3 className={cn('font-semibold', dark ? 'text-brand-light' : 'text-gray-900')}>Change Role</h3>
                <p className={cn('text-xs', dark ? 'text-brand-muted' : 'text-gray-500')}>This action changes user permissions</p>
              </div>
            </div>
            <p className={cn('text-sm mb-5', dark ? 'text-brand-muted' : 'text-gray-600')}>
              Change <strong>{confirm.userName}</strong> from{' '}
              <span className="font-semibold">{ROLE_LABELS[confirm.oldRole]}</span> to{' '}
              <span className="font-semibold">{ROLE_LABELS[confirm.newRole]}</span>?
            </p>
            <div className="flex gap-2">
              <button onClick={() => setConfirm(null)} disabled={processing}
                className={cn('flex-1 rounded-lg border py-2 text-sm font-medium transition-colors',
                  dark ? 'border-navy-600 text-brand-muted hover:bg-navy-700' : 'border-gray-200 text-gray-600 hover:bg-gray-50')}>
                Cancel
              </button>
              <button onClick={confirmRoleChange} disabled={processing}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-brand-dark py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-mid disabled:opacity-50">
                {processing ? <Loader2 size={14} className="animate-spin" /> : <Shield size={14} />}
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
