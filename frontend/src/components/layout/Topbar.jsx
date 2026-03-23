import { useState, useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Bell, Check, Menu, Search, Command } from 'lucide-react'
import { cn } from '../../lib/cn'
import useStore from '../../store/useStore'
import { markNotificationRead as apiMarkRead, markAllNotificationsRead as apiMarkAllRead } from '../../api/notifications'

const routeMeta = {
  '/dashboard':     { label: 'Dashboard' },
  '/planner':       { label: 'Trip Planner' },
  '/accommodation': { label: 'Accommodation' },
  '/expenses':      { label: 'Expenses' },
  '/meetings':      { label: 'Meetings' },
  '/requests':      { label: 'Requests' },
  '/approvals':     { label: 'Approvals' },
  '/analytics':     { label: 'Analytics' },
  '/chat':          { label: 'AI Chat' },
}

export default function Topbar() {
  const location = useLocation()
  const navigate = useNavigate()
  const meta = routeMeta[location.pathname] || { label: 'TravelSync' }
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
  const user = auth.user

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

  // Cmd+K shortcut → navigate to chat
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        navigate('/chat')
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [navigate])

  const handleMarkRead = (id) => {
    markNotificationRead(id)
    apiMarkRead(id).catch(() => {})
  }

  const handleMarkAllRead = () => {
    markAllNotificationsRead()
    apiMarkAllRead().catch(() => {})
  }

  const healthColor =
    apiHealth.status === 'healthy'  ? 'bg-emerald-500' :
    apiHealth.status === 'degraded' ? 'bg-amber-500' : 'bg-gray-400'

  const handleSidebarToggle = () => {
    if (window.innerWidth < 1024) {
      setSidebarCollapsed(!sidebar.collapsed)
      return
    }
    toggleSidebar()
  }

  return (
    <header className="z-20 flex h-14 min-w-0 shrink-0 items-center gap-3 border-b border-surface-border bg-surface-raised px-4 sm:px-6">
      {/* Mobile menu toggle */}
      <button
        type="button"
        onClick={handleSidebarToggle}
        aria-label="Toggle sidebar"
        className="lg:hidden rounded-md p-1.5 text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700"
      >
        <Menu size={18} />
      </button>

      {/* Page title */}
      <h1 className="flex-1 min-w-0 truncate font-heading text-lg font-semibold text-gray-900">
        {meta.label}
      </h1>

      {/* Right section */}
      <div className="flex items-center gap-1.5 shrink-0">
        {/* Cmd+K search trigger */}
        <button
          type="button"
          onClick={() => navigate('/chat')}
          className="hidden sm:flex items-center gap-2 rounded-lg border border-surface-border bg-surface-sunken px-3 py-1.5 text-sm text-gray-400 transition-colors hover:border-gray-300 hover:text-gray-500"
        >
          <Search size={14} />
          <span className="text-[13px]">Ask AI...</span>
          <kbd className="ml-2 flex items-center gap-0.5 rounded border border-gray-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-gray-400">
            <Command size={10} />K
          </kbd>
        </button>

        {/* Health dot */}
        <div
          className="flex items-center justify-center rounded-md p-2 cursor-default"
          title={`API: ${apiHealth.status || 'unknown'}`}
        >
          <span className={cn('h-2 w-2 rounded-full', healthColor)} />
        </div>

        {/* Notifications */}
        <div className="relative" ref={notifRef}>
          <button
            onClick={() => setNotifOpen((v) => !v)}
            className={cn(
              'relative rounded-md p-2 transition-colors',
              notifOpen
                ? 'bg-accent-50 text-accent-600'
                : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600'
            )}
            aria-label="Notifications"
          >
            <Bell size={17} />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 w-4 h-4 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center leading-none">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </button>

          {notifOpen && (
            <div className="absolute right-0 top-full z-50 mt-2 w-[min(22rem,calc(100vw-1rem))] rounded-xl border border-surface-border bg-white shadow-card-lg animate-slide-down sm:w-80">
              <div className="flex items-center justify-between px-4 py-3 border-b border-surface-border">
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">Notifications</h3>
                  {unreadCount > 0 && (
                    <p className="text-xs text-gray-400">{unreadCount} unread</p>
                  )}
                </div>
                {unreadCount > 0 && (
                  <button
                    onClick={handleMarkAllRead}
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
                      className={cn(
                        'flex items-start gap-3 px-4 py-3 transition-colors',
                        !n.read ? 'bg-accent-50/40' : 'hover:bg-gray-50'
                      )}
                    >
                      <div
                        className={cn(
                          'w-1.5 h-1.5 rounded-full mt-2 shrink-0',
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
                          onClick={() => handleMarkRead(n.id)}
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

        {/* User */}
        <div className="flex items-center gap-2 pl-1.5 border-l border-surface-border ml-1">
          <div className="w-7 h-7 rounded-full bg-brand-dark flex items-center justify-center text-white text-xs font-bold">
            {user?.name?.charAt(0)?.toUpperCase() || 'U'}
          </div>
          <span className="hidden md:block text-[13px] font-medium text-gray-700 max-w-[120px] truncate">
            {user?.name || user?.username || 'User'}
          </span>
        </div>
      </div>
    </header>
  )
}
