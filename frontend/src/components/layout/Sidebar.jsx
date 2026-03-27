import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  MapPin,
  Building2,
  Receipt,
  Users,
  FileText,
  CheckSquare,
  BarChart3,
  MessageSquare,
  Sparkles,
  LogOut,
  X,
  ChevronsLeft,
  ChevronsRight,
  UserCircle,
  Settings,
  Globe,
  Volume2,
} from 'lucide-react'
import { cn } from '../../lib/cn'
import useStore from '../../store/useStore'
import { logout as apiLogout } from '../../api/auth'
import toast from 'react-hot-toast'

const ELEVATED = ['manager', 'admin', 'super_admin']

const navGroups = [
  {
    label: 'Travel',
    items: [
      { to: '/dashboard',     icon: LayoutDashboard, label: 'Dashboard' },
      { to: '/planner',       icon: MapPin,          label: 'Trip Planner' },
      { to: '/accommodation', icon: Building2,       label: 'Accommodation' },
      { to: '/meetings',      icon: Users,           label: 'Meetings' },
      { to: '/chat',          icon: Sparkles,        label: 'AI Chat' },
    ],
  },
  {
    label: 'Manage',
    items: [
      { to: '/expenses',  icon: Receipt,     label: 'Expenses' },
      { to: '/requests',  icon: FileText,    label: 'Requests' },
      { to: '/approvals', icon: CheckSquare, label: 'Approvals' },
      { to: '/analytics', icon: BarChart3,   label: 'Analytics', roles: ELEVATED },
      { to: '/otis',      icon: Volume2,     label: 'OTIS Voice', roles: ELEVATED },
    ],
  },
  {
    label: 'Account',
    items: [
      { to: '/profile',         icon: UserCircle, label: 'Profile' },
      { to: '/organization',    icon: Building2,  label: 'Organization' },
      { to: '/user-management', icon: Settings,   label: 'Users', roles: ['super_admin'] },
      { to: '/platform-admin',  icon: Globe,      label: 'Platform Admin', roles: ['super_admin'] },
    ],
  },
]

