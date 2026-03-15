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
  Plane,
  LogOut,
  X,
} from 'lucide-react'
import clsx from 'clsx'
import useStore from '../../store/useStore'
import { logout as apiLogout } from '../../api/auth'
import toast from 'react-hot-toast'

const navItems = [
  { to: '/dashboard',     icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/planner',       icon: MapPin,           label: 'Trip Planner' },
  { to: '/accommodation', icon: Building2,        label: 'Accommodation' },
  { to: '/expenses',      icon: Receipt,          label: 'Expenses' },
  { to: '/meetings',      icon: Users,            label: 'Meetings' },
  { to: '/requests',      icon: FileText,         label: 'Requests' },
  { to: '/approvals',     icon: CheckSquare,      label: 'Approvals' },
  { to: '/analytics',     icon: BarChart3,        label: 'Analytics' },
  { to: '/chat',          icon: MessageSquare,    label: 'AI Chat' },
]

function CitySkylineSVG() {
  return (
    <svg
      viewBox="0 0 256 60"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="w-full opacity-[0.16]"
      aria-hidden="true"
    >
      {/* Skyline silhouette */}
      <path
        d="M0 60 L0 40 L8 40 L8 28 L12 28 L12 40 L20 40 L20 32 L22 20 L24 32 L24 40 L34 40 L34 36 L36 36 L36 40 L44 40 L44 22 L46 18 L48 22 L48 40 L56 40 L56 34 L62 34 L62 26 L66 26 L66 34 L72 34 L72 40 L80 40 L80 30 L82 24 L84 30 L84 40 L90 40 L90 28 L96 20 L102 28 L102 40 L108 40 L108 35 L112 35 L112 40 L120 40 L120 26 L124 18 L126 14 L128 18 L132 26 L132 40 L140 40 L140 30 L144 30 L144 40 L152 40 L152 24 L156 16 L160 24 L160 40 L168 40 L168 34 L172 34 L172 40 L180 40 L180 28 L184 28 L184 40 L190 40 L190 32 L196 26 L202 32 L202 40 L210 40 L210 36 L214 36 L214 40 L222 40 L222 30 L226 22 L230 30 L230 40 L240 40 L240 44 L244 44 L244 40 L256 40 L256 60 Z"
        fill="currentColor"
        className="text-[#E0E1DD]/30"
      />
    </svg>
  )
}

export default function Sidebar() {
  const { sidebar, toggleSidebar, setSidebarCollapsed, logout: storeLogout } = useStore()
  const collapsed = sidebar.collapsed
  const navigate = useNavigate()

  const handleLogout = async () => {
    try {
      await apiLogout()
    } catch {
      toast.error('Signed out locally (server logout unavailable)')
    }
    storeLogout()
    navigate('/login')
    toast.success('Logged out successfully')
  }

  const handleDesktopSidebarToggle = () => {
    if (typeof window !== 'undefined' && window.innerWidth < 1024) {
      return
    }
    toggleSidebar()
  }

  const handleMobileSidebarClose = () => {
    setSidebarCollapsed(true)
  }

  return (
    <aside
      className={clsx(
        'fixed inset-y-0 left-0 z-40 flex h-full shrink-0 flex-col select-none border-r border-[#2b3d59] text-[#E0E1DD] lg:relative',
        'will-change-[transform,width] transition-[transform,width] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none',
        'bg-[linear-gradient(180deg,#1B263B_0%,#22314a_52%,#1B263B_100%)] shadow-[0_16px_36px_rgba(9,14,24,0.42)]',
        collapsed
          ? 'w-[256px] -translate-x-full lg:w-[72px] lg:translate-x-0'
          : 'w-[256px] translate-x-0 lg:w-[256px]'
      )}
    >
      {/* ── Brand ─────────────────────────────────────── */}
      <div
        className={clsx(
          'flex h-16 shrink-0 items-center border-b border-[#2b3d59]',
          collapsed ? 'justify-center px-0' : 'gap-3 px-4'
        )}
      >
        <button
          type="button"
          onClick={handleDesktopSidebarToggle}
          className="shrink-0 flex h-8 w-8 cursor-default items-center justify-center rounded-lg bg-[#4CC9F0] shadow-md transition-colors hover:bg-[#39c0e8] lg:cursor-pointer"
          title={collapsed ? 'Open sidebar' : 'Close sidebar'}
        >
          <Plane size={16} className="text-[#1B263B]" />
        </button>
        {!collapsed && (
          <div className="overflow-hidden">
            <span className="block whitespace-nowrap font-heading text-base font-bold leading-tight tracking-tight text-[#E0E1DD]">
              TravelSync
            </span>
            <span className="-mt-0.5 block whitespace-nowrap text-[10px] font-semibold uppercase tracking-widest text-[#778DA9]">
              Pro
            </span>
          </div>
        )}
      </div>

      {/* ── Nav ───────────────────────────────────────── */}
      <nav className="sidebar-scroll flex-1 overflow-x-hidden overflow-y-auto px-2 py-3">
        {!collapsed && (
          <p className="mb-2 mt-1 px-3 text-[10px] font-semibold uppercase tracking-widest text-[#778DA9]">
            Navigation
          </p>
        )}
        <ul className="space-y-0.5">
          {navItems.map(({ to, icon: Icon, label }) => (
            <li key={to}>
              <NavLink
                to={to}
                className={({ isActive }) =>
                  clsx(
                    'flex items-center rounded-lg transition-all duration-150 group relative',
                    collapsed ? 'justify-center px-0 py-2.5 mx-0' : 'gap-3 px-3 py-2.5',
                    isActive
                      ? 'bg-white/10 text-white shadow-[inset_0_0_0_1px_rgba(76,201,240,0.5)]'
                      : 'text-[#B7C4D8] hover:bg-white/5 hover:text-white'
                  )
                }
                title={collapsed ? label : undefined}
              >
                {({ isActive }) => (
                  <>
                    <Icon
                        size={18}
                        className={clsx(
                          'shrink-0 transition-colors',
                          isActive ? 'text-[#4CC9F0]' : 'text-[#8197b6] group-hover:text-[#4CC9F0]'
                        )}
                      />
                    {!collapsed && (
                      <span className="text-sm font-medium leading-none">{label}</span>
                    )}
                    {/* Active indicator */}
                    {isActive && !collapsed && (
                      <span className="absolute right-2.5 h-1.5 w-1.5 rounded-full bg-[#4CC9F0]" />
                    )}
                    {/* Tooltip for collapsed */}
                    {collapsed && (
                      <span className="
                        absolute left-full ml-3 px-2.5 py-1.5 rounded-lg
                        bg-[#0f172a] text-white text-xs font-medium whitespace-nowrap
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
      </nav>

      {/* ── City Skyline ──────────────────────────────── */}
      {!collapsed && (
        <div className="px-2 mt-auto shrink-0">
          <CitySkylineSVG />
        </div>
      )}

      {/* ── Footer ───────────────────────────────────── */}
      <div
        className={clsx(
          'relative h-16 w-full shrink-0 border-t border-[#2b3d59] bg-[#162235] backdrop-blur-sm',
          collapsed ? 'flex items-center justify-center px-0' : 'flex items-center px-4'
        )}
      >
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-[#2b3d59]" />
        <button
          onClick={handleLogout}
          className={clsx(
            'rounded-lg text-[#B7C4D8] transition-colors hover:bg-white/10 hover:text-white',
            collapsed
              ? 'h-8 w-8 flex items-center justify-center'
              : 'h-8 px-3 inline-flex items-center justify-center gap-2'
          )}
          title="Logout"
        >
          <LogOut size={15} />
          {!collapsed && <span className="text-sm font-medium">Logout</span>}
        </button>
      </div>

      {/* ── Collapse Toggle ───────────────────────────── */}
      <button
        onClick={handleMobileSidebarClose}
        className="absolute right-3 top-3 z-50 flex h-7 w-7 items-center justify-center rounded-lg border border-[#2f4463] bg-[#1f2d44] text-[#c4d1e2] transition-colors hover:bg-[#253753] hover:text-white lg:hidden"
        title="Close sidebar"
      >
        <X size={13} />
      </button>
    </aside>
  )
}
