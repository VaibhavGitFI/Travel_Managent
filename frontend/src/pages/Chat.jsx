import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Send, Sparkles, Copy, RefreshCw, Check,
  MapPin, CloudSun, Plane, Mic, MicOff, Paperclip, X, Phone, Plus,
  Hotel, ArrowRight, ChevronDown, Brain, Zap, Globe, Shield,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { sendMessage, getChatHistory, sendStreamingMessage, clearChatHistory } from '../api/chat'
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

const VOICE_LANGUAGES = [
  { code: 'en-IN', label: 'EN', name: 'English (India)' },
  { code: 'hi-IN', label: 'हि', name: 'Hindi' },
  { code: 'ta-IN', label: 'த',  name: 'Tamil' },
  { code: 'te-IN', label: 'తె', name: 'Telugu' },
  { code: 'kn-IN', label: 'ಕ',  name: 'Kannada' },
  { code: 'mr-IN', label: 'म',  name: 'Marathi' },
  { code: 'gu-IN', label: 'ગ',  name: 'Gujarati' },
  { code: 'bn-IN', label: 'বা', name: 'Bengali' },
  { code: 'pa-IN', label: 'ਪ',  name: 'Punjabi' },
  { code: 'en-US', label: 'US', name: 'English (US)' },
]

const MAX_INPUT = 1600
const MAX_FILE  = 20 * 1024 * 1024

