import { useState, useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { Bell, ChevronRight, Check, Menu } from 'lucide-react'
import clsx from 'clsx'
import useStore from '../../store/useStore'

const routeMeta = {
  '/dashboard':     { label: 'Dashboard',     crumbs: [], hideBreadcrumb: true },
  '/planner':       { label: 'Trip Planner',  crumbs: [], hideBreadcrumb: true },
  '/accommodation': { label: 'Accommodation', crumbs: [], hideBreadcrumb: true },
  '/expenses':      { label: 'Expenses',      crumbs: [], hideBreadcrumb: true },
  '/meetings':      { label: 'Meetings',      crumbs: [], hideBreadcrumb: true },
  '/requests':      { label: 'Requests',      crumbs: [], hideBreadcrumb: true },
  '/approvals':     { label: 'Approvals',     crumbs: [], hideBreadcrumb: true },
  '/analytics':     { label: 'Analytics',     crumbs: [], hideBreadcrumb: true },
  '/chat':          { label: 'Chat',          crumbs: [], hideBreadcrumb: true },
}

export default function Topbar() {
  const location   = useLocation()
  const meta       = routeMeta[location.pathname] || { label: 'TravelSync', crumbs: ['Home'] }
  const {
    auth,
    notifications,
    markAllNotificationsRead,
    markNotificationRead,
    apiHealth,
    sidebar,
    toggleSidebar,
    setSidebarCollapsed,
  } = useStore()

  const [notifOpen, setNotifOpen] = useState(false)
  const notifRef = useRef(null)

  const unreadCount = notifications.filter((n) => !n.read).length

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e) => {
      if (notifRef.current && !notifRef.current.contains(e.target)) {
        setNotifOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Health dot
  const healthColor =
    apiHealth.status === 'healthy'  ? 'online' :
    apiHealth.status === 'degraded' ? 'warning' : 'offline'

  const user = auth.user
  const isDashboard = location.pathname === '/dashboard'

  const handleSidebarToggle = () => {
    if (window.innerWidth < 1024) {
      setSidebarCollapsed(!sidebar.collapsed)
      return
    }
    toggleSidebar()
  }

  return (
    <header className="z-20 flex h-16 min-w-0 shrink-0 items-center gap-3 border-b border-gray-100 bg-white px-4 sm:gap-4 sm:px-6">
      <button
        type="button"
        onClick={handleSidebarToggle}
        aria-label="Toggle sidebar"
        className="lg:hidden rounded-lg border border-gray-200 p-2 text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-800"
      >
        <Menu size={18} />
      </button>

      {/* ── Title + Breadcrumb ─────────────────────── */}
      <div className="flex-1 min-w-0">
        <h1
          className={clsx(
            'font-heading leading-tight truncate text-gray-900',
            isDashboard ? 'text-2xl font-semibold tracking-tight' : 'text-xl font-bold'
          )}
        >
          {meta.label}
        </h1>
        {!meta.hideBreadcrumb && (
          <nav className="mt-0.5 hidden items-center gap-1 overflow-hidden whitespace-nowrap sm:flex" aria-label="Breadcrumb">
            {meta.crumbs.map((crumb, i) => (
              <span key={i} className="flex items-center gap-1">
                <span className="truncate text-xs text-gray-400">{crumb}</span>
                {i < meta.crumbs.length - 1 && (
                  <ChevronRight size={10} className="text-gray-300" />
                )}
              </span>
            ))}
            <ChevronRight size={10} className="text-gray-300" />
            <span className="truncate text-xs font-medium text-accent-600">{meta.label}</span>
          </nav>
        )}
      </div>

      {/* ── Right section ─────────────────────────── */}
      <div className="flex items-center gap-2 shrink-0">
        {/* API Health indicator */}
        <div
          className="flex items-center rounded-lg border border-gray-100 bg-gray-50 px-2.5 py-1.5 cursor-default"
          title={`API ${apiHealth.status || 'status unknown'}`}
        >
          <span className={clsx('status-dot', healthColor)} />
          <span className="sr-only">{`API ${apiHealth.status || 'status unknown'}`}</span>
        </div>

        {/* Notifications */}
        <div className="relative" ref={notifRef}>
          <button
            onClick={() => setNotifOpen((v) => !v)}
            className={clsx(
              'relative p-2 rounded-lg transition-colors',
              notifOpen
                ? 'bg-accent-50 text-accent-600'
                : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
            )}
            aria-label="Notifications"
          >
            <Bell size={18} />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 w-4 h-4 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center leading-none">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </button>

          {/* Notifications dropdown */}
          {notifOpen && (
            <div className="absolute right-0 top-full z-50 mt-2 w-[min(22rem,calc(100vw-1rem))] rounded-xl border border-gray-100 bg-white shadow-card-lg animate-slide-down sm:w-80">
              <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">Notifications</h3>
                  {unreadCount > 0 && (
                    <p className="text-xs text-gray-400">{unreadCount} unread</p>
                  )}
                </div>
                {unreadCount > 0 && (
                  <button
                    onClick={markAllNotificationsRead}
                    className="text-xs text-accent-600 hover:text-accent-700 font-medium"
                  >
                    Mark all read
                  </button>
                )}
              </div>

              <div className="max-h-72 overflow-y-auto divide-y divide-gray-50">
                {notifications.length === 0 ? (
                  <div className="py-8 text-center">
                    <Bell size={24} className="mx-auto text-gray-300 mb-2" />
                    <p className="text-sm text-gray-400">No notifications</p>
                  </div>
                ) : (
                  notifications.slice(0, 10).map((n) => (
                    <div
                      key={n.id}
                      className={clsx(
                        'flex items-start gap-3 px-4 py-3 transition-colors',
                        !n.read ? 'bg-accent-50/50' : 'hover:bg-gray-50'
                      )}
                    >
                      <div
                        className={clsx(
                          'w-2 h-2 rounded-full mt-1.5 shrink-0',
                          !n.read ? 'bg-accent-500' : 'bg-gray-200'
                        )}
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-800 font-medium">{n.title}</p>
                        <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{n.message}</p>
                        {n.time && (
                          <p className="text-[10px] text-gray-400 mt-1">{n.time}</p>
                        )}
                      </div>
                      {!n.read && (
                        <button
                          onClick={() => markNotificationRead(n.id)}
                          className="shrink-0 p-0.5 rounded text-gray-400 hover:text-success-600 hover:bg-success-50 transition-colors"
                        >
                          <Check size={12} />
                        </button>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>

        {/* User avatar */}
        <div className="flex items-center">
          <div className="w-8 h-8 rounded-full gradient-accent flex items-center justify-center text-white text-sm font-bold shadow-sm">
            {user?.name?.charAt(0)?.toUpperCase() || 'U'}
          </div>
        </div>
      </div>
    </header>
  )
}
