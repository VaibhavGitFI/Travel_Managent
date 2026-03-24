import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Send, Copy, RefreshCw, Check, Square,
  MapPin, CloudSun, Plane, Mic, Paperclip, X, Phone, Plus,
  Hotel, ArrowRight, Brain, Zap, Globe, Shield,
  PanelRightOpen, PanelRightClose, MessageSquare, Trash2,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { sendMessage, getChatHistory, sendStreamingMessage, transcribeAudio, listSessions, createSession, deleteSession } from '../api/chat'
import useStore from '../store/useStore'
import Spinner from '../components/ui/Spinner'
import { format } from 'date-fns'
import { cn } from '../lib/cn'

const ROUTE_MAP = {
  planner: '/planner', hotels: '/accommodation', expenses: '/expenses',
  meetings: '/meetings', requests: '/requests', approvals: '/approvals',
  analytics: '/analytics', dashboard: '/dashboard', chat: '/chat',
}

const SUGGESTIONS = [
  { icon: Plane,    text: 'Plan a business trip from Delhi to Mumbai next week', tag: 'Trip Planning' },
  { icon: CloudSun, text: 'What is the weather in Bangalore for the next 3 days?', tag: 'Weather' },
  { icon: MapPin,   text: 'Find hotels near Hyderabad city center under ₹8000', tag: 'Hotels' },
  { icon: Hotel,    text: 'Compare train vs flight for Chennai to Pune', tag: 'Compare' },
]

const AUDIO_MIME_TYPES = [
  'audio/webm;codecs=opus', 'audio/webm',
  'audio/ogg;codecs=opus', 'audio/ogg', 'audio/mp4',
]

function getSupportedMimeType() {
  if (typeof MediaRecorder === 'undefined') return null
  for (const mime of AUDIO_MIME_TYPES) {
    if (MediaRecorder.isTypeSupported(mime)) return mime
  }
  return null
}

const MAX_INPUT = 1600
const MAX_FILE  = 20 * 1024 * 1024

/* ═══════════════════════════════════════════════════════
   Main Chat Component
   ═══════════════════════════════════════════════════════ */

