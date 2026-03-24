import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import toast from 'react-hot-toast'
import { cn } from '../../lib/cn'
import { Phone, AlertTriangle, X, Loader2 } from 'lucide-react'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import useStore from '../../store/useStore'
import client from '../../api/client'
import socket from '../../lib/socket'
import { triggerSOS, getEmergencyContacts } from '../../api/sos'
import { getNotifications } from '../../api/notifications'

const NOTIF_ICONS = {
  approval: '✅',
  rejection: '❌',
  approval_request: '📋',
  trip_plan_ready: '🗺️',
  expense: '💰',
}

export default function Layout() {
  const { auth, addNotification, setNotifications, setApiHealth, setSidebarCollapsed, sidebar, markStale, theme } = useStore()
  const [sosOpen,    setSosOpen]    = useState(false)
  const [sosCity,    setSosCity]    = useState('')
  const [sosMsg,     setSosMsg]     = useState('')
  const [sosLoading, setSosLoading] = useState(false)
  const [sosData,    setSosData]    = useState(null)

  // ── Sync dark mode class on <html> ──────────────────────────────────────────
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
  }, [theme])

  // ── Load persistent notifications from DB on login ──────────────────────────
  useEffect(() => {
    if (!auth.isLoggedIn) return
    getNotifications(30)
      .then((res) => {
        if (res.success && res.notifications) {
          setNotifications(res.notifications)
        }
      })
      .catch(() => {})
  }, [auth.isLoggedIn, setNotifications])

  // ── Real-time WebSocket ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!auth.isLoggedIn) return

    socket.connect()

    const handleNotification = (data) => {
      const now = new Date()
      addNotification({
        title: data.title || 'Notification',
        message: data.message || '',
        time: now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        type: data.type,
        request_id: data.request_id,
      })
      const icon = NOTIF_ICONS[data.type] || '🔔'
      toast(
        () => (
          <div className="flex items-start gap-2">
            <span className="text-lg leading-none">{icon}</span>
            <div>
              <p className="font-medium text-gray-900 text-sm">{data.title}</p>
              {data.message && <p className="text-xs text-gray-500 mt-0.5">{data.message}</p>}
            </div>
          </div>
        ),
        { duration: 6000, id: `notif-${data.request_id || Date.now()}` }
      )
    }

    const handleTripUpdate = (data) => {
      const now = new Date()
      addNotification({
        title: data.title || 'Trip Update',
        message: data.message || '',
        time: now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        type: 'trip_update',
      })
      toast.success(data.message || 'Trip plan is ready!', { duration: 5000 })
    }

    const handleDataChanged = (data) => {
      const entity = data?.entity
      if (entity && ['requests', 'meetings', 'expenses', 'approvals', 'analytics'].includes(entity)) {
        markStale(entity)
      }
    }

    socket.on('notification', handleNotification)
    socket.on('trip_update', handleTripUpdate)
    socket.on('data_changed', handleDataChanged)

    return () => {
      socket.off('notification', handleNotification)
      socket.off('trip_update', handleTripUpdate)
      socket.off('data_changed', handleDataChanged)
      socket.disconnect()
    }
  }, [auth.isLoggedIn, addNotification, markStale])

  // Poll health every 60 s
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const { data } = await client.get('/health')
        const rawServices = data.services || {}
        const services = Object.keys(rawServices).length
          ? rawServices
          : Object.fromEntries(
              Object.entries(data || {}).filter(([k]) => !['status', 'version', 'timestamp', 'error'].includes(k))
            )

        const allOk = Object.keys(services).length > 0
          && Object.values(services).every((s) => s === true || s?.status === 'ok' || s?.configured === true || s === 'ok')

        setApiHealth({
          status:      allOk ? 'healthy' : 'degraded',
          services,
          lastChecked: new Date().toISOString(),
        })
      } catch {
        setApiHealth({ status: 'degraded', services: {}, lastChecked: new Date().toISOString() })
      }
    }

    checkHealth()
    const id = setInterval(checkHealth, 60_000)
    return () => clearInterval(id)
  }, [setApiHealth])

  useEffect(() => {
    const media = window.matchMedia('(max-width: 1023px)')

    const onBreakpointChange = (event) => {
      if (event.matches) {
        setSidebarCollapsed(true)
      }
    }

    if (media.matches) {
      setSidebarCollapsed(true)
    }

    if (typeof media.addEventListener === 'function') {
      media.addEventListener('change', onBreakpointChange)
      return () => media.removeEventListener('change', onBreakpointChange)
    }

    media.addListener(onBreakpointChange)
    return () => media.removeListener(onBreakpointChange)
  }, [setSidebarCollapsed])

  const openSos = async () => {
    setSosData(null)
    setSosMsg('')
    setSosOpen(true)
    if (sosCity) {
      try {
        const contacts = await getEmergencyContacts(sosCity)
        setSosData(contacts)
      } catch { /* non-blocking */ }
    }
  }

  const handleSendSOS = async () => {
    setSosLoading(true)
    try {
      const result = await triggerSOS(sosCity, sosMsg)
      setSosData(result)
      addNotification({
        title: '🚨 SOS Alert Sent',
        message: 'Your manager has been notified.',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        type: 'sos',
      })
      toast('🚨 SOS alert sent to your manager', { duration: 8000 })
    } catch {
      toast.error('Failed to send SOS alert')
    } finally {
      setSosLoading(false)
    }
  }

  return (
    <div className={cn('relative flex h-dvh min-h-screen w-full overflow-hidden transition-colors duration-200', theme === 'dark' ? 'bg-navy-900' : 'bg-gray-50')}>
      <Sidebar />

      <button
        type="button"
        aria-label="Close sidebar"
        onClick={() => setSidebarCollapsed(true)}
        className={cn(
          'fixed inset-0 z-30 bg-slate-950/40 backdrop-blur-[1px] transition-opacity duration-300 lg:hidden',
          sidebar.collapsed ? 'pointer-events-none opacity-0' : 'opacity-100'
        )}
      />

      {/* Main content */}
      <div className="flex flex-1 min-h-0 min-w-0 flex-col overflow-hidden">
        <Topbar />

        <main className={cn('flex-1 min-h-0 overflow-x-hidden overflow-y-auto transition-colors duration-200', theme === 'dark' ? 'bg-navy-900' : 'bg-surface')}>
          <div className="page-enter min-h-full px-4 py-5 sm:px-6 sm:py-6">
            <Outlet />
          </div>
        </main>
      </div>

      {/* ── Floating SOS Button ─────────────────────────────────────────── */}
      {auth.isLoggedIn && (
        <button
          type="button"
          onClick={openSos}
          aria-label="SOS Emergency"
          className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-red-600 text-white shadow-lg ring-4 ring-red-200 transition-transform hover:scale-110 hover:bg-red-700 active:scale-95"
        >
          <span className="text-xs font-black tracking-tighter">SOS</span>
        </button>
      )}

      {/* ── SOS Modal ──────────────────────────────────────────────────── */}
      {sosOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setSosOpen(false)}
          />
          <div className={cn('relative w-full max-w-md rounded-2xl border shadow-2xl', theme === 'dark' ? 'border-red-800 bg-navy-800' : 'border-red-200 bg-white')}>
            {/* Header */}
            <div className="flex items-center gap-3 rounded-t-2xl bg-red-600 px-5 py-4 text-white">
              <AlertTriangle size={20} />
              <div className="flex-1">
                <h3 className="font-bold">SOS Emergency</h3>
                <p className="text-xs text-red-100">Alert sent to your manager instantly</p>
              </div>
              <button
                type="button"
                onClick={() => setSosOpen(false)}
                className="rounded-lg p-1 hover:bg-red-700 transition-colors"
              >
                <X size={16} />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* Quick call buttons */}
              <div className="grid grid-cols-3 gap-2">
                {[
                  { label: 'Ambulance', number: '108', color: 'bg-red-50 border-red-200 text-red-700' },
                  { label: 'Police',    number: '100', color: 'bg-blue-50 border-blue-200 text-blue-700' },
                  { label: 'General',   number: '112', color: 'bg-orange-50 border-orange-200 text-orange-700' },
                ].map(({ label, number, color }) => (
                  <a
                    key={label}
                    href={`tel:${number}`}
                    className={`flex flex-col items-center rounded-xl border p-3 text-center transition-opacity hover:opacity-80 ${color}`}
                  >
                    <Phone size={16} className="mb-1" />
                    <span className="text-xs font-bold">{number}</span>
                    <span className="text-[10px]">{label}</span>
                  </a>
                ))}
              </div>

              {/* Emergency numbers from API if available */}
              {sosData?.emergency_numbers && (
                <div className="rounded-xl border border-gray-100 bg-gray-50 p-3">
                  <p className="text-xs font-semibold text-gray-500 mb-2">
                    Local numbers — {sosData.city || sosCity}
                  </p>
                  <div className="grid grid-cols-2 gap-1.5">
                    {Object.entries(sosData.emergency_numbers)
                      .filter(([k]) => !['note'].includes(k))
                      .map(([key, val]) => (
                        <a
                          key={key}
                          href={`tel:${val}`}
                          className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs hover:bg-red-50 hover:border-red-200 transition-colors"
                        >
                          <Phone size={10} className="text-gray-400" />
                          <span className="text-gray-500 capitalize">{key.replace(/_/g, ' ')}</span>
                          <span className="ml-auto font-bold text-gray-800">{val}</span>
                        </a>
                      ))}
                  </div>
                </div>
              )}

              {/* City + message input */}
              {!sosData?.message && (
                <div className="space-y-2">
                  <input
                    type="text"
                    placeholder="Current city (optional)"
                    value={sosCity}
                    onChange={(e) => setSosCity(e.target.value)}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-300 focus:border-red-400"
                  />
                  <textarea
                    rows={2}
                    placeholder="Describe the situation (optional)"
                    value={sosMsg}
                    onChange={(e) => setSosMsg(e.target.value)}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-red-300 focus:border-red-400"
                  />
                </div>
              )}

              {sosData?.message ? (
                <div className="rounded-lg bg-green-50 border border-green-200 px-3 py-2 text-sm text-green-800 text-center font-medium">
                  ✅ {sosData.message}
                </div>
              ) : (
                <button
                  type="button"
                  onClick={handleSendSOS}
                  disabled={sosLoading}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-red-600 py-3 text-sm font-bold text-white transition-colors hover:bg-red-700 disabled:opacity-60"
                >
                  {sosLoading ? <Loader2 size={16} className="animate-spin" /> : <AlertTriangle size={16} />}
                  Send SOS Alert to Manager
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
