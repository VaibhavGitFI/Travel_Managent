import { useEffect, useState, useRef, useCallback } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { cn } from '../../lib/cn'
import {
  Phone, AlertTriangle, X, Loader2, MapPin, Mic, MicOff, Navigation,
  Building2, Shield, Heart, Siren, ChevronDown, ChevronUp, Copy, Check,
  CheckCircle, XCircle, ClipboardList, Map, Bell, Wallet, Calendar,
} from 'lucide-react'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import OtisLauncher from '../voice/OtisLauncher'
import useStore from '../../store/useStore'
import client from '../../api/client'
import socket from '../../lib/socket'
import { triggerSOS, getEmergencyContacts, reverseGeocode } from '../../api/sos'
import { getNotifications } from '../../api/notifications'

// ── Notification type config ─────────────────────────────────────────────────
const NOTIF_CONFIG = {
  approval:          { icon: CheckCircle,    color: 'text-emerald-500', bg: 'bg-emerald-50',  border: 'border-emerald-200', label: 'Approved' },
  rejection:         { icon: XCircle,        color: 'text-red-500',     bg: 'bg-red-50',      border: 'border-red-200',     label: 'Rejected' },
  approval_request:  { icon: ClipboardList,  color: 'text-indigo-500',  bg: 'bg-indigo-50',   border: 'border-indigo-200',  label: 'New Request' },
  trip_plan_ready:   { icon: Map,            color: 'text-violet-500',  bg: 'bg-violet-50',   border: 'border-violet-200',  label: 'Trip Plan' },
  status_update:     { icon: Navigation,     color: 'text-sky-500',     bg: 'bg-sky-50',      border: 'border-sky-200',     label: 'Status Update' },
  expense_submitted: { icon: Wallet,         color: 'text-amber-500',   bg: 'bg-amber-50',    border: 'border-amber-200',   label: 'Expense' },
  expense_approved:  { icon: CheckCircle,    color: 'text-emerald-500', bg: 'bg-emerald-50',  border: 'border-emerald-200', label: 'Expense Approved' },
  expense_rejected:  { icon: XCircle,        color: 'text-red-500',     bg: 'bg-red-50',      border: 'border-red-200',     label: 'Expense Rejected' },
  sos_alert:         { icon: AlertTriangle,  color: 'text-red-500',     bg: 'bg-red-50',      border: 'border-red-200',     label: 'SOS' },
  meeting_reminder:  { icon: Calendar,       color: 'text-sky-500',     bg: 'bg-sky-50',      border: 'border-sky-200',     label: 'Meeting' },
  info:              { icon: Bell,           color: 'text-blue-500',    bg: 'bg-blue-50',     border: 'border-blue-200',    label: 'Info' },
}

// ── Request browser notification permission on first load ────────────────────
function requestBrowserNotifPermission() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission()
  }
}

function showBrowserNotification(title, message, type) {
  if ('Notification' in window && Notification.permission === 'granted') {
    try {
      const n = new Notification(title, {
        body: message,
        icon: '/favicon.ico',
        tag: `ts-${type}-${Date.now()}`,
        silent: type !== 'sos_alert',
      })
      // Auto-close after 6 seconds
      setTimeout(() => n.close(), 6000)
    } catch { /* non-blocking */ }
  }
}