export default function Chat() {
  const { auth, theme } = useStore()
  const dark = theme === 'dark'
  const navigate = useNavigate()

  // Session state (server-driven)
  const [sessions, setSessions]               = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [sessionsLoading, setSessionsLoading] = useState(true)

  // Message state
  const [messages, setMessages]       = useState([])
  const [input, setInput]             = useState('')
  const [loading, setLoading]         = useState(false)
  const [histLoading, setHistLoading] = useState(false)
  const [selectedFile, setSelectedFile] = useState(null)
  const [listening, setListening]     = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [copiedId, setCopiedId]       = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const bottomRef    = useRef(null)
  const inputRef     = useRef(null)
  const fileInputRef = useRef(null)
  const mediaRecRef  = useRef(null)
  const chunksRef    = useRef([])
  const silenceRef   = useRef(null)
  const analyserRef  = useRef(null)
  const animFrameRef = useRef(null)
  const sendMsgRef   = useRef(null)

  const userInitial     = auth.user?.name?.charAt(0)?.toUpperCase() || 'U'
  const canSend         = !loading && (input.trim().length > 0 || Boolean(selectedFile))
  const lastAssistantId = [...messages].reverse().find(m => m.role === 'assistant')?.id
  const lastUserPrompt  = getLastUserPrompt(messages)

  // Load sessions on mount
  useEffect(() => {
    loadSessions()
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])
  useEffect(() => () => {
    mediaRecRef.current?.stop?.()
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
  }, [])

  const loadSessions = async () => {
    try {
      const data = await listSessions()
      const sess = data.sessions || []
      setSessions(sess)
      if (sess.length > 0) {
        const latest = sess[0]
        setActiveSessionId(latest.id)
        await loadHistory(latest.id)
      }
    } catch {}
    finally { setSessionsLoading(false) }
  }

  const loadHistory = async (sessionId) => {
    if (!sessionId) return
    setHistLoading(true)
    try {
      const data = await getChatHistory(sessionId)
      const history = Array.isArray(data) ? data : data.messages || []
      setMessages(history.map(m => ({
        id: m.id || Date.now() + Math.random(),
        role: m.role || (m.is_bot ? 'assistant' : 'user'),
        content: m.content || m.message || m.text,
        // Backend stores UTC timestamps without 'Z' suffix — append it for correct local parsing
        time: m.created_at ? (m.created_at.endsWith('Z') ? m.created_at : m.created_at + 'Z') : new Date().toISOString(),
        action_cards: m.action_cards || [],
      })))
    } catch {}
    finally { setHistLoading(false) }
  }

  const switchSession = async (sessionId) => {
    if (sessionId === activeSessionId) return
    setActiveSessionId(sessionId)
    await loadHistory(sessionId)
  }

  const handleDeleteSession = async (sessionId, e) => {
    e.stopPropagation()
    try {
      await deleteSession(sessionId)
      setSessions(prev => prev.filter(s => s.id !== sessionId))
      if (activeSessionId === sessionId) {
        const remaining = sessions.filter(s => s.id !== sessionId)
        if (remaining.length > 0) {
          setActiveSessionId(remaining[0].id)
          await loadHistory(remaining[0].id)
        } else {
          setActiveSessionId(null)
          setMessages([])
        }
      }
    } catch { toast.error('Failed to delete conversation') }
  }

  const stopRecording = useCallback(() => {
    if (animFrameRef.current) { cancelAnimationFrame(animFrameRef.current); animFrameRef.current = null }
    if (silenceRef.current) { clearTimeout(silenceRef.current); silenceRef.current = null }
    mediaRecRef.current?.stop?.()
  }, [])

  const toggleVoice = async () => {
    if (listening) { stopRecording(); return }
    const mimeType = getSupportedMimeType()
    if (!mimeType) { toast.error('Voice not supported in this browser.'); return }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      chunksRef.current = []
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)()
      const source = audioCtx.createMediaStreamSource(stream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 512
      analyser.smoothingTimeConstant = 0.3
      source.connect(analyser)
      analyserRef.current = { audioCtx, analyser }

      const recorder = new MediaRecorder(stream, { mimeType })
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }

      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        audioCtx.close().catch(() => {})
        if (animFrameRef.current) { cancelAnimationFrame(animFrameRef.current); animFrameRef.current = null }
        if (silenceRef.current) { clearTimeout(silenceRef.current); silenceRef.current = null }
        setListening(false)

        const blob = new Blob(chunksRef.current, { type: mimeType })
        if (blob.size < 500) { toast.error('Too short — try again'); return }

        setTranscribing(true)
        try {
          const result = await transcribeAudio(blob)
          if (result.success && result.text) {
            const finalText = result.text.slice(0, MAX_INPUT)
            setInput(finalText)
            if (inputRef.current) autoResize(inputRef.current)
            // Auto-send after short delay so user sees what was transcribed
            setTimeout(() => sendMsgRef.current?.(finalText), 400)
          } else { toast.error(result.error || 'Could not transcribe') }
        } catch { toast.error('Transcription failed') }
        finally { setTranscribing(false) }
      }

      recorder.onerror = () => {
        stream.getTracks().forEach(t => t.stop())
        audioCtx.close().catch(() => {})
        setListening(false)
        toast.error('Recording failed')
      }

      mediaRecRef.current = recorder
      recorder.start(250)
      setListening(true)

      // Silence detection
      const dataArr = new Uint8Array(analyser.frequencyBinCount)
      let silentSince = 0
      const startedAt = Date.now()
      const checkSilence = () => {
        if (!mediaRecRef.current || mediaRecRef.current.state !== 'recording') return
        if (Date.now() - startedAt > 60000) { stopRecording(); return }
        analyser.getByteFrequencyData(dataArr)
        const avg = dataArr.reduce((sum, v) => sum + v, 0) / dataArr.length
        if (avg < 15) {
          if (!silentSince) silentSince = Date.now()
          else if (Date.now() - silentSince > 1800) { stopRecording(); return }
        } else { silentSince = 0 }
        animFrameRef.current = requestAnimationFrame(checkSilence)
      }
      setTimeout(() => { animFrameRef.current = requestAnimationFrame(checkSilence) }, 1000)
    } catch (err) {
      toast.error(err.name === 'NotAllowedError' ? 'Mic access denied' : 'Could not access microphone')
    }
  }

  const handleFile = (e) => {
    const f = e.target.files?.[0]
    if (!f) return
    if (f.size > MAX_FILE) { toast.error('Max 20 MB'); e.target.value = ''; return }
    setSelectedFile(f)
  }
  const removeFile = () => { setSelectedFile(null); if (fileInputRef.current) fileInputRef.current.value = '' }

  const sendMsg = useCallback(async (text) => {
    const content = (typeof text === 'string' ? text : input).trim()
    if ((!content && !selectedFile) || loading) return
    const pendingFile = selectedFile

    // Auto-create session if none active
    let sid = activeSessionId
    if (!sid) {
      try {
        const res = await createSession()
        sid = res.session.id
        setSessions(prev => [res.session, ...prev])
        setActiveSessionId(sid)
      } catch {
        sid = null
      }
    }

    const userMsg = {
      id: Date.now(), role: 'user',
      content: pendingFile ? [content, `[Attachment: ${pendingFile.name}]`].filter(Boolean).join('\n') : content,
      time: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMsg]); setLoading(true); setInput('')
    if (inputRef.current) inputRef.current.style.height = 'auto'

    if (pendingFile) {
      try {
        const data = await sendMessage(content, { user: auth.user?.name }, pendingFile, sid)
        removeFile()
        if (data.session_id && !sid) {
          sid = data.session_id
          setActiveSessionId(sid)
        }
        setMessages(prev => [...prev, {
          id: Date.now() + 1, role: 'assistant',
          content: data.reply || data.message || data.response || 'Sorry, I could not process that.',
          time: new Date().toISOString(), action_cards: data.action_cards || [], trip_results: data.trip_results || null,
        }])
        // Refresh sessions list to get auto-generated title
        listSessions().then(d => setSessions(d.sessions || [])).catch(() => {})
      } catch {
        setMessages(prev => [...prev, { id: Date.now() + 1, role: 'assistant', content: 'Sorry, I encountered an error.', time: new Date().toISOString(), error: true }])
      } finally { setLoading(false); inputRef.current?.focus() }
      return
    }

    const streamId = Date.now() + 1
    setMessages(prev => [...prev, { id: streamId, role: 'assistant', content: '', time: new Date().toISOString(), streaming: true, action_cards: [] }])
    try {
      await sendStreamingMessage(
        content, { user: auth.user?.name },
        (token) => setMessages(prev => prev.map(m => m.id === streamId ? { ...m, content: m.content + token } : m)),
        (meta) => {
          setMessages(prev => prev.map(m => m.id === streamId
            ? { ...m, streaming: false, action_cards: meta.action_cards || [], ai_powered: meta.ai_powered, trip_results: meta.trip_results || null }
            : m))
          // Update session ID if returned and refresh session titles
          if (meta.session_id && !activeSessionId) {
            setActiveSessionId(meta.session_id)
          }
          listSessions().then(d => setSessions(d.sessions || [])).catch(() => {})
        },
        sid,
      )
    } catch {
      setMessages(prev => prev.map(m => m.id === streamId
        ? { ...m, streaming: false, content: m.content || 'Sorry, I encountered an error.', error: !m.content }
        : m))
    } finally { setLoading(false); inputRef.current?.focus() }
  }, [input, selectedFile, loading, auth.user, activeSessionId])
  sendMsgRef.current = sendMsg

  const handleKeyDown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg() } }
  const copyMsg = (id, c) => { navigator.clipboard.writeText(c); setCopiedId(id); setTimeout(() => setCopiedId(null), 2000) }
  const regenerate = () => { if (!lastUserPrompt || loading) return; sendMsg(lastUserPrompt) }

  const startNew = () => {
    // Clear active session — a new one will be auto-created on first message
    setActiveSessionId(null)
    setMessages([])
    setInput('')
    removeFile()
    if (inputRef.current) inputRef.current.style.height = 'auto'
    inputRef.current?.focus()
  }
  const handleAction = (card) => {
    if (card.action === 'openTab') navigate(ROUTE_MAP[card.target] || '/')
    else if (card.action === 'openSOS') toast('Emergency: Ambulance 108 · Police 100 · Fire 101 · General 112', { duration: 12000 })
    else if (card.action === 'tel' && card.target) window.location.href = `tel:${card.target}`
  }

  // Theme classes — dark uses brand navy palette for depth
  const t = {
    root: dark ? 'bg-navy-900 text-brand-light' : 'bg-white text-gray-900',
    header: dark ? 'border-navy-700/50 bg-navy-950' : 'border-gray-100 bg-white',
    headerText: dark ? 'text-brand-light' : 'text-gray-900',
    headerSub: dark ? 'text-brand-muted' : 'text-gray-400',
    headerBtn: dark ? 'border-navy-700 text-brand-muted hover:bg-navy-800 hover:text-brand-light' : 'border-gray-200 text-gray-600 hover:bg-gray-50',
    msgArea: dark ? 'bg-navy-900' : 'bg-gray-50/30',
    inputWrap: dark ? 'bg-navy-900' : 'bg-white',
    inputBox: dark
      ? 'border-navy-600 bg-navy-800 text-brand-light placeholder:text-brand-muted/60 focus-within:border-brand-cyan/40 focus-within:shadow-[0_0_0_1px_rgba(76,201,240,0.15)]'
      : 'border-gray-300 bg-white text-gray-900 placeholder:text-gray-400 focus-within:border-gray-400 focus-within:shadow-md',
    inputText: dark ? 'text-brand-light placeholder:text-brand-muted/60' : 'text-gray-900 placeholder:text-gray-400',
    iconBtn: dark ? 'text-brand-muted hover:text-brand-cyan hover:bg-navy-700' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100',
    sendBtn: dark ? 'bg-brand-cyan text-navy-950 hover:bg-brand-cyan/80' : 'bg-gray-900 text-white hover:bg-gray-700',
    sidebar: dark ? 'bg-navy-950 border-navy-700/50' : 'bg-gray-50 border-gray-200',
    sideItem: dark ? 'text-brand-muted hover:bg-navy-800 hover:text-brand-light' : 'text-gray-700 hover:bg-gray-100',
    sideItemActive: dark ? 'bg-navy-800 text-brand-cyan' : 'bg-blue-50 text-blue-700',
    userBubble: dark ? 'bg-accent-700/80 text-white' : 'bg-gradient-to-br from-brand-dark to-[#1a2744] text-white',
    aiBubble: dark ? 'bg-navy-800 border-navy-700 text-gray-200' : 'bg-white border-gray-100 text-gray-800',
    errBubble: dark ? 'bg-red-900/20 border-red-700/40 text-red-300' : 'border-red-200 bg-red-50 text-red-700',
    label: dark ? 'text-brand-muted' : 'text-gray-400',
    time: dark ? 'text-navy-400' : 'text-gray-400',
    file: dark ? 'border-navy-700 bg-navy-800 text-brand-muted' : 'border-gray-200 bg-gray-50 text-gray-600',
  }

  return (
    <div className={cn('flex h-[calc(100dvh-88px)] min-h-[400px] rounded-2xl overflow-hidden border shadow-card', dark ? 'border-navy-700/50' : 'border-gray-200', t.root)}>

      {/* ── Main chat area ──────────────────────────────── */}
      <div className="flex flex-1 flex-col min-w-0">

        {/* Header */}
        <div className={cn('flex items-center justify-between px-4 py-2.5 border-b shrink-0', t.header)}>
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-dark to-brand-mid">
              <Brain size={15} className="text-brand-cyan" />
            </div>
            <div>
              <p className={cn('text-sm font-semibold leading-tight', t.headerText)}>TravelSync AI</p>
              <div className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
                <span className={cn('text-[10px]', t.headerSub)}>Online</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button onClick={startNew}
              className={cn('flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors', t.headerBtn)}>
              <Plus size={11} /> New
            </button>
            <button onClick={() => setSidebarOpen(v => !v)}
              className={cn('flex h-8 w-8 items-center justify-center rounded-lg transition-colors', t.headerBtn)} title="Chat history">
              {sidebarOpen ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className={cn('flex-1 overflow-y-auto px-4 py-4 space-y-4', t.msgArea)}>
          {(histLoading || sessionsLoading) ? (
            <div className="space-y-4 py-4">
              {[false, true, false].map((u, i) => (
                <div key={i} className={cn('flex gap-3', u && 'flex-row-reverse')}>
                  <div className={cn('h-7 w-7 rounded-full shrink-0 animate-pulse', dark ? 'bg-navy-700' : 'bg-gray-100')} />
                  <div className={cn('h-10 rounded-2xl animate-pulse', dark ? 'bg-navy-700' : 'bg-gray-100', u ? 'w-40' : 'w-64')} />
                </div>
              ))}
            </div>
          ) : messages.length === 0 ? (
            <WelcomeScreen onSuggest={sendMsg} userName={auth.user?.name?.split(' ')[0]} dark={dark} />
          ) : (
            <div className="mx-auto max-w-3xl space-y-4">
              {messages.map(msg => (
                <MessageBubble
                  key={msg.id} message={msg} dark={dark} t={t}
                  onCopy={() => copyMsg(msg.id, msg.content)}
                  copied={copiedId === msg.id}
                  onRegenerate={regenerate}
                  onAction={handleAction}
                  isLastAssistant={msg.role === 'assistant' && msg.id === lastAssistantId}
                  userInitial={userInitial}
                  navigate={navigate}
                />
              ))}
            </div>
          )}
          {loading && !messages.some(m => m.streaming) && <div className="mx-auto max-w-3xl"><TypingBubble dark={dark} /></div>}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className={cn('shrink-0 px-3 pb-3 pt-2', t.inputWrap)}>
          <div className="mx-auto max-w-3xl">
            {selectedFile && (
              <div className={cn('mb-1.5 flex items-center gap-2 rounded-lg border px-2.5 py-1 text-xs', t.file)}>
                <Paperclip size={11} className="opacity-50" />
                <span className="truncate">{selectedFile.name}</span>
                <span className="shrink-0 opacity-50">{fmtSize(selectedFile.size)}</span>
                <button onClick={removeFile} className="ml-auto rounded p-0.5 hover:opacity-70"><X size={10} /></button>
              </div>
            )}

            <div className={cn(
              'flex items-center gap-1.5 rounded-full border px-3 py-1.5 transition-all shadow-sm',
              listening && 'border-red-400 shadow-red-100/50',
              t.inputBox,
            )}>
              <input ref={fileInputRef} type="file" accept=".png,.jpg,.jpeg,.pdf,.txt,.csv,.json" className="hidden" onChange={handleFile} />
              <button onClick={() => fileInputRef.current?.click()}
                className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition-colors', t.iconBtn)} aria-label="Attach">
                <Paperclip size={15} />
              </button>

              <textarea ref={inputRef} rows={1} maxLength={MAX_INPUT}
                placeholder={listening ? 'Listening... speak now' : 'Message TravelSync AI'}
                value={input} onChange={e => { setInput(e.target.value); autoResize(e.target) }}
                onKeyDown={handleKeyDown} disabled={loading || listening}
                className={cn('flex-1 min-w-0 resize-none overflow-hidden border-0 bg-transparent py-1 text-sm leading-snug focus:outline-none focus:ring-0 disabled:opacity-50', t.inputText)}
                style={{ minHeight: '24px', maxHeight: '120px' }} />

              {transcribing ? (
                <div className="flex h-7 w-7 shrink-0 items-center justify-center">
                  <Spinner size="xs" color={dark ? 'white' : 'accent'} />
                </div>
              ) : listening ? (
                <button onClick={stopRecording}
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-red-500 text-white hover:bg-red-600 transition-colors animate-pulse" aria-label="Stop">
                  <Square size={10} fill="currentColor" />
                </button>
              ) : canSend ? (
                <button onClick={() => sendMsg()} disabled={loading}
                  className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition-colors', t.sendBtn)} aria-label="Send">
                  {loading ? <Spinner size="xs" color={dark ? 'dark' : 'white'} /> : <Send size={13} />}
                </button>
              ) : (
                <button onClick={toggleVoice}
                  className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition-colors', t.iconBtn)} aria-label="Voice">
                  <Mic size={15} />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── History Sidebar (right) ────────────────────── */}
      {sidebarOpen && (
        <div className={cn('w-64 shrink-0 border-l flex flex-col', t.sidebar)}>
          <div className={cn('flex items-center justify-between px-3 py-2.5 border-b', dark ? 'border-navy-700/50' : 'border-gray-200')}>
            <span className={cn('text-xs font-semibold', t.headerText)}>Conversations</span>
            <button onClick={() => setSidebarOpen(false)} className={cn('rounded p-1 transition-colors', t.iconBtn)}>
              <X size={12} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto py-1">
            {sessions.length === 0 ? (
              <p className={cn('text-xs text-center py-8', t.headerSub)}>No conversations yet</p>
            ) : (
              sessions.map(s => (
                <div key={s.id} onClick={() => switchSession(s.id)}
                  className={cn('flex items-start gap-2 px-3 py-2 mx-1 rounded-lg cursor-pointer transition-colors group',
                    s.id === activeSessionId ? t.sideItemActive : t.sideItem)}>
                  <MessageSquare size={13} className="mt-0.5 shrink-0 opacity-50" />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium truncate">{s.title || 'New Chat'}</p>
                    <p className={cn('text-[10px] mt-0.5', t.headerSub)}>
                      {(() => { try { const ts = s.updated_at || s.created_at; const d = new Date(ts?.endsWith?.('Z') ? ts : ts + 'Z'); return format(d, 'MMM d, h:mm a') } catch { return '' } })()}
                    </p>
                  </div>
                  <button onClick={(e) => handleDeleteSession(s.id, e)}
                    className="opacity-0 group-hover:opacity-100 rounded p-0.5 hover:bg-red-100 hover:text-red-500 transition-all">
                    <Trash2 size={10} />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Welcome Screen ──────────────────────────────────── */

function WelcomeScreen({ onSuggest, userName, dark }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 animate-fade-in mx-auto max-w-2xl">
      <div className="relative mb-4">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-dark to-brand-mid shadow-lg">
          <Brain size={24} className="text-brand-cyan" />
        </div>
        <div className="absolute -top-0.5 -right-0.5 h-3.5 w-3.5 rounded-full bg-green-400 border-2 border-white" />
      </div>

      <h3 className={cn('text-lg font-bold', dark ? 'text-brand-light' : 'text-gray-900')}>
        {userName ? `Hi ${userName}, how can I help?` : 'How can I help you today?'}
      </h3>
      <p className={cn('mt-1 max-w-md text-center text-sm', dark ? 'text-brand-muted' : 'text-gray-500')}>
        Plan trips, find flights & hotels, check weather, manage expenses, and more.
      </p>

      <div className="mt-4 flex flex-wrap justify-center gap-1.5">
        {[
          { icon: Plane, label: 'Flights' }, { icon: Hotel, label: 'Hotels' },
          { icon: CloudSun, label: 'Weather' }, { icon: Shield, label: 'Policy' },
          { icon: Globe, label: 'Multilingual' }, { icon: Zap, label: 'Real-time' },
        ].map((c) => (
          <span key={c.label} className={cn('flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-medium',
            dark ? 'border-navy-700 bg-navy-800 text-brand-muted' : 'border-gray-200 bg-white text-gray-600')}>
            <c.icon size={10} className={dark ? 'text-brand-cyan/50' : 'opacity-50'} /> {c.label}
          </span>
        ))}
      </div>

      <div className="mt-5 grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map(s => (
          <button key={s.text} onClick={() => onSuggest(s.text)}
            className={cn('group flex items-start gap-2.5 rounded-xl border p-3 text-left transition-all hover:shadow-md',
              dark ? 'border-navy-700 bg-navy-800 hover:border-brand-cyan/30' : 'border-gray-200 bg-white hover:border-blue-200')}>
            <div className={cn('mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border transition-all',
              dark ? 'border-navy-600 bg-navy-700 group-hover:bg-brand-cyan/20 group-hover:border-brand-cyan/40' : 'border-gray-100 bg-gray-50 group-hover:bg-gradient-to-br group-hover:from-blue-500 group-hover:to-cyan-500 group-hover:border-transparent')}>
              <s.icon size={12} className={cn(dark ? 'text-brand-muted group-hover:text-brand-cyan' : 'text-gray-400 group-hover:text-white')} />
            </div>
            <div className="min-w-0">
              <span className={cn('text-[9px] font-semibold uppercase tracking-wide', dark ? 'text-brand-muted group-hover:text-brand-cyan' : 'text-gray-400 group-hover:text-blue-500')}>{s.tag}</span>
              <p className={cn('text-xs leading-snug mt-0.5', dark ? 'text-navy-200' : 'text-gray-700')}>{s.text}</p>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

/* ── Message Bubble ──────────────────────────────────── */

function MessageBubble({ message: msg, onCopy, copied, onRegenerate, onAction, isLastAssistant, userInitial, navigate, dark, t }) {
  const isUser = msg.role === 'user'
  const cards  = (!isUser && Array.isArray(msg.action_cards)) ? msg.action_cards : []
  const parsedDate = msg.time ? new Date(msg.time) : null
  const time = parsedDate && !Number.isNaN(parsedDate.getTime()) ? format(parsedDate, 'h:mm a') : ''

  return (
    <div className={cn('group flex gap-2.5', isUser && 'flex-row-reverse', 'animate-fade-in')}>
      <div className={cn('mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-bold',
        isUser
          ? 'bg-gradient-to-br from-blue-500 to-cyan-500 text-white'
          : dark ? 'bg-[#2f2f2f] border border-[#444] text-gray-400' : 'bg-white border border-gray-200 text-gray-500')}>
        {isUser ? userInitial : <Brain size={12} className="text-brand-cyan" />}
      </div>

      <div className={cn('flex min-w-0 max-w-[80%] flex-col gap-0.5', isUser ? 'items-end' : 'items-start')}>
        <span className={cn('text-[10px] font-medium px-0.5', t.label)}>
          {isUser ? 'You' : 'TravelSync AI'}
        </span>

        <div className={cn('rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed',
          isUser
            ? cn('rounded-tr-sm shadow-sm', t.userBubble)
            : msg.error
            ? cn('rounded-tl-sm', t.errBubble)
            : cn('border rounded-tl-sm shadow-sm', t.aiBubble)
        )}>
          {msg.streaming && !msg.content ? (
            <span className="flex items-center gap-1.5 py-0.5 text-xs opacity-50">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: '-0.2s' }} />
              <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: '-0.1s' }} />
              <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-bounce" />
              <span className="ml-1">Thinking...</span>
            </span>
          ) : (
            <>
              <div className={cn('chat-prose', isUser && 'chat-prose-user')}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content || ''}</ReactMarkdown>
              </div>
              {msg.streaming && <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-blue-500 align-middle" />}
            </>
          )}
        </div>

        {!isUser && msg.trip_results && <TripResultsCard results={msg.trip_results} onViewFull={() => navigate?.('/planner')} dark={dark} />}

        {cards.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-0.5">
            {cards.map((card, i) => (
              <button key={i} onClick={() => onAction?.(card)}
                className={cn('flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium transition-all',
                  card.action === 'openSOS' ? 'border-red-300 bg-red-50 text-red-600 hover:bg-red-500 hover:text-white'
                  : card.action === 'tel' ? 'border-green-300 bg-green-50 text-green-600 hover:bg-green-500 hover:text-white'
                  : dark ? 'border-[#444] bg-[#2f2f2f] text-gray-300 hover:bg-gray-600' : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-900 hover:text-white')}>
                {card.action === 'tel' && <Phone size={9} />}
                {card.label}
              </button>
            ))}
          </div>
        )}

        <div className={cn('flex items-center gap-1.5 px-0.5', isUser ? 'flex-row-reverse' : '')}>
          {time && <span className={cn('text-[10px]', t.time)}>{time}</span>}
          {!isUser && (
            <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
              <button onClick={onCopy} className={cn('rounded p-0.5 transition-colors', dark ? 'hover:bg-[#3a3a3a] text-gray-600' : 'hover:bg-gray-100 text-gray-400')} title="Copy">
                {copied ? <Check size={10} className="text-green-500" /> : <Copy size={10} />}
              </button>
              {isLastAssistant && (
                <button onClick={onRegenerate} className={cn('rounded p-0.5 transition-colors', dark ? 'hover:bg-[#3a3a3a] text-gray-600' : 'hover:bg-gray-100 text-gray-400')} title="Regenerate">
                  <RefreshCw size={10} />
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── Typing Bubble ───────────────────────────────────── */

function TypingBubble({ dark }) {
  return (
    <div className="flex gap-2.5 animate-fade-in">
      <div className={cn('mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full',
        dark ? 'bg-[#2f2f2f] border border-[#444]' : 'bg-white border border-gray-200')}>
        <Brain size={12} className="text-brand-cyan" />
      </div>
      <div>
        <span className={cn('text-[10px] font-medium px-0.5', dark ? 'text-gray-500' : 'text-gray-400')}>TravelSync AI</span>
        <div className={cn('rounded-2xl rounded-tl-sm border px-3.5 py-2.5 mt-0.5',
          dark ? 'bg-[#2f2f2f] border-[#3a3a3a]' : 'bg-white border-gray-100 shadow-sm')}>
          <span className="flex items-center gap-1.5 text-xs opacity-50">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: '-0.2s' }} />
            <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: '-0.1s' }} />
            <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-bounce" />
          </span>
        </div>
      </div>
    </div>
  )
}

/* ── Trip Results Card ───────────────────────────────── */

function TripResultsCard({ results, onViewFull, dark }) {
  if (!results) return null
  const flights = results.flights || []
  const hotels  = results.hotels  || []
  const wx      = results.weather || {}
  if (!flights.length && !hotels.length && !wx.summary) return null

  return (
    <div className={cn('mt-1 w-full max-w-sm rounded-xl border p-3.5',
      dark ? 'border-[#444] bg-[#2f2f2f]' : 'border-gray-200 bg-white shadow-sm')}>
      <div className="flex items-center gap-2 mb-2.5">
        <div className={cn('flex h-5 w-5 items-center justify-center rounded-md',
          dark ? 'bg-blue-900/30' : 'bg-blue-50 border border-blue-100')}>
          <MapPin size={10} className="text-blue-500" />
        </div>
        <p className={cn('text-sm font-semibold', dark ? 'text-gray-200' : 'text-gray-900')}>{results.destination || 'Trip Plan'}</p>
        {results.travel_dates && <span className={cn('ml-auto text-[10px]', dark ? 'text-gray-600' : 'text-gray-400')}>{results.travel_dates}</span>}
      </div>

      {flights.length > 0 && (
        <div className="mb-2">
          <p className={cn('flex items-center gap-1 text-[9px] font-semibold uppercase tracking-wide mb-1', dark ? 'text-gray-500' : 'text-gray-400')}>
            <Plane size={9} /> Flights
          </p>
          {flights.map((f, i) => (
            <div key={i} className={cn('flex justify-between rounded-lg border px-2.5 py-1.5 text-xs mb-1',
              dark ? 'bg-[#3a3a3a] border-[#444]' : 'bg-gray-50 border-gray-100')}>
              <span className={cn('truncate', dark ? 'text-gray-300' : 'text-gray-700')}>{f.airline || f.carrier} {f.flight_number || ''}</span>
              {(f.price || f.fare) && <span className={cn('font-bold ml-2 shrink-0', dark ? 'text-gray-200' : 'text-gray-900')}>
                {Number(f.price || f.fare).toLocaleString('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })}
              </span>}
            </div>
          ))}
        </div>
      )}

      {hotels.length > 0 && (
        <div className="mb-2">
          <p className={cn('flex items-center gap-1 text-[9px] font-semibold uppercase tracking-wide mb-1', dark ? 'text-gray-500' : 'text-gray-400')}>
            <Hotel size={9} /> Hotels
          </p>
          {hotels.map((h, i) => (
            <div key={i} className={cn('flex justify-between rounded-lg border px-2.5 py-1.5 text-xs mb-1',
              dark ? 'bg-[#3a3a3a] border-[#444]' : 'bg-gray-50 border-gray-100')}>
              <span className={cn('truncate', dark ? 'text-gray-300' : 'text-gray-700')}>{h.name || h.hotel_name}</span>
              {(h.price || h.price_per_night) && <span className={cn('font-bold ml-2 shrink-0', dark ? 'text-gray-200' : 'text-gray-900')}>
                {Number(h.price || h.price_per_night).toLocaleString('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })}/n
              </span>}
            </div>
          ))}
        </div>
      )}

      {wx.summary && (
        <div className="mb-2">
          <p className={cn('flex items-center gap-1 text-[9px] font-semibold uppercase tracking-wide mb-1', dark ? 'text-gray-500' : 'text-gray-400')}>
            <CloudSun size={9} /> Weather
          </p>
          <p className={cn('text-xs', dark ? 'text-gray-400' : 'text-gray-600')}>{wx.summary}</p>
        </div>
      )}

      {onViewFull && (
        <button onClick={onViewFull}
          className={cn('flex w-full items-center justify-center gap-1 rounded-lg border py-1.5 text-xs font-semibold transition-colors',
            dark ? 'bg-[#3a3a3a] border-[#444] text-gray-300 hover:bg-[#444]' : 'bg-gray-50 border-gray-200 text-gray-700 hover:bg-gray-100')}>
          View Full Plan <ArrowRight size={10} />
        </button>
      )}
    </div>
  )
}

/* ── Helpers ─────────────────────────────────────────── */

function autoResize(el) {
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 120)}px`
}

function fmtSize(b = 0) {
  if (b < 1024) return `${b} B`
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1048576).toFixed(1)} MB`
}

function getLastUserPrompt(messages) {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i]
    if (msg.role !== 'user') continue
    const clean = String(msg.content || '').split('\n').filter(l => !/^\[attachment:/i.test(l.trim())).join('\n').trim()
    if (clean) return clean
  }
  return ''
}