export default function Sidebar() {
  const { auth, sidebar, org, toggleSidebar, setSidebarCollapsed, logout: storeLogout } = useStore()
  const collapsed = sidebar.collapsed
  const navigate = useNavigate()
  const user = auth.user
  const userRole = user?.role || 'employee'
  const orgName = org?.current?.name || user?.org_name

  // Filter nav items by role
  const filteredGroups = navGroups
    .map(group => ({
      ...group,
      items: group.items.filter(item => !item.roles || item.roles.includes(userRole)),
    }))
    .filter(group => group.items.length > 0)

  const handleLogout = async () => {
    try {
      await apiLogout()
    } catch {
      // silent — local logout still works
    }
    storeLogout()
    navigate('/login')
    toast.success('Logged out successfully')
  }

  const handleDesktopToggle = () => {
    if (typeof window !== 'undefined' && window.innerWidth < 1024) return
    toggleSidebar()
  }

  return (
    <aside
      className={cn(
        'fixed inset-y-0 left-0 z-40 flex h-full shrink-0 flex-col select-none border-r border-brand-mid/60 text-brand-light lg:relative',
        'will-change-[transform,width] transition-[transform,width] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none',
        'bg-gradient-to-b from-[#0a1628] via-[#0d2a5e] to-[#0a1628] shadow-navy',
        collapsed
          ? 'w-[256px] -translate-x-full lg:w-[68px] lg:translate-x-0'
          : 'w-[256px] translate-x-0 lg:w-[240px]'
      )}
    >
      {/* Background effects */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute inset-0" style={{
          backgroundImage: `radial-gradient(1px 1px at 15% 10%, rgba(255,255,255,0.4) 0%, transparent 100%),
            radial-gradient(1px 1px at 35% 25%, rgba(255,255,255,0.3) 0%, transparent 100%),
            radial-gradient(1px 1px at 55% 50%, rgba(255,255,255,0.2) 0%, transparent 100%),
            radial-gradient(1px 1px at 75% 70%, rgba(255,255,255,0.3) 0%, transparent 100%),
            radial-gradient(1px 1px at 25% 85%, rgba(255,255,255,0.2) 0%, transparent 100%),
            radial-gradient(1px 1px at 85% 40%, rgba(255,255,255,0.3) 0%, transparent 100%)`,
        }} />
        <div className="absolute top-0 right-0 h-32 w-32 rounded-full bg-brand-cyan/[0.04] blur-2xl" />
        <div className="absolute bottom-0 left-0 h-24 w-24 rounded-full bg-violet-500/[0.03] blur-2xl" />
      </div>

      {/* Brand */}
      <div
        className={cn(
          'relative flex h-14 shrink-0 items-center border-b border-white/[0.06]',
          collapsed ? 'justify-center px-0' : 'gap-2.5 px-4'
        )}
      >
        <button
          type="button"
          onClick={handleDesktopToggle}
          className="shrink-0 flex h-8 w-8 cursor-default items-center justify-center rounded-lg bg-brand-cyan text-brand-dark shadow-sm transition-colors hover:bg-brand-cyan/90 lg:cursor-pointer"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <MessageSquare size={15} strokeWidth={2.5} />
        </button>
        {!collapsed && (
          <div className="overflow-hidden">
            <span className="block whitespace-nowrap font-heading text-[15px] font-bold leading-tight tracking-tight text-white">
              TravelSync
            </span>
            <span className="-mt-0.5 block whitespace-nowrap text-[10px] font-medium uppercase tracking-[0.15em] text-brand-muted">
              {orgName || 'Pro'}
            </span>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="sidebar-scroll flex-1 overflow-x-hidden overflow-y-auto py-3">
        {filteredGroups.map((group) => (
          <div key={group.label} className="mb-1">
            {!collapsed && (
              <p className="mb-1.5 mt-2 px-5 text-[10px] font-semibold uppercase tracking-[0.14em] text-brand-muted/70">
                {group.label}
              </p>
            )}
            {collapsed && <div className="mx-auto my-1.5 h-px w-6 bg-white/[0.06]" />}
            <ul className="space-y-0.5 px-2">
              {group.items.map(({ to, icon: Icon, label }) => (
                <li key={to}>
                  <NavLink
                    to={to}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center rounded-lg transition-all duration-150 group relative',
                        collapsed ? 'justify-center px-0 py-2 mx-0' : 'gap-2.5 px-3 py-[7px]',
                        isActive
                          ? 'bg-white/[0.08] text-white'
                          : 'text-brand-muted hover:bg-white/[0.04] hover:text-white'
                      )
                    }
                    title={collapsed ? label : undefined}
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && (
                          <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r-full bg-brand-cyan" />
                        )}
                        <Icon
                          size={17}
                          strokeWidth={isActive ? 2.2 : 1.8}
                          className={cn(
                            'shrink-0 transition-colors',
                            isActive ? 'text-brand-cyan' : 'text-brand-muted group-hover:text-white'
                          )}
                        />
                        {!collapsed && (
                          <span className="text-[13px] font-medium leading-none">{label}</span>
                        )}
                        {collapsed && (
                          <span className="
                            absolute left-full ml-3 px-2.5 py-1.5 rounded-md
                            bg-gray-900 text-white text-xs font-medium whitespace-nowrap
                            opacity-0 pointer-events-none group-hover:opacity-100
                            transition-opacity duration-150 z-50 shadow-lg
                          ">
                            {label}
                          </span>
                        )}
                      </>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      {/* Collapse toggle — desktop only */}
      {!collapsed && (
        <div className="hidden lg:flex items-center justify-end px-3 py-1">
          <button
            type="button"
            onClick={handleDesktopToggle}
            className="rounded-md p-1 text-brand-muted/50 transition-colors hover:bg-white/[0.04] hover:text-brand-muted"
            title="Collapse sidebar"
          >
            <ChevronsLeft size={14} />
          </button>
        </div>
      )}
      {collapsed && (
        <div className="hidden lg:flex items-center justify-center px-0 py-1">
          <button
            type="button"
            onClick={handleDesktopToggle}
            className="rounded-md p-1 text-brand-muted/50 transition-colors hover:bg-white/[0.04] hover:text-brand-muted"
            title="Expand sidebar"
          >
            <ChevronsRight size={14} />
          </button>
        </div>
      )}

      {/* User + Logout footer */}
      <div
        className={cn(
          'shrink-0 border-t border-white/[0.06]',
          collapsed ? 'flex flex-col items-center gap-2 py-3' : 'flex items-center gap-2.5 px-4 py-3'
        )}
      >
        <div
          className={cn(
            'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold',
            'bg-brand-cyan/15 text-brand-cyan'
          )}
        >
          {user?.name?.charAt(0)?.toUpperCase() || 'U'}
        </div>
        {!collapsed && (
          <div className="flex-1 min-w-0">
            <p className="truncate text-[13px] font-medium text-white leading-tight">
              {user?.name || user?.username || 'User'}
            </p>
            <p className="truncate text-[11px] text-brand-muted capitalize">
              {user?.role || 'employee'}
            </p>
          </div>
        )}
        <button
          onClick={handleLogout}
          className={cn(
            'rounded-md text-brand-muted/70 transition-colors hover:bg-white/[0.06] hover:text-white',
            collapsed ? 'p-1.5' : 'p-1.5 ml-auto'
          )}
          title="Logout"
        >
          <LogOut size={15} />
        </button>
      </div>

      {/* Mobile close button */}
      <button
        onClick={() => setSidebarCollapsed(true)}
        className="absolute right-2.5 top-2.5 z-50 flex h-7 w-7 items-center justify-center rounded-md bg-white/[0.06] text-brand-muted transition-colors hover:bg-white/10 hover:text-white lg:hidden"
        title="Close sidebar"
      >
        <X size={14} />
      </button>
    </aside>
  )
}