export default function Layout() {
  const { auth, addNotification, setNotifications, setApiHealth, setSidebarCollapsed, sidebar, markStale, theme } = useStore()
  const [sosOpen, setSosOpen] = useState(false)
  const [sosCity, setSosCity] = useState('')
  const [sosCountry, setSosCountry] = useState('')
  const [sosMsg, setSosMsg] = useState('')
  const [sosLoading, setSosLoading] = useState(false)
  const [sosData, setSosData] = useState(null)
  const [sosLocation, setSosLocation] = useState(null) // { lat, lng, accuracy, address }
  const [sosLocating, setSosLocating] = useState(false)
  const [sosLocError, setSosLocError] = useState('')
  const [sosEmergencyType, setSosEmergencyType] = useState('general')
  const [sosVoiceActive, setSosVoiceActive] = useState(false)
  const [sosVoiceText, setSosVoiceText] = useState('')
  const [sosExpanded, setSosExpanded] = useState({}) // which sections are expanded
  const [sosCopied, setSosCopied] = useState('')
  const recognitionRef = useRef(null)
  const locationWatchRef = useRef(null)

  // ── Sync dark mode class on <html> ──────────────────────────────────────────
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
  }, [theme])

  const navigate = useNavigate()

  // ── Request browser notification permission ─────────────────────────────────
  useEffect(() => {
    if (auth.isLoggedIn) requestBrowserNotifPermission()
  }, [auth.isLoggedIn])

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

      // Browser native notification (works in background tab)
      showBrowserNotification(data.title, data.message, data.type)

      // Styled in-app toast
      const cfg = NOTIF_CONFIG[data.type] || NOTIF_CONFIG.info
      const Icon = cfg.icon
      const actionUrl = data.action_url
      toast(
        (t) => (
          <div
            className={cn('flex items-start gap-3 cursor-pointer')}
            onClick={() => { toast.dismiss(t.id); if (actionUrl) navigate(actionUrl) }}
          >
            <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border', cfg.bg, cfg.border)}>
              <Icon size={16} className={cfg.color} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-gray-900 text-sm leading-tight">{data.title}</p>
              {data.message && <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{data.message}</p>}
              {actionUrl && <p className="text-[10px] text-blue-500 font-medium mt-1">Click to view →</p>}
            </div>
            <button onClick={(e) => { e.stopPropagation(); toast.dismiss(t.id) }}
              className="shrink-0 p-0.5 rounded text-gray-300 hover:text-gray-500 transition-colors">
              <X size={14} />
            </button>
          </div>
        ),
        {
          duration: data.type === 'sos_alert' ? 15000 : 8000,
          id: `notif-${data.request_id || Date.now()}`,
          style: {
            padding: '14px 16px',
            borderRadius: '14px',
            maxWidth: '420px',
            boxShadow: '0 10px 25px -5px rgba(0,0,0,.12), 0 4px 10px -6px rgba(0,0,0,.08)',
          },
        }
      )

      // Auto-refresh stale data for relevant notification types
      const entityMap = {
        approval: 'approvals', rejection: 'requests', approval_request: 'approvals',
        status_update: 'requests', expense_submitted: 'approvals',
        expense_approved: 'expenses', expense_rejected: 'expenses',
      }
      if (entityMap[data.type]) markStale(entityMap[data.type])
    }

    const handleTripUpdate = (data) => {
      const now = new Date()
      addNotification({
        title: data.title || 'Trip Plan Ready',
        message: data.message || '',
        time: now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        type: 'trip_plan_ready',
      })
      showBrowserNotification(data.title || 'Trip Plan Ready', data.message, 'trip_plan_ready')
      const cfg = NOTIF_CONFIG.trip_plan_ready
      const Icon = cfg.icon
      toast(
        (t) => (
          <div className="flex items-start gap-3 cursor-pointer" onClick={() => { toast.dismiss(t.id); navigate('/planner') }}>
            <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border', cfg.bg, cfg.border)}>
              <Icon size={16} className={cfg.color} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-gray-900 text-sm leading-tight">{data.title || 'Trip Plan Ready'}</p>
              <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{data.message || 'Your AI trip plan is ready!'}</p>
              <p className="text-[10px] text-violet-500 font-medium mt-1">Click to view plan →</p>
            </div>
          </div>
        ),
        {
          duration: 10000,
          style: { padding: '14px 16px', borderRadius: '14px', maxWidth: '420px',
                   boxShadow: '0 10px 25px -5px rgba(0,0,0,.12), 0 4px 10px -6px rgba(0,0,0,.08)' },
        }
      )
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

  // ── GPS Location Detection ─────────────────────────────────────────────────
  const detectLocation = useCallback(async () => {
    if (!navigator.geolocation) {
      setSosLocError('Geolocation not supported by your browser')
      return
    }
    setSosLocating(true)
    setSosLocError('')
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude, longitude, accuracy } = pos.coords
        const loc = { lat: latitude, lng: longitude, accuracy: Math.round(accuracy) }
        setSosLocation(loc)
        setSosLocating(false)
        // Reverse geocode to get city/country
        try {
          const geo = await reverseGeocode(latitude, longitude)
          if (geo.success) {
            loc.address = geo.formatted_address
            setSosLocation({ ...loc })
            if (geo.city) setSosCity(geo.city)
            if (geo.country) setSosCountry(geo.country)
            // Load emergency contacts for detected location
            if (geo.emergency_numbers) {
              setSosData(prev => ({
                ...prev,
                emergency_numbers: geo.emergency_numbers,
                embassy: geo.embassy,
                city: geo.city,
                country: geo.country,
              }))
            }
          }
        } catch { /* non-blocking */ }
      },
      (err) => {
        setSosLocating(false)
        const msgs = { 1: 'Location permission denied. Please allow location access.', 2: 'Location unavailable.', 3: 'Location request timed out.' }
        setSosLocError(msgs[err.code] || 'Failed to detect location')
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    )
  }, [])

  // ── Voice Recognition ─────────────────────────────────────────────────────
  const startVoice = useCallback(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      toast.error('Voice recognition not supported in this browser')
      return
    }
    const recognition = new SpeechRecognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'
    recognition.onresult = (event) => {
      let transcript = ''
      for (let i = 0; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript
      }
      setSosVoiceText(transcript)
      setSosMsg(transcript)
    }
    recognition.onerror = () => {
      setSosVoiceActive(false)
    }
    recognition.onend = () => {
      setSosVoiceActive(false)
    }
    recognitionRef.current = recognition
    recognition.start()
    setSosVoiceActive(true)
  }, [])

  const stopVoice = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop()
      recognitionRef.current = null
    }
    setSosVoiceActive(false)
  }, [])

  // ── Open SOS ──────────────────────────────────────────────────────────────
  const openSos = async () => {
    setSosData(null)
    setSosMsg('')
    setSosVoiceText('')
    setSosEmergencyType('general')
    setSosLocError('')
    setSosExpanded({})
    setSosCopied('')
    setSosOpen(true)
    // Immediately start detecting location
    detectLocation()
    // If we already have a city, pre-fetch contacts
    if (sosCity) {
      try {
        const contacts = await getEmergencyContacts({ city: sosCity, country: sosCountry })
        setSosData(contacts)
      } catch { /* non-blocking */ }
    }
  }

  // ── Send SOS ──────────────────────────────────────────────────────────────
  const handleSendSOS = async () => {
    setSosLoading(true)
    try {
      const result = await triggerSOS({
        city: sosCity,
        country: sosCountry,
        message: sosMsg,
        latitude: sosLocation?.lat,
        longitude: sosLocation?.lng,
        emergency_type: sosEmergencyType,
      })
      setSosData(prev => ({ ...prev, ...result }))
      addNotification({
        title: '🚨 SOS Alert Sent',
        message: `Your manager has been notified.${sosCity ? ` Location: ${sosCity}` : ''}`,
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

  // ── Copy to clipboard helper ──────────────────────────────────────────────
  const copyToClipboard = (text, label) => {
    navigator.clipboard.writeText(text).then(() => {
      setSosCopied(label)
      setTimeout(() => setSosCopied(''), 2000)
    }).catch(() => {})
  }

  // Cleanup voice/location on modal close
  useEffect(() => {
    if (!sosOpen) {
      if (recognitionRef.current) { recognitionRef.current.stop(); recognitionRef.current = null }
      if (locationWatchRef.current) { navigator.geolocation?.clearWatch(locationWatchRef.current); locationWatchRef.current = null }
      setSosVoiceActive(false)
    }
  }, [sosOpen])

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

      {/* ── OTIS Voice Launcher ──────────────────────────────────────────── */}
      <OtisLauncher />

      {/* ── Floating SOS Button ─────────────────────────────────────────── */}
      {auth.isLoggedIn && (
        <button
          type="button"
          onClick={openSos}
          aria-label="SOS Emergency"
          className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-red-600 text-white shadow-lg ring-4 ring-red-200 transition-transform hover:scale-110 hover:bg-red-700 active:scale-95 animate-pulse-slow"
        >
          <span className="text-xs font-black tracking-tighter">SOS</span>
        </button>
      )}

      {/* ── Intelligent SOS Modal ────────────────────────────────────────── */}
      {sosOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setSosOpen(false)} />
          <div className={cn(
            'relative w-full max-w-lg max-h-[90vh] rounded-2xl border shadow-2xl flex flex-col overflow-hidden',
            theme === 'dark' ? 'border-red-900/60 bg-navy-800' : 'border-red-200 bg-white'
          )}>
            {/* Header */}
            <div className="flex items-center gap-3 rounded-t-2xl bg-gradient-to-r from-red-600 to-red-700 px-5 py-4 text-white shrink-0">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/20">
                <AlertTriangle size={18} />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-bold text-base">SOS Emergency</h3>
                <p className="text-xs text-red-100 truncate">
                  {sosCity
                    ? `${[sosCity, sosCountry].filter(Boolean).join(', ')}${sosLocation?.address ? ` — ${sosLocation.address}` : ''}`
                    : sosLocating ? 'Detecting your location...' : 'Alert sent to your manager instantly'}
                </p>
              </div>
              <button type="button" onClick={() => setSosOpen(false)} className="rounded-lg p-1.5 hover:bg-red-800/50 transition-colors">
                <X size={16} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-4">

              {/* ── GPS Location Card ──────────────────────────────── */}
              <div className={cn('rounded-xl border p-3', theme === 'dark' ? 'border-navy-600 bg-navy-900' : 'border-gray-200 bg-gray-50')}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Navigation size={14} className={sosLocation ? 'text-emerald-500' : 'text-gray-400'} />
                    <span className={cn('text-xs font-semibold', theme === 'dark' ? 'text-gray-300' : 'text-gray-600')}>
                      {sosLocating ? 'Detecting precise location...' : sosLocation ? 'Location Detected' : 'Location'}
                    </span>
                  </div>
                  {!sosLocating && (
                    <button onClick={detectLocation} className="text-[10px] font-semibold text-blue-500 hover:text-blue-600">
                      {sosLocation ? 'Refresh' : 'Detect'}
                    </button>
                  )}
                </div>

                {sosLocating && (
                  <div className="flex items-center gap-2 py-2">
                    <Loader2 size={14} className="animate-spin text-blue-500" />
                    <span className={cn('text-xs', theme === 'dark' ? 'text-gray-400' : 'text-gray-500')}>Using GPS for precise coordinates...</span>
                  </div>
                )}

                {sosLocation && (
                  <div className="space-y-2">
                    {/* City & country — prominent text */}
                    <div className="flex items-center gap-2">
                      <MapPin size={14} className="text-red-500 shrink-0" />
                      <p className={cn('text-sm font-bold', theme === 'dark' ? 'text-gray-100' : 'text-gray-900')}>
                        {(sosCity || sosCountry)
                          ? [sosCity, sosCountry].filter(Boolean).join(', ')
                          : `${Math.abs(sosLocation.lat).toFixed(4)}°${sosLocation.lat >= 0 ? 'N' : 'S'}, ${Math.abs(sosLocation.lng).toFixed(4)}°${sosLocation.lng >= 0 ? 'E' : 'W'}`}
                      </p>
                    </div>
                    {/* Full address */}
                    {sosLocation.address && (
                      <p className={cn('text-xs leading-relaxed pl-6', theme === 'dark' ? 'text-gray-300' : 'text-gray-600')}>
                        {sosLocation.address}
                      </p>
                    )}
                    {/* Coordinates row */}
                    <div className="flex items-center gap-3 flex-wrap pl-6">
                      <span className={cn('text-[10px] font-mono', theme === 'dark' ? 'text-gray-400' : 'text-gray-500')}>
                        {sosLocation.lat.toFixed(6)}, {sosLocation.lng.toFixed(6)}
                      </span>
                      {sosLocation.accuracy && (
                        <span className={cn('text-[10px]', theme === 'dark' ? 'text-gray-500' : 'text-gray-400')}>
                          ±{sosLocation.accuracy}m accuracy
                        </span>
                      )}
                      <button
                        onClick={() => copyToClipboard(`${sosLocation.lat.toFixed(6)}, ${sosLocation.lng.toFixed(6)}`, 'coords')}
                        className="text-[10px] text-blue-500 hover:text-blue-600 flex items-center gap-0.5"
                      >
                        {sosCopied === 'coords' ? <Check size={9} /> : <Copy size={9} />}
                        {sosCopied === 'coords' ? 'Copied' : 'Copy'}
                      </button>
                      <a href={`https://maps.google.com/?q=${sosLocation.lat},${sosLocation.lng}`}
                        target="_blank" rel="noopener noreferrer"
                        className="text-[10px] text-blue-500 hover:text-blue-600 flex items-center gap-0.5">
                        <Navigation size={9} /> Open Map
                      </a>
                    </div>
                  </div>
                )}

                {sosLocError && (
                  <p className="text-xs text-red-500">{sosLocError}</p>
                )}
              </div>

              {/* ── Quick Call Buttons (dynamic based on detected country) ──── */}
              {(() => {
                const nums = sosData?.emergency_numbers || {}
                const amb = nums.ambulance || '108'
                const pol = nums.police || '100'
                const gen = nums.general || '112'
                const fire = nums.fire || '101'
                return (
                  <div className="grid grid-cols-4 gap-2">
                    {[
                      { label: 'Ambulance', number: amb, icon: Heart, gradient: 'from-red-500 to-rose-600' },
                      { label: 'Police', number: pol, icon: Shield, gradient: 'from-blue-500 to-indigo-600' },
                      { label: 'Fire', number: fire, icon: Siren, gradient: 'from-orange-500 to-amber-600' },
                      { label: 'General', number: gen, icon: Phone, gradient: 'from-emerald-500 to-teal-600' },
                    ].map(({ label, number, icon: Icon, gradient }) => (
                      <a key={label} href={`tel:${number}`}
                        className="flex flex-col items-center rounded-xl p-2.5 text-center text-white transition-transform hover:scale-105 active:scale-95"
                        style={{ background: `linear-gradient(135deg, var(--tw-gradient-stops))` }}
                      >
                        <div className={cn('flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br mb-1', gradient)}>
                          <Icon size={14} />
                        </div>
                        <span className={cn('text-xs font-bold', theme === 'dark' ? 'text-gray-200' : 'text-gray-900')}>{number}</span>
                        <span className={cn('text-[9px]', theme === 'dark' ? 'text-gray-400' : 'text-gray-500')}>{label}</span>
                      </a>
                    ))}
                  </div>
                )
              })()}

              {/* ── Full Emergency Numbers (expandable) ──────────── */}
              {sosData?.emergency_numbers && Object.keys(sosData.emergency_numbers).length > 4 && (
                <div className={cn('rounded-xl border', theme === 'dark' ? 'border-navy-600' : 'border-gray-200')}>
                  <button onClick={() => setSosExpanded(p => ({ ...p, numbers: !p.numbers }))}
                    className={cn('flex w-full items-center justify-between px-3 py-2.5 text-left transition-colors',
                      theme === 'dark' ? 'hover:bg-navy-700' : 'hover:bg-gray-50')}>
                    <div className="flex items-center gap-2">
                      <Phone size={13} className="text-red-500" />
                      <span className={cn('text-xs font-semibold', theme === 'dark' ? 'text-gray-300' : 'text-gray-700')}>
                        All Emergency Numbers — {sosData.city || sosCity || 'Local'}
                      </span>
                    </div>
                    {sosExpanded.numbers ? <ChevronUp size={14} className="text-gray-400" /> : <ChevronDown size={14} className="text-gray-400" />}
                  </button>
                  {sosExpanded.numbers && (
                    <div className={cn('grid grid-cols-2 gap-1.5 px-3 pb-3 border-t', theme === 'dark' ? 'border-navy-600' : 'border-gray-100')}>
                      {Object.entries(sosData.emergency_numbers)
                        .filter(([k]) => !['note', 'hospitals'].includes(k))
                        .map(([key, val]) => (
                          <a key={key} href={`tel:${val}`}
                            className={cn('flex items-center gap-1.5 rounded-lg border px-2 py-1.5 text-xs transition-colors',
                              theme === 'dark' ? 'border-navy-600 bg-navy-900 hover:bg-red-900/20 hover:border-red-800' : 'border-gray-200 bg-white hover:bg-red-50 hover:border-red-200')}>
                            <Phone size={10} className="text-gray-400 shrink-0" />
                            <span className={cn('capitalize', theme === 'dark' ? 'text-gray-400' : 'text-gray-500')}>{key.replace(/_/g, ' ')}</span>
                            <span className={cn('ml-auto font-bold', theme === 'dark' ? 'text-gray-200' : 'text-gray-800')}>{val}</span>
                          </a>
                        ))}
                    </div>
                  )}
                </div>
              )}

              {/* ── Nearby Hospitals ──────────────────────────────── */}
              {sosData?.nearby_hospitals?.length > 0 && sosData.nearby_hospitals[0]?.source !== 'fallback' && (
                <div className={cn('rounded-xl border', theme === 'dark' ? 'border-navy-600' : 'border-gray-200')}>
                  <button onClick={() => setSosExpanded(p => ({ ...p, hospitals: !p.hospitals }))}
                    className={cn('flex w-full items-center justify-between px-3 py-2.5 text-left transition-colors',
                      theme === 'dark' ? 'hover:bg-navy-700' : 'hover:bg-gray-50')}>
                    <div className="flex items-center gap-2">
                      <Building2 size={13} className="text-emerald-500" />
                      <span className={cn('text-xs font-semibold', theme === 'dark' ? 'text-gray-300' : 'text-gray-700')}>
                        Nearby Hospitals ({sosData.nearby_hospitals.length})
                      </span>
                    </div>
                    {sosExpanded.hospitals ? <ChevronUp size={14} className="text-gray-400" /> : <ChevronDown size={14} className="text-gray-400" />}
                  </button>
                  {sosExpanded.hospitals && (
                    <div className={cn('space-y-1.5 px-3 pb-3 border-t', theme === 'dark' ? 'border-navy-600' : 'border-gray-100')}>
                      {sosData.nearby_hospitals.map((h, i) => (
                        <div key={i} className={cn('rounded-lg border p-2.5', theme === 'dark' ? 'border-navy-600 bg-navy-900' : 'border-gray-100 bg-gray-50')}>
                          <p className={cn('text-xs font-semibold', theme === 'dark' ? 'text-gray-200' : 'text-gray-800')}>{h.name}</p>
                          {h.vicinity && <p className={cn('text-[10px] mt-0.5', theme === 'dark' ? 'text-gray-400' : 'text-gray-500')}>{h.vicinity}</p>}
                          <div className="flex items-center gap-2 mt-1">
                            {h.rating && <span className="text-[10px] font-semibold text-amber-500">★ {h.rating}</span>}
                            {h.open_now != null && (
                              <span className={cn('text-[10px] font-semibold', h.open_now ? 'text-emerald-500' : 'text-red-500')}>
                                {h.open_now ? 'Open now' : 'Closed'}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* ── Nearby Police Stations ────────────────────────── */}
              {sosData?.nearby_police?.length > 0 && (
                <div className={cn('rounded-xl border', theme === 'dark' ? 'border-navy-600' : 'border-gray-200')}>
                  <button onClick={() => setSosExpanded(p => ({ ...p, police: !p.police }))}
                    className={cn('flex w-full items-center justify-between px-3 py-2.5 text-left transition-colors',
                      theme === 'dark' ? 'hover:bg-navy-700' : 'hover:bg-gray-50')}>
                    <div className="flex items-center gap-2">
                      <Shield size={13} className="text-blue-500" />
                      <span className={cn('text-xs font-semibold', theme === 'dark' ? 'text-gray-300' : 'text-gray-700')}>
                        Nearby Police Stations ({sosData.nearby_police.length})
                      </span>
                    </div>
                    {sosExpanded.police ? <ChevronUp size={14} className="text-gray-400" /> : <ChevronDown size={14} className="text-gray-400" />}
                  </button>
                  {sosExpanded.police && (
                    <div className={cn('space-y-1.5 px-3 pb-3 border-t', theme === 'dark' ? 'border-navy-600' : 'border-gray-100')}>
                      {sosData.nearby_police.map((s, i) => (
                        <div key={i} className={cn('rounded-lg border p-2.5', theme === 'dark' ? 'border-navy-600 bg-navy-900' : 'border-gray-100 bg-gray-50')}>
                          <p className={cn('text-xs font-semibold', theme === 'dark' ? 'text-gray-200' : 'text-gray-800')}>{s.name}</p>
                          {s.vicinity && <p className={cn('text-[10px] mt-0.5', theme === 'dark' ? 'text-gray-400' : 'text-gray-500')}>{s.vicinity}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* ── Embassy Info ──────────────────────────────────── */}
              {sosData?.embassy && (
                <div className={cn('rounded-xl border p-3', theme === 'dark' ? 'border-indigo-800/40 bg-indigo-900/20' : 'border-indigo-200 bg-indigo-50')}>
                  <div className="flex items-center gap-2 mb-1.5">
                    <Building2 size={13} className="text-indigo-500" />
                    <span className={cn('text-xs font-semibold', theme === 'dark' ? 'text-indigo-300' : 'text-indigo-700')}>Indian Embassy / Consulate</span>
                  </div>
                  {sosData.embassy.embassy && (
                    <a href={`tel:${sosData.embassy.embassy.split(': ').pop()}`}
                      className={cn('flex items-center gap-1.5 text-xs', theme === 'dark' ? 'text-indigo-200' : 'text-indigo-800')}>
                      <Phone size={10} /> {sosData.embassy.embassy}
                    </a>
                  )}
                  {sosData.embassy.hotline && (
                    <a href={`tel:${sosData.embassy.hotline}`}
                      className={cn('flex items-center gap-1.5 text-xs mt-1', theme === 'dark' ? 'text-indigo-200' : 'text-indigo-800')}>
                      <Phone size={10} /> Emergency Hotline: {sosData.embassy.hotline}
                    </a>
                  )}
                </div>
              )}

              {/* ── Emergency Type + Message ──────────────────────── */}
              {!sosData?.message && (
                <div className="space-y-3">
                  {/* Emergency type pills */}
                  <div>
                    <label className={cn('block text-[10px] font-semibold uppercase tracking-wide mb-1.5', theme === 'dark' ? 'text-gray-400' : 'text-gray-500')}>
                      Emergency Type
                    </label>
                    <div className="flex flex-wrap gap-1.5">
                      {[
                        { value: 'medical', label: 'Medical', icon: Heart },
                        { value: 'safety', label: 'Safety Threat', icon: Shield },
                        { value: 'accident', label: 'Accident', icon: AlertTriangle },
                        { value: 'general', label: 'General', icon: Phone },
                      ].map(({ value, label, icon: Icon }) => (
                        <button key={value} onClick={() => setSosEmergencyType(value)}
                          className={cn('flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-medium transition-colors',
                            sosEmergencyType === value
                              ? 'border-red-300 bg-red-50 text-red-700'
                              : theme === 'dark' ? 'border-navy-600 text-gray-400 hover:border-navy-500' : 'border-gray-200 text-gray-500 hover:border-gray-300')}>
                          <Icon size={11} /> {label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Voice or text message */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className={cn('text-[10px] font-semibold uppercase tracking-wide', theme === 'dark' ? 'text-gray-400' : 'text-gray-500')}>
                        Describe Situation
                      </label>
                      <button
                        onClick={sosVoiceActive ? stopVoice : startVoice}
                        className={cn('flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-semibold transition-colors',
                          sosVoiceActive
                            ? 'bg-red-100 text-red-600 border border-red-300 animate-pulse'
                            : theme === 'dark' ? 'bg-navy-700 text-gray-300 hover:bg-navy-600' : 'bg-gray-100 text-gray-600 hover:bg-gray-200')}
                      >
                        {sosVoiceActive ? <MicOff size={10} /> : <Mic size={10} />}
                        {sosVoiceActive ? 'Stop' : 'Voice'}
                      </button>
                    </div>
                    <textarea
                      rows={2}
                      placeholder={sosVoiceActive ? 'Listening... speak now' : 'Type or use voice (optional)'}
                      value={sosMsg}
                      onChange={(e) => setSosMsg(e.target.value)}
                      className={cn('w-full rounded-lg border px-3 py-2 text-sm resize-none transition-colors focus:outline-none focus:ring-2 focus:ring-red-300 focus:border-red-400',
                        sosVoiceActive && 'border-red-300 ring-2 ring-red-200',
                        theme === 'dark' ? 'border-navy-600 bg-navy-900 text-gray-200 placeholder:text-gray-500' : 'border-gray-200')}
                    />
                  </div>
                </div>
              )}

              {/* ── Success / Send Button ─────────────────────────── */}
              {sosData?.message ? (
                <div className={cn('rounded-xl border px-4 py-3 text-center', theme === 'dark' ? 'border-emerald-800 bg-emerald-900/30' : 'border-green-200 bg-green-50')}>
                  <div className="flex items-center justify-center gap-2 mb-1">
                    <Check size={16} className="text-emerald-500" />
                    <span className={cn('text-sm font-bold', theme === 'dark' ? 'text-emerald-300' : 'text-green-800')}>{sosData.message}</span>
                  </div>
                  <p className={cn('text-xs', theme === 'dark' ? 'text-emerald-400' : 'text-green-600')}>
                    {sosData.timestamp && `Sent at ${new Date(sosData.timestamp).toLocaleTimeString()}`}
                  </p>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={handleSendSOS}
                  disabled={sosLoading}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-red-600 to-red-700 py-3.5 text-sm font-bold text-white shadow-lg transition-all hover:from-red-700 hover:to-red-800 disabled:opacity-60 active:scale-[0.98]"
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