export default function Chat() {
  const { auth } = useStore()
  const navigate = useNavigate()
  const [messages, setMessages]       = useState([])
  const [input, setInput]             = useState('')
  const [loading, setLoading]         = useState(false)
  const [histLoading, setHistLoading] = useState(true)
  const [selectedFile, setSelectedFile] = useState(null)
  const [listening, setListening]     = useState(false)
  const [copiedId, setCopiedId]       = useState(null)
  const [voiceLang, setVoiceLang]     = useState(
    () => VOICE_LANGUAGES.find(l => l.code.startsWith(navigator.language?.slice(0, 2))) || VOICE_LANGUAGES[0]
  )
  const [showLangPicker, setShowLangPicker] = useState(false)

  const bottomRef    = useRef(null)
  const inputRef     = useRef(null)
  const fileInputRef = useRef(null)
  const recogRef     = useRef(null)
  const langRef      = useRef(null)

  const userInitial     = auth.user?.name?.charAt(0)?.toUpperCase() || 'U'
  const canSend         = !loading && (input.trim().length > 0 || Boolean(selectedFile))
  const lastAssistantId = [...messages].reverse().find(m => m.role === 'assistant')?.id
  const lastUserPrompt  = getLastUserPrompt(messages)

  useEffect(() => { loadHistory() }, [])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])
  useEffect(() => () => { recogRef.current?.stop?.() }, [])
  useEffect(() => {
    if (!showLangPicker) return
    const h = (e) => { if (langRef.current && !langRef.current.contains(e.target)) setShowLangPicker(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [showLangPicker])

  const loadHistory = async () => {
    try {
      const data = await getChatHistory()
      const history = Array.isArray(data) ? data : data.messages || []
      if (history.length > 0) {
        setMessages(history.map(m => ({
          id: m.id || Date.now() + Math.random(),
          role: m.role || (m.is_bot ? 'assistant' : 'user'),
          content: m.content || m.message || m.text,
          time: m.created_at || m.timestamp || new Date().toISOString(),
          action_cards: m.action_cards || [],
        })))
      }
    } catch {}
    finally { setHistLoading(false) }
  }

  const toggleVoice = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) { toast.error('Voice not supported. Try Chrome or Edge.'); return }
    if (listening) { recogRef.current?.stop?.(); setListening(false); return }
    const r = new SR()
    r.lang = voiceLang.code; r.interimResults = false; r.maxAlternatives = 1
    r.onresult = (e) => {
      const t = e.results?.[0]?.[0]?.transcript?.trim()
      if (!t) return
      setInput(prev => (prev ? `${prev} ${t}` : t).slice(0, MAX_INPUT))
      if (inputRef.current) autoResize(inputRef.current)
      toast.success(`Captured in ${voiceLang.name}`)
    }
    r.onerror = (e) => { if (e.error !== 'aborted') toast.error('Voice input failed'); setListening(false) }
    r.onend = () => setListening(false)
    recogRef.current = r; r.start(); setListening(true)
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
    const userMsg = {
      id: Date.now(), role: 'user',
      content: pendingFile ? [content, `[Attachment: ${pendingFile.name}]`].filter(Boolean).join('\n') : content,
      time: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMsg]); setLoading(true); setInput('')
    if (inputRef.current) inputRef.current.style.height = '44px'

    if (pendingFile) {
      try {
        const data = await sendMessage(content, { user: auth.user?.name }, pendingFile)
        removeFile()
        setMessages(prev => [...prev, {
          id: Date.now() + 1, role: 'assistant',
          content: data.reply || data.message || data.response || 'Sorry, I could not process that.',
          time: new Date().toISOString(), action_cards: data.action_cards || [], trip_results: data.trip_results || null,
        }])
      } catch {
        setMessages(prev => [...prev, { id: Date.now() + 1, role: 'assistant', content: 'Sorry, I encountered an error. Please try again.', time: new Date().toISOString(), error: true }])
      } finally { setLoading(false); inputRef.current?.focus() }
      return
    }

    const streamId = Date.now() + 1
    setMessages(prev => [...prev, { id: streamId, role: 'assistant', content: '', time: new Date().toISOString(), streaming: true, action_cards: [] }])
    try {
      await sendStreamingMessage(
        content, { user: auth.user?.name },
        (token) => setMessages(prev => prev.map(m => m.id === streamId ? { ...m, content: m.content + token } : m)),
        ({ action_cards, ai_powered, trip_results }) =>
          setMessages(prev => prev.map(m => m.id === streamId
            ? { ...m, streaming: false, action_cards: action_cards || [], ai_powered, trip_results: trip_results || null }
            : m))
      )
    } catch {
      setMessages(prev => prev.map(m => m.id === streamId
        ? { ...m, streaming: false, content: m.content || 'Sorry, I encountered an error.', error: !m.content }
        : m))
    } finally { setLoading(false); inputRef.current?.focus() }
  }, [input, selectedFile, loading, auth.user])

  const handleKeyDown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg() } }
  const copyMsg = (id, c) => { navigator.clipboard.writeText(c); setCopiedId(id); setTimeout(() => setCopiedId(null), 2000) }
  const regenerate = () => { if (!lastUserPrompt || loading) return; sendMsg(lastUserPrompt) }
  const startNew = async () => {
    setMessages([]); setInput(''); removeFile()
    if (inputRef.current) inputRef.current.style.height = '44px'
    try { await clearChatHistory() } catch {}
  }
  const handleAction = (card) => {
    if (card.action === 'openTab') navigate(ROUTE_MAP[card.target] || '/')
    else if (card.action === 'openSOS') toast('Emergency: Ambulance 108 · Police 100 · Fire 101 · General 112', { duration: 12000 })
    else if (card.action === 'tel' && card.target) window.location.href = `tel:${card.target}`
  }

  return (
    <div className="flex flex-col h-[calc(100dvh-88px)] min-h-[400px] rounded-2xl overflow-hidden border border-gray-200 shadow-card bg-white">

      {/* ── Header ────────────────────────────────────── */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-dark to-brand-mid shadow-sm">
            <Brain size={17} className="text-brand-cyan" />
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900 leading-tight">TravelSync AI</p>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
              <span className="text-[10px] text-gray-400">Online</span>
              <span className="text-[10px] text-gray-300">|</span>
              <span className="text-[10px] text-gray-400">Flights, Hotels, Weather, Expenses</span>
            </div>
          </div>
        </div>
        <button onClick={startNew}
          className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors">
          <Plus size={12} /> New Chat
        </button>
      </div>

      {/* ── Messages ──────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-4 py-5 space-y-5 bg-gray-50/30">
        {histLoading ? (
          <div className="space-y-5 py-4">
            {[false, true, false].map((u, i) => (
              <div key={i} className={cn('flex gap-3', u && 'flex-row-reverse')}>
                <div className="h-8 w-8 rounded-full bg-gray-100 shrink-0 animate-pulse" />
                <div className={cn('h-12 rounded-2xl bg-gray-100 animate-pulse', u ? 'w-40' : 'w-64')} />
              </div>
            ))}
          </div>
        ) : messages.length === 0 ? (
          <WelcomeScreen onSuggest={sendMsg} userName={auth.user?.name?.split(' ')[0]} />
        ) : (
          messages.map(msg => (
            <MessageBubble
              key={msg.id} message={msg}
              onCopy={() => copyMsg(msg.id, msg.content)}
              copied={copiedId === msg.id}
              onRegenerate={regenerate}
              onAction={handleAction}
              isLastAssistant={msg.role === 'assistant' && msg.id === lastAssistantId}
              userInitial={userInitial}
              navigate={navigate}
            />
          ))
        )}
        {loading && !messages.some(m => m.streaming) && <TypingBubble />}
        <div ref={bottomRef} />
      </div>

      {/* ── Input Area ────────────────────────────────── */}
      <div className="shrink-0 border-t border-gray-100 bg-white px-4 pb-3 pt-3">
        {selectedFile && (
          <div className="mb-2 flex items-center gap-2 rounded-lg border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs text-blue-700">
            <Paperclip size={12} />
            <span className="truncate">{selectedFile.name}</span>
            <span className="shrink-0 text-blue-400">{fmtSize(selectedFile.size)}</span>
            <button onClick={removeFile} className="ml-auto rounded p-0.5 hover:bg-blue-100"><X size={11} /></button>
          </div>
        )}

        <div className="flex items-end gap-2 rounded-2xl border border-gray-200 bg-gray-50 px-3 py-2 focus-within:border-blue-300 focus-within:bg-white focus-within:shadow-sm transition-all">
          <input ref={fileInputRef} type="file" accept=".png,.jpg,.jpeg,.pdf,.txt,.csv,.json" className="hidden" onChange={handleFile} />
          <button onClick={() => fileInputRef.current?.click()}
            className="mb-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-200 hover:text-gray-600 transition-colors" aria-label="Attach">
            <Paperclip size={15} />
          </button>

          <textarea ref={inputRef} rows={1} maxLength={MAX_INPUT}
            placeholder="Ask anything about travel..."
            value={input} onChange={e => { setInput(e.target.value); autoResize(e.target) }}
            onKeyDown={handleKeyDown} disabled={loading}
            className="flex-1 min-w-0 resize-none overflow-hidden border-0 bg-transparent py-1.5 px-1 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-0 disabled:text-gray-400 leading-relaxed"
            style={{ minHeight: '32px', maxHeight: '140px' }} />

          {/* Voice */}
          <div className="relative mb-0.5 flex shrink-0 items-center" ref={langRef}>
            <button onClick={() => !listening && setShowLangPicker(v => !v)} title={voiceLang.name}
              className={cn('flex h-8 items-center gap-0.5 rounded-l-lg border border-r-0 px-1.5 text-[10px] font-bold transition-colors',
                listening ? 'border-red-200 bg-red-50 text-red-400' : 'border-gray-200 bg-white text-gray-500 hover:bg-gray-100')}>
              {voiceLang.label}
              {!listening && <ChevronDown size={9} />}
            </button>
            <button onClick={toggleVoice}
              className={cn('flex h-8 w-8 items-center justify-center rounded-r-lg border transition-colors',
                listening ? 'border-red-200 bg-red-50 text-red-500 hover:bg-red-100' : 'border-gray-200 bg-white text-gray-400 hover:bg-gray-100 hover:text-gray-600')}>
              {listening ? <MicOff size={14} /> : <Mic size={14} />}
            </button>
            {showLangPicker && (
              <div className="absolute bottom-full right-0 mb-2 z-50 w-44 rounded-xl border border-gray-200 bg-white shadow-xl py-1">
                <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">Voice Language</p>
                {VOICE_LANGUAGES.map(lang => (
                  <button key={lang.code} onClick={() => { setVoiceLang(lang); setShowLangPicker(false) }}
                    className={cn('flex w-full items-center gap-2 px-3 py-1.5 text-sm hover:bg-gray-50 transition-colors',
                      voiceLang.code === lang.code ? 'text-blue-600 font-semibold' : 'text-gray-700')}>
                    <span className="w-5 text-center text-xs font-bold text-gray-400">{lang.label}</span>
                    <span>{lang.name}</span>
                    {voiceLang.code === lang.code && <Check size={11} className="ml-auto text-blue-600" />}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Send */}
          <button onClick={() => sendMsg()} disabled={!canSend}
            className={cn('mb-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all',
              canSend ? 'bg-gradient-to-r from-blue-600 to-cyan-500 text-white shadow-sm hover:shadow-md' : 'bg-gray-200 text-gray-400 cursor-not-allowed')}
            aria-label="Send">
            {loading ? <Spinner size="sm" /> : <Send size={14} />}
          </button>
        </div>

        <div className="mt-1.5 flex items-center justify-between text-[10px] text-gray-400 px-1">
          <span>Enter to send · Shift+Enter for new line</span>
          <span>{input.length}/{MAX_INPUT}</span>
        </div>
      </div>
    </div>
  )
}

/* ── Welcome Screen ──────────────────────────────────── */

function WelcomeScreen({ onSuggest, userName }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 animate-fade-in">
      <div className="relative mb-5">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-dark to-brand-mid shadow-lg">
          <Brain size={28} className="text-brand-cyan" />
        </div>
        <div className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-green-400 border-2 border-white" />
      </div>

      <h3 className="text-xl font-bold text-gray-900">
        {userName ? `Hi ${userName}, how can I help?` : 'How can I help you today?'}
      </h3>
      <p className="mt-1.5 max-w-md text-center text-sm text-gray-500">
        I can plan trips, find flights and hotels, check weather, manage expenses, and answer travel policy questions.
      </p>

      {/* Capabilities */}
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        {[
          { icon: Plane, label: 'Flight Search' },
          { icon: Hotel, label: 'Hotel Booking' },
          { icon: CloudSun, label: 'Weather' },
          { icon: Shield, label: 'Policy Check' },
          { icon: Globe, label: '10 Languages' },
          { icon: Zap, label: 'Real-time Data' },
        ].map((c) => (
          <span key={c.label} className="flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-1.5 text-[11px] font-medium text-gray-600">
            <c.icon size={12} className="text-gray-400" /> {c.label}
          </span>
        ))}
      </div>

      {/* Suggestions */}
      <div className="mt-6 grid w-full max-w-lg grid-cols-1 gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map(s => (
          <button key={s.text} onClick={() => onSuggest(s.text)}
            className="group flex items-start gap-3 rounded-xl border border-gray-200 bg-white p-3.5 text-left transition-all hover:border-blue-200 hover:shadow-md">
            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gray-50 border border-gray-100 group-hover:bg-gradient-to-br group-hover:from-blue-500 group-hover:to-cyan-500 group-hover:border-transparent transition-all">
              <s.icon size={14} className="text-gray-400 group-hover:text-white" />
            </div>
            <div>
              <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 group-hover:text-blue-500">{s.tag}</span>
              <p className="text-[13px] text-gray-700 leading-snug mt-0.5">{s.text}</p>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

/* ── Message Bubble ──────────────────────────────────── */

function MessageBubble({ message: msg, onCopy, copied, onRegenerate, onAction, isLastAssistant, userInitial, navigate }) {
  const isUser = msg.role === 'user'
  const cards  = (!isUser && Array.isArray(msg.action_cards)) ? msg.action_cards : []
  const parsedDate = msg.time ? new Date(msg.time) : null
  const time = parsedDate && !Number.isNaN(parsedDate.getTime()) ? format(parsedDate, 'h:mm a') : ''

  return (
    <div className={cn('group flex gap-3', isUser && 'flex-row-reverse', 'animate-fade-in')}>
      <div className={cn('mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold',
        isUser ? 'bg-gradient-to-br from-blue-500 to-cyan-500 text-white shadow-sm' : 'bg-white border border-gray-200 text-gray-500 shadow-sm')}>
        {isUser ? userInitial : <Brain size={14} className="text-brand-cyan" />}
      </div>

      <div className={cn('flex min-w-0 max-w-[82%] flex-col gap-1', isUser ? 'items-end' : 'items-start')}>
        {/* Label */}
        <span className="text-[10px] font-medium text-gray-400 px-1">
          {isUser ? 'You' : 'TravelSync AI'}
        </span>

        {/* Bubble */}
        <div className={cn('rounded-2xl px-4 py-3 text-sm leading-relaxed',
          isUser
            ? 'bg-gradient-to-br from-brand-dark to-[#1a2744] text-white rounded-tr-sm shadow-sm'
            : msg.error
            ? 'border border-red-200 bg-red-50 text-red-700 rounded-tl-sm'
            : 'bg-white border border-gray-100 text-gray-800 rounded-tl-sm shadow-sm'
        )}>
          {msg.streaming && !msg.content ? (
            <span className="flex items-center gap-1.5 py-0.5 text-gray-400 text-xs">
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

        {/* Trip results */}
        {!isUser && msg.trip_results && (
          <TripResultsCard results={msg.trip_results} onViewFull={() => navigate?.('/planner')} />
        )}

        {/* Action cards */}
        {cards.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-0.5">
            {cards.map((card, i) => (
              <button key={i} onClick={() => onAction?.(card)}
                className={cn('flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-all',
                  card.action === 'openSOS' ? 'border-red-200 bg-red-50 text-red-600 hover:bg-red-500 hover:text-white hover:border-red-500'
                  : card.action === 'tel' ? 'border-green-200 bg-green-50 text-green-600 hover:bg-green-500 hover:text-white'
                  : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-900 hover:text-white hover:border-gray-900')}>
                {card.action === 'tel' && <Phone size={10} />}
                {card.label}
              </button>
            ))}
          </div>
        )}

        {/* Meta */}
        <div className={cn('flex items-center gap-2 px-1', isUser ? 'flex-row-reverse' : '')}>
          {time && <span className="text-[10px] text-gray-400">{time}</span>}
          {!isUser && (
            <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
              <button onClick={onCopy} className="rounded p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100" title="Copy">
                {copied ? <Check size={11} className="text-green-500" /> : <Copy size={11} />}
              </button>
              {isLastAssistant && (
                <button onClick={onRegenerate} className="rounded p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100" title="Regenerate">
                  <RefreshCw size={11} />
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

function TypingBubble() {
  return (
    <div className="flex gap-3 animate-fade-in">
      <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white border border-gray-200 shadow-sm">
        <Brain size={14} className="text-brand-cyan" />
      </div>
      <div>
        <span className="text-[10px] font-medium text-gray-400 px-1">TravelSync AI</span>
        <div className="rounded-2xl rounded-tl-sm bg-white border border-gray-100 shadow-sm px-4 py-3 mt-1">
          <span className="flex items-center gap-1.5 text-xs text-gray-400">
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

function TripResultsCard({ results, onViewFull }) {
  if (!results) return null
  const flights = results.flights || []
  const hotels  = results.hotels  || []
  const wx      = results.weather || {}
  if (!flights.length && !hotels.length && !wx.summary) return null

  return (
    <div className="mt-1 w-full max-w-sm rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-3">
        <div className="flex h-6 w-6 items-center justify-center rounded-md bg-blue-50 border border-blue-100">
          <MapPin size={12} className="text-blue-600" />
        </div>
        <p className="text-sm font-semibold text-gray-900">{results.destination || 'Trip Plan'}</p>
        {results.travel_dates && <span className="ml-auto text-[11px] text-gray-400">{results.travel_dates}</span>}
      </div>

      {flights.length > 0 && (
        <div className="mb-2.5">
          <p className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400 mb-1.5">
            <Plane size={10} /> Flights
          </p>
          {flights.map((f, i) => (
            <div key={i} className="flex justify-between rounded-lg bg-gray-50 border border-gray-100 px-3 py-2 text-xs mb-1">
              <span className="text-gray-700 truncate">{f.airline || f.carrier} {f.flight_number || ''}</span>
              {(f.price || f.fare) && <span className="font-bold text-gray-900 ml-2 shrink-0">₹{Number(f.price || f.fare).toLocaleString('en-IN')}</span>}
            </div>
          ))}
        </div>
      )}

      {hotels.length > 0 && (
        <div className="mb-2.5">
          <p className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400 mb-1.5">
            <Hotel size={10} /> Hotels
          </p>
          {hotels.map((h, i) => (
            <div key={i} className="flex justify-between rounded-lg bg-gray-50 border border-gray-100 px-3 py-2 text-xs mb-1">
              <span className="text-gray-700 truncate">{h.name || h.hotel_name}</span>
              {(h.price || h.price_per_night) && <span className="font-bold text-gray-900 ml-2 shrink-0">₹{Number(h.price || h.price_per_night).toLocaleString('en-IN')}/n</span>}
            </div>
          ))}
        </div>
      )}

      {wx.summary && (
        <div className="mb-2.5">
          <p className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400 mb-1">
            <CloudSun size={10} /> Weather
          </p>
          <p className="text-xs text-gray-600">{wx.summary}</p>
        </div>
      )}

      {onViewFull && (
        <button onClick={onViewFull}
          className="flex w-full items-center justify-center gap-1 rounded-lg bg-gray-50 border border-gray-200 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-100 transition-colors">
          View Full Plan <ArrowRight size={11} />
        </button>
      )}
    </div>
  )
}

/* ── Helpers ─────────────────────────────────────────── */

function autoResize(el) {
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 140)}px`
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
