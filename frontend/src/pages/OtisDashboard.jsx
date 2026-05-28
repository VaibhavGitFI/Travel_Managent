import { useState, useEffect, useCallback } from 'react'
import {
  Volume2, TrendingUp, Clock, MessageSquare, Activity, Settings,
  Calendar, Zap, CheckCircle, XCircle, BarChart3, Trash2, Eye,
  ChevronDown, ChevronUp, Download, Filter, RefreshCw,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import {
  getOtisStatus,
  listOtisSessions,
  getOtisSession,
  deleteOtisSession,
  getOtisAnalytics,
  getOtisCommands,
  getOtisSettings,
  updateOtisSettings,
} from '../api/otis'
import useStore from '../store/useStore'
import StatCard from '../components/ui/StatCard'
import Spinner from '../components/ui/Spinner'
import { Skeleton } from '../components/ui/Skeleton'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import { cn } from '../lib/cn'

const formatDuration = (seconds) => {
  if (!seconds) return '0s'
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
}

const formatDate = (dateStr) => {
  try {
    return format(new Date(dateStr), 'MMM d, h:mm a')
  } catch {
    return dateStr
  }
}

const LoadingSkeleton = () => (
  <div className="mx-auto w-full max-w-7xl space-y-5">
    <Skeleton className="h-20 w-full" />
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
      {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24" />)}
    </div>
    <Skeleton className="h-96 w-full" />
  </div>
)

export default function OtisDashboard() {
  const { auth, theme } = useStore()
  const dark = theme === 'dark'

  // Data state
  const [status, setStatus] = useState(null)
  const [analytics, setAnalytics] = useState(null)
  const [sessions, setSessions] = useState([])
  const [commands, setCommands] = useState([])
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)

  // UI state
  const [selectedSession, setSelectedSession] = useState(null)
  const [sessionDetails, setSessionDetails] = useState(null)
  const [activeTab, setActiveTab] = useState('overview') // overview | sessions | commands | settings
  const [period, setPeriod] = useState('7d')
  const [expandedSessions, setExpandedSessions] = useState({})
  const [settingsEditing, setSettingsEditing] = useState(false)

  // Load data
  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const [statusRes, analyticsRes, sessionsRes, commandsRes, settingsRes] = await Promise.allSettled([
        getOtisStatus(),
        getOtisAnalytics(period),
        listOtisSessions(20),
        getOtisCommands(50),
        getOtisSettings(),
      ])

      if (statusRes.status === 'fulfilled') setStatus(statusRes.value)
      if (analyticsRes.status === 'fulfilled') setAnalytics(analyticsRes.value)
      if (sessionsRes.status === 'fulfilled') setSessions(sessionsRes.value.sessions || [])
      if (commandsRes.status === 'fulfilled') setCommands(commandsRes.value.commands || [])
      if (settingsRes.status === 'fulfilled') setSettings(settingsRes.value.settings || {})
    } catch (error) {
      console.error('[OTIS Dashboard] Load failed:', error)
      toast.error('Failed to load OTIS data')
    } finally {
      setLoading(false)
    }
  }, [period])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleViewSession = async (sessionId) => {
    try {
      const data = await getOtisSession(sessionId)
      setSessionDetails(data)
      setSelectedSession(sessionId)
    } catch (error) {
      toast.error('Failed to load session details')
    }
  }

  const handleDeleteSession = async (sessionId) => {
    if (!confirm('Delete this session? This cannot be undone.')) return

    try {
      await deleteOtisSession(sessionId)
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId))
      if (selectedSession === sessionId) {
        setSelectedSession(null)
        setSessionDetails(null)
      }
      toast.success('Session deleted')
    } catch (error) {
      toast.error('Failed to delete session')
    }
  }

  const handleUpdateSettings = async (newSettings) => {
    try {
      await updateOtisSettings(newSettings)
      setSettings(newSettings)
      setSettingsEditing(false)
      toast.success('Settings updated')
    } catch (error) {
      toast.error('Failed to update settings')
    }
  }

  const toggleSessionExpand = (sessionId) => {
    setExpandedSessions((prev) => ({
      ...prev,
      [sessionId]: !prev[sessionId],
    }))
  }

  if (loading) return <LoadingSkeleton />

  if (!status?.available) {
    return (
      <div className="mx-auto w-full max-w-7xl">
        <Card className="p-8 text-center">
          <div className="mx-auto w-16 h-16 rounded-full bg-red-100 flex items-center justify-center mb-4">
            <XCircle className="w-8 h-8 text-red-500" />
          </div>
          <h2 className="text-xl font-bold text-gray-900 mb-2">OTIS Unavailable</h2>
          <p className="text-gray-500">{status?.reason || 'OTIS is not available'}</p>
        </Card>
      </div>
    )
  }

  const summary = analytics?.summary || {}
  const daily = analytics?.daily || []

  return (
    <div className="mx-auto w-full max-w-7xl space-y-5">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-purple-600">
              <Volume2 size={14} className="text-white" />
            </div>
            <h1 className="font-heading text-xl font-bold text-gray-900">OTIS Dashboard</h1>
            <span className="rounded-full bg-blue-50 border border-blue-200 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-blue-600">
              Voice AI
            </span>
          </div>
          <p className="mt-1 text-sm text-gray-500">Voice assistant analytics, session history, and settings</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 text-sm text-gray-700 transition-colors"
          >
            <RefreshCw size={13} />
            Refresh
          </button>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-sm text-gray-700"
          >
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="90d">Last 90 days</option>
          </select>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-gray-200">
        {[
          { id: 'overview', label: 'Overview', icon: Activity },
          { id: 'sessions', label: 'Sessions', icon: MessageSquare },
          { id: 'commands', label: 'Commands', icon: Zap },
          { id: 'settings', label: 'Settings', icon: Settings },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              'flex items-center gap-2 px-4 py-2 border-b-2 text-sm font-medium transition-colors',
              activeTab === tab.id
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            )}
          >
            <tab.icon size={16} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="space-y-5">
          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
            <StatCard
              icon={<MessageSquare size={20} />}
              value={summary.total_sessions || 0}
              label="Total Sessions"
              accentColor="blue"
              className="rounded-xl border border-gray-200 bg-white shadow-card"
            />
            <StatCard
              icon={<Zap size={20} />}
              value={summary.total_commands || 0}
              label="Total Commands"
              accentColor="purple"
              className="rounded-xl border border-gray-200 bg-white shadow-card"
            />
            <StatCard
              icon={<Clock size={20} />}
              value={`${summary.avg_latency_ms || 0}ms`}
              label="Avg Latency"
              accentColor="green"
              className="rounded-xl border border-gray-200 bg-white shadow-card"
            />
            <StatCard
              icon={<CheckCircle size={20} />}
              value={`${Math.round((summary.success_rate || 0) * 100)}%`}
              label="Success Rate"
              accentColor="orange"
              className="rounded-xl border border-gray-200 bg-white shadow-card"
            />
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Daily Activity */}
            <Card className="overflow-hidden">
              <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
                <div className="flex items-center gap-2">
                  <BarChart3 size={15} className="text-blue-500" />
                  <h3 className="text-sm font-semibold text-gray-900">Daily Activity</h3>
                </div>
              </div>
              <div className="p-5">
                {daily.length > 0 ? (
                  <div className="space-y-3">
                    {daily.slice(0, 7).map((day, i) => {
                      const maxCommands = Math.max(...daily.map((d) => d.commands || 0), 1)
                      const pct = Math.round(((day.commands || 0) / maxCommands) * 100)
                      return (
                        <div key={i}>
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="text-sm text-gray-700">{day.date}</span>
                            <span className="text-sm font-bold text-gray-900">{day.commands} cmds</span>
                          </div>
                          <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                            <div
                              className="h-full rounded-full bg-blue-500 transition-all duration-700"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <p className="text-sm text-gray-400 text-center py-6">No activity data yet</p>
                )}
              </div>
            </Card>

            {/* Recent Sessions */}
            <Card className="overflow-hidden">
              <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
                <div className="flex items-center gap-2">
                  <MessageSquare size={15} className="text-purple-500" />
                  <h3 className="text-sm font-semibold text-gray-900">Recent Sessions</h3>
                </div>
              </div>
              <div className="p-5">
                {sessions.length > 0 ? (
                  <div className="space-y-3">
                    {sessions.slice(0, 5).map((session) => (
                      <div
                        key={session.session_id}
                        className="flex items-center justify-between p-3 rounded-lg border border-gray-100 hover:border-gray-200 transition-colors"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-gray-900 truncate">
                              {formatDate(session.started_at)}
                            </span>
                            <Badge color={session.status === 'active' ? 'green' : 'gray'} size="sm">
                              {session.status}
                            </Badge>
                          </div>
                          <p className="text-xs text-gray-500 mt-1">
                            {session.total_turns || 0} turns · {formatDuration(session.duration_seconds)}
                          </p>
                        </div>
                        <button
                          onClick={() => handleViewSession(session.session_id)}
                          className="ml-2 p-2 rounded-lg hover:bg-gray-100 transition-colors"
                        >
                          <Eye size={16} className="text-gray-400" />
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-gray-400 text-center py-6">No sessions yet</p>
                )}
              </div>
            </Card>
          </div>

          {/* Service Status */}
          <Card>
            <div className="px-5 py-4 border-b border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900">Service Status</h3>
            </div>
            <div className="p-5">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {Object.entries(status.services || {}).map(([service, serviceStatus]) => (
                  <div key={service} className="flex items-center gap-3 p-3 rounded-lg border border-gray-100">
                    <div
                      className={cn(
                        'w-3 h-3 rounded-full',
                        serviceStatus === 'available' || serviceStatus.includes('lab') || serviceStatus.includes('gram')
                          ? 'bg-green-500'
                          : serviceStatus === 'fallback'
                          ? 'bg-yellow-500'
                          : 'bg-red-500'
                      )}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 capitalize">{service.replace('_', ' ')}</p>
                      <p className="text-xs text-gray-500 capitalize">{serviceStatus}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Sessions Tab */}
      {activeTab === 'sessions' && (
        <div className="space-y-4">
          {sessions.length > 0 ? (
            sessions.map((session) => (
              <Card key={session.session_id} className="overflow-hidden">
                <div className="p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-sm font-semibold text-gray-900">
                          {formatDate(session.started_at)}
                        </span>
                        <Badge color={session.status === 'active' ? 'green' : 'gray'} size="sm">
                          {session.status}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-4 text-xs text-gray-500">
                        <span className="flex items-center gap-1">
                          <MessageSquare size={12} />
                          {session.total_turns || 0} turns
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock size={12} />
                          {formatDuration(session.duration_seconds)}
                        </span>
                        {session.wake_word_detected > 0 && (
                          <span className="flex items-center gap-1">
                            <Volume2 size={12} />
                            Wake word
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleViewSession(session.session_id)}
                        className="px-3 py-1.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 text-xs font-medium text-gray-700 transition-colors"
                      >
                        View
                      </button>
                      <button
                        onClick={() => handleDeleteSession(session.session_id)}
                        className="p-1.5 rounded-lg hover:bg-red-50 text-red-500 transition-colors"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>

                  {/* Session Details (Expanded) */}
                  {selectedSession === session.session_id && sessionDetails && (
                    <div className="mt-4 pt-4 border-t border-gray-100">
                      {/* Conversation */}
                      {sessionDetails.conversation && sessionDetails.conversation.length > 0 && (
                        <div className="mb-4">
                          <h4 className="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider">
                            Conversation
                          </h4>
                          <div className="space-y-2 max-h-64 overflow-y-auto">
                            {sessionDetails.conversation.map((msg, i) => (
                              <div
                                key={i}
                                className={cn(
                                  'flex gap-2 text-sm',
                                  msg.role === 'user' ? 'justify-end' : 'justify-start'
                                )}
                              >
                                {msg.role === 'assistant' && (
                                  <div className="w-6 h-6 rounded-full bg-blue-500 text-white flex items-center justify-center text-xs font-bold flex-shrink-0">
                                    O
                                  </div>
                                )}
                                <div
                                  className={cn(
                                    'max-w-[75%] rounded-lg px-3 py-2',
                                    msg.role === 'user'
                                      ? 'bg-blue-500 text-white'
                                      : 'bg-gray-100 text-gray-900'
                                  )}
                                >
                                  {msg.content}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Commands */}
                      {sessionDetails.commands && sessionDetails.commands.length > 0 && (
                        <div>
                          <h4 className="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider">
                            Commands Executed
                          </h4>
                          <div className="space-y-2">
                            {sessionDetails.commands.map((cmd, i) => (
                              <div key={i} className="flex items-start gap-2 text-xs p-2 rounded bg-gray-50">
                                <div className="flex-1">
                                  <p className="font-medium text-gray-900">{cmd.command_text}</p>
                                  {cmd.function_called && (
                                    <p className="text-gray-500 mt-1">
                                      Function: <code className="text-purple-600">{cmd.function_called}()</code>
                                    </p>
                                  )}
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="text-gray-400">{cmd.latency_ms}ms</span>
                                  {cmd.success ? (
                                    <CheckCircle size={14} className="text-green-500" />
                                  ) : (
                                    <XCircle size={14} className="text-red-500" />
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </Card>
            ))
          ) : (
            <Card className="p-12 text-center">
              <MessageSquare size={48} className="mx-auto text-gray-300 mb-4" />
              <p className="text-gray-500">No sessions yet. Start using OTIS to see your history here.</p>
            </Card>
          )}
        </div>
      )}

      {/* Commands Tab */}
      {activeTab === 'commands' && (
        <Card>
          <div className="px-5 py-4 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900">Command History</h3>
          </div>
          <div className="divide-y divide-gray-100">
            {commands.length > 0 ? (
              commands.map((cmd, i) => (
                <div key={i} className="p-4 hover:bg-gray-50 transition-colors">
                  <div className="flex items-start gap-3">
                    <div className={cn(
                      'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
                      cmd.success ? 'bg-green-100' : 'bg-red-100'
                    )}>
                      {cmd.success ? (
                        <CheckCircle size={16} className="text-green-600" />
                      ) : (
                        <XCircle size={16} className="text-red-600" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 mb-1">{cmd.command_text}</p>
                      <div className="flex items-center gap-3 text-xs text-gray-500">
                        <span>{formatDate(cmd.created_at)}</span>
                        {cmd.function_called && (
                          <span className="flex items-center gap-1">
                            <Zap size={12} />
                            {cmd.function_called}()
                          </span>
                        )}
                        <span className="flex items-center gap-1">
                          <Clock size={12} />
                          {cmd.latency_ms}ms
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="p-12 text-center">
                <Zap size={48} className="mx-auto text-gray-300 mb-4" />
                <p className="text-gray-500">No commands executed yet</p>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Settings Tab */}
      {activeTab === 'settings' && (
        <Card>
          <div className="px-5 py-4 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900">Voice Settings</h3>
          </div>
          <div className="p-5 space-y-4">
            {settings ? (
              <>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">Voice Speed</label>
                  <input
                    type="range"
                    min="0.5"
                    max="2"
                    step="0.1"
                    value={settings.voice_speed || 1.0}
                    onChange={(e) => setSettings({ ...settings, voice_speed: parseFloat(e.target.value) })}
                    disabled={!settingsEditing}
                    className="w-full"
                  />
                  <div className="flex justify-between text-xs text-gray-500 mt-1">
                    <span>0.5x</span>
                    <span>{settings.voice_speed || 1.0}x</span>
                    <span>2.0x</span>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">Voice Pitch</label>
                  <input
                    type="range"
                    min="-1"
                    max="1"
                    step="0.1"
                    value={settings.voice_pitch || 0.0}
                    onChange={(e) => setSettings({ ...settings, voice_pitch: parseFloat(e.target.value) })}
                    disabled={!settingsEditing}
                    className="w-full"
                  />
                  <div className="flex justify-between text-xs text-gray-500 mt-1">
                    <span>Lower</span>
                    <span>{settings.voice_pitch || 0.0}</span>
                    <span>Higher</span>
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <label className="text-sm font-medium text-gray-700">Auto Listen</label>
                    <p className="text-xs text-gray-500 mt-1">Automatically start listening after wake word</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.auto_listen !== false}
                      onChange={(e) => setSettings({ ...settings, auto_listen: e.target.checked })}
                      disabled={!settingsEditing}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                  </label>
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <label className="text-sm font-medium text-gray-700">Confirm Actions</label>
                    <p className="text-xs text-gray-500 mt-1">Ask for confirmation before executing actions</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.confirm_actions !== false}
                      onChange={(e) => setSettings({ ...settings, confirm_actions: e.target.checked })}
                      disabled={!settingsEditing}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                  </label>
                </div>

                <div className="flex gap-2 pt-4">
                  {settingsEditing ? (
                    <>
                      <Button
                        onClick={() => handleUpdateSettings(settings)}
                        className="flex-1"
                      >
                        Save Changes
                      </Button>
                      <Button
                        onClick={() => {
                          setSettingsEditing(false)
                          loadData()
                        }}
                        variant="outline"
                        className="flex-1"
                      >
                        Cancel
                      </Button>
                    </>
                  ) : (
                    <Button
                      onClick={() => setSettingsEditing(true)}
                      className="w-full"
                    >
                      Edit Settings
                    </Button>
                  )}
                </div>
              </>
            ) : (
              <p className="text-sm text-gray-500 text-center py-6">Loading settings...</p>
            )}
          </div>
        </Card>
      )}
    </div>
  )
}
