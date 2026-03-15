import { useState, useEffect, useRef } from 'react'
import {
  Send, Sparkles, Copy, RefreshCw,
  MapPin, CloudSun, Plane, Mic, Paperclip, X, Bot, MessageSquarePlus,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { sendMessage, getChatHistory } from '../api/chat'
import useStore from '../store/useStore'
import Button from '../components/ui/Button'
import Spinner from '../components/ui/Spinner'
import { format } from 'date-fns'

const SUGGESTIONS = [
  { icon: Plane, text: 'Plan a business trip from New York to London next week' },
  { icon: CloudSun, text: 'What is the weather forecast in Tokyo for next 3 days?' },
  { icon: MapPin, text: 'Find hotels near Berlin city center for 2 travelers' },
  { icon: Plane, text: 'Compare train vs flight for Paris to Amsterdam' },
]

const FOLLOW_UP_SUGGESTIONS = [
  'Show cheaper alternatives',
  'Create a day-wise itinerary',
  'Suggest nearby client meeting spots',
]

const URL_REGEX = /(https?:\/\/[^\s]+)/g
const MAX_INPUT_CHARS = 1600
const MIN_TEXTAREA_HEIGHT = 44
const MAX_TEXTAREA_HEIGHT = 140
const MAX_FILE_SIZE = 20 * 1024 * 1024

export default function Chat() {
  const { auth } = useStore()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [histLoading, setHistLoading] = useState(true)
  const [selectedFile, setSelectedFile] = useState(null)
  const [listening, setListening] = useState(false)

  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const fileInputRef = useRef(null)
  const recognitionRef = useRef(null)

  const userInitial = auth.user?.name?.charAt(0)?.toUpperCase() || 'U'
  const canSend = (!loading && (input.trim().length > 0 || Boolean(selectedFile)))
  const lastAssistantId = [...messages].reverse().find((m) => m.role === 'assistant')?.id
  const lastUserPrompt = getLastUserPrompt(messages)

  useEffect(() => {
    loadHistory()
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  useEffect(() => {
    return () => {
      recognitionRef.current?.stop?.()
    }
  }, [])

  const loadHistory = async () => {
    try {
      const data = await getChatHistory()
      const history = Array.isArray(data) ? data : data.messages || []
      if (history.length > 0) {
        setMessages(history.map((m) => ({
          id: m.id || Date.now() + Math.random(),
          role: m.role || (m.is_bot ? 'assistant' : 'user'),
          content: m.content || m.message || m.text,
          time: m.created_at || m.timestamp || new Date().toISOString(),
          source: m.source,
        })))
      }
    } catch {
      // Preserve clean first-load experience if history API is unavailable.
    } finally {
      setHistLoading(false)
    }
  }

  const toggleVoiceInput = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      toast.error('Voice input is not supported in this browser')
      return
    }

    if (listening) {
      recognitionRef.current?.stop?.()
      setListening(false)
      return
    }

    const recognition = new SpeechRecognition()
    recognition.lang = 'en-US'
    recognition.interimResults = false
    recognition.maxAlternatives = 1

    recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript?.trim()
      if (!transcript) return
      setInput((prev) => {
        const next = prev ? `${prev} ${transcript}` : transcript
        return next.slice(0, MAX_INPUT_CHARS)
      })
      if (inputRef.current) resizeInput(inputRef.current)
      toast.success('Voice text captured')
    }

    recognition.onerror = () => {
      toast.error('Could not process voice input')
      setListening(false)
    }

    recognition.onend = () => setListening(false)

    recognitionRef.current = recognition
    recognition.start()
    setListening(true)
  }

  const handleFileSelect = (event) => {
    const file = event.target.files?.[0]
    if (!file) return

    if (file.size > MAX_FILE_SIZE) {
      toast.error('File is too large. Max size is 20MB.')
      event.target.value = ''
      return
    }

    setSelectedFile(file)
  }

  const removeSelectedFile = () => {
    setSelectedFile(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const sendMsg = async (text) => {
    const content = (typeof text === 'string' ? text : input).trim()
    if ((!content && !selectedFile) || loading) return

    const pendingFile = selectedFile

    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: pendingFile
        ? [content, `[Attachment: ${pendingFile.name}]`].filter(Boolean).join('\n')
        : content,
      time: new Date().toISOString(),
    }

    setMessages((prev) => [...prev, userMsg])
    setLoading(true)
    setInput('')

    if (inputRef.current) {
      inputRef.current.style.height = `${MIN_TEXTAREA_HEIGHT}px`
    }

    try {
      const data = await sendMessage(content, { user: auth.user?.name }, pendingFile)
      removeSelectedFile()

      const reply = data.reply || data.message || data.response || 'Sorry, I could not process that.'

      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: 'assistant',
          content: reply,
          time: new Date().toISOString(),
          source: data.source,
        },
      ])

    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: 'assistant',
          content: 'Sorry, I encountered an error. Please try again.',
          time: new Date().toISOString(),
          error: true,
        },
      ])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      sendMsg()
    }
  }

  const copyMessage = (content) => {
    navigator.clipboard.writeText(content)
    toast.success('Copied to clipboard')
  }

  const regenerateLastResponse = () => {
    if (!lastUserPrompt || loading) return
    sendMsg(lastUserPrompt)
  }

  const startNewChat = () => {
    setMessages([])
    setInput('')
    removeSelectedFile()
    if (inputRef.current) {
      inputRef.current.style.height = `${MIN_TEXTAREA_HEIGHT}px`
    }
  }

  return (
    <div className="mx-auto w-full max-w-7xl rounded-3xl border border-[#cdd6e0] bg-[radial-gradient(circle_at_top_left,#f6f9fc_0%,transparent_38%),linear-gradient(180deg,#edf1f5_0%,#E0E1DD_100%)] p-2 sm:p-3">
      <div className="flex h-[calc(100dvh-88px)] min-h-[540px] min-w-0 flex-col gap-3 lg:flex-row">
        <aside className="hidden w-72 shrink-0 flex-col rounded-2xl border border-[#d3dbe7] bg-white/95 p-4 shadow-[0_10px_22px_rgba(27,38,59,0.07)] lg:flex">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#1B263B] text-white">
              <Bot size={16} />
            </div>
            <div>
              <p className="text-sm font-semibold text-[#1B263B]">Travel AI</p>
              <p className="text-xs text-[#778DA9]">Smart assistant</p>
            </div>
          </div>

          <div className="mt-4">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#7d90a7]">
              Quick prompts
            </p>
            <div className="space-y-2">
              {SUGGESTIONS.slice(0, 3).map((suggestion) => (
                <button
                  key={suggestion.text}
                  type="button"
                  onClick={() => sendMsg(suggestion.text)}
                  className="w-full rounded-xl border border-[#dde5ef] bg-white px-3 py-2.5 text-left text-xs text-[#4f647b] transition-colors hover:border-[#4CC9F0]/60 hover:bg-[#f4fbff]"
                >
                  {suggestion.text}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-4">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#7d90a7]">
              Follow-ups
            </p>
            <div className="flex flex-wrap gap-2">
              {FOLLOW_UP_SUGGESTIONS.map((tip) => (
                <button
                  key={tip}
                  type="button"
                  onClick={() => sendMsg(tip)}
                  className="rounded-full border border-[#dbe4ee] bg-[#f8fbff] px-2.5 py-1 text-[11px] text-[#5a7088] transition-colors hover:border-[#4CC9F0]/60"
                >
                  {tip}
                </button>
              ))}
            </div>
          </div>
        </aside>

        <section className="flex min-h-0 flex-1 flex-col rounded-2xl border border-[#d3dbe7] bg-white/95 shadow-[0_10px_22px_rgba(27,38,59,0.07)]">
          <div className="flex flex-col gap-2 border-b border-[#dde4ee] px-3 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#1B263B] text-white">
                <Sparkles size={15} />
              </div>
              <div>
                <p className="text-sm font-semibold text-[#1B263B]">AI Travel Chat</p>
                <p className="text-xs text-[#778DA9]">
                  {histLoading ? 'Syncing history...' : 'Ask routes, hotels, policies, weather, and costs'}
                </p>
              </div>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={startNewChat}
              leftIcon={<MessageSquarePlus size={14} />}
              className="w-full justify-center border border-[#d5deea] bg-white text-[#1B263B] hover:bg-[#f6fafe] sm:w-auto"
            >
              New Chat
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto px-3 py-4 sm:px-5 sm:py-5">
            <div className="mx-auto w-full max-w-4xl">
              {histLoading ? (
                <div className="flex justify-center py-10">
                  <Spinner size="md" color="accent" />
                </div>
              ) : messages.length === 0 ? (
                <WelcomeScreen onSuggest={sendMsg} userName={auth.user?.name?.split(' ')[0]} />
              ) : (
                <div className="space-y-5">
                  {messages.map((msg) => (
                    <MessageBubble
                      key={msg.id}
                      message={msg}
                      onCopy={() => copyMessage(msg.content)}
                      onRegenerate={regenerateLastResponse}
                      isLastAssistant={msg.role === 'assistant' && msg.id === lastAssistantId}
                      userInitial={userInitial}
                    />
                  ))}

                  {loading && <TypingBubble />}
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          </div>

          <div className="shrink-0 border-t border-[#dde4ee] bg-white/90 px-3 py-3 sm:px-5 sm:py-4">
            <div className="mx-auto w-full max-w-4xl">
              {messages.length > 0 && !loading && (
                <div className="mb-3 flex flex-wrap gap-2">
                  {FOLLOW_UP_SUGGESTIONS.map((tip) => (
                    <button
                      key={tip}
                      type="button"
                      onClick={() => sendMsg(tip)}
                      className="rounded-full border border-[#dbe4ee] bg-white px-3 py-1 text-xs text-[#5a7088] transition-colors hover:border-[#4CC9F0]/60 hover:bg-[#f4fbff]"
                    >
                      {tip}
                    </button>
                  ))}
                </div>
              )}

              {selectedFile && (
                <div className="mb-2 flex items-center gap-2 rounded-lg border border-accent-100 bg-accent-50 px-3 py-2 text-xs text-accent-700">
                  <Paperclip size={12} />
                  <span className="truncate">{selectedFile.name}</span>
                  <span className="shrink-0 text-[11px] text-accent-600">{formatFileSize(selectedFile.size)}</span>
                  <button
                    type="button"
                    onClick={removeSelectedFile}
                    className="ml-auto rounded p-0.5 text-accent-500 transition-colors hover:bg-accent-100 hover:text-accent-700"
                    aria-label="Remove attachment"
                  >
                    <X size={12} />
                  </button>
                </div>
              )}

              <div className="rounded-2xl border border-[#ced8e4] bg-white p-2 shadow-[0_8px_18px_rgba(27,38,59,0.08)]">
                <div className="flex items-end gap-2">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".png,.jpg,.jpeg,.pdf,.txt,.csv,.json"
                    className="hidden"
                    onChange={handleFileSelect}
                  />

                  <Button
                    variant="ghost"
                    onClick={() => fileInputRef.current?.click()}
                    className="h-11 w-11 !p-0 shrink-0 rounded-xl border border-transparent hover:border-[#d3dde9]"
                    aria-label="Attach file"
                    title="Attach file"
                  >
                    <Paperclip size={16} />
                  </Button>

                  <div className="flex-1">
                    <textarea
                      ref={inputRef}
                      rows={1}
                      maxLength={MAX_INPUT_CHARS}
                      placeholder="Ask anything about global travel, routes, costs, weather, and policies..."
                      value={input}
                      onChange={(event) => {
                        setInput(event.target.value)
                        resizeInput(event.target)
                      }}
                      onKeyDown={handleKeyDown}
                      disabled={loading}
                      className="w-full resize-none overflow-hidden rounded-xl border-0 bg-transparent px-4 py-3 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-0 disabled:bg-gray-50 disabled:text-gray-400"
                      style={{ minHeight: `${MIN_TEXTAREA_HEIGHT}px`, maxHeight: `${MAX_TEXTAREA_HEIGHT}px` }}
                    />
                  </div>

                  <Button
                    variant={listening ? 'danger' : 'ghost'}
                    onClick={toggleVoiceInput}
                    className="h-11 w-11 !p-0 shrink-0 rounded-xl border border-transparent hover:border-[#d3dde9]"
                    aria-label="Toggle voice input"
                    title={listening ? 'Stop voice input' : 'Start voice input'}
                  >
                    <Mic size={16} />
                  </Button>

                  <Button
                    onClick={() => sendMsg()}
                    loading={loading}
                    disabled={!canSend}
                    leftIcon={!loading ? <Send size={15} /> : null}
                    className="h-11 shrink-0 rounded-xl border border-[#4CC9F0] bg-[#4CC9F0] px-3 text-[#1B263B] hover:bg-[#35bee9] sm:px-4"
                    aria-label="Send message"
                  >
                    <span className="hidden sm:inline">Send</span>
                  </Button>
                </div>
              </div>

              <div className="mt-2 flex flex-wrap items-center justify-between gap-1 px-1 text-[11px] text-[#7e92a7]">
                <span className="hidden sm:inline">Enter to send · Shift+Enter for new line</span>
                <span>{input.length}/{MAX_INPUT_CHARS}</span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

function WelcomeScreen({ onSuggest, userName }) {
  return (
    <div className="mx-auto max-w-4xl rounded-2xl border border-[#d6deea] bg-[linear-gradient(135deg,#ffffff_0%,#f4f8fd_100%)] p-5 shadow-[0_10px_22px_rgba(27,38,59,0.07)] animate-fade-in sm:p-7">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-[#1B263B] text-white">
        <Sparkles size={24} className="text-white" />
      </div>

      <h3 className="text-center font-heading text-xl font-semibold text-[#1B263B]">
        Hi{userName ? `, ${userName}` : ''}. Start with a prompt below.
      </h3>
      <p className="mx-auto mt-1 max-w-xl text-center text-sm leading-relaxed text-gray-500">
        Ask for flights, trains, hotels, weather, itineraries, policy checks, and expense guidance.
        You can also use voice input and upload files.
      </p>

      <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
        {['Flights', 'Hotels', 'Weather', 'Expenses', 'Policies', 'Meetings'].map((item) => (
          <span
            key={item}
            className="rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs font-medium text-gray-600"
          >
            {item}
          </span>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-3 text-left sm:grid-cols-2">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion.text}
            type="button"
            onClick={() => onSuggest(suggestion.text)}
            className="group flex items-start gap-3 rounded-xl border border-[#dce5ef] bg-white p-4 text-left transition-all hover:border-[#4CC9F0]/60 hover:bg-[#f4fbff]"
          >
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[#dce5ef] bg-[#f8fbff] transition-colors group-hover:bg-[#eef8fd]">
              <suggestion.icon size={16} className="text-[#425a75]" />
            </div>
            <span className="text-sm text-[#4f647b] group-hover:text-[#1B263B]">{suggestion.text}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function MessageBubble({ message: msg, onCopy, onRegenerate, isLastAssistant, userInitial }) {
  const isUser = msg.role === 'user'
  const parsedDate = msg.time ? new Date(msg.time) : null
  const time = parsedDate && !Number.isNaN(parsedDate.getTime()) ? format(parsedDate, 'h:mm a') : ''

  return (
    <div className={`flex max-w-[min(48rem,92vw)] items-start gap-3 ${isUser ? 'ml-auto flex-row-reverse' : ''} animate-fade-in`}>
      <div
        className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
          isUser ? 'bg-[#1B263B] text-white' : 'bg-[#e9f2fb] text-[#3c5876]'
        }`}
      >
        {isUser ? <span className="text-xs font-bold">{userInitial}</span> : <Sparkles size={14} />}
      </div>

      <div className={`group flex min-w-0 flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={`max-w-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? 'rounded-2xl bg-[#1B263B] text-white'
              : msg.error
              ? 'rounded-2xl border border-red-100 bg-red-50 text-red-700'
              : 'rounded-2xl border border-[#dce5ef] bg-[#f8fbff] text-[#2f435c]'
          }`}
        >
          {renderMessageContent(msg.content)}
        </div>

        <div className={`flex items-center gap-2 ${isUser ? 'flex-row-reverse' : ''}`}>
          {time && <span className="text-[10px] text-[#8ba0b6]">{time}</span>}
          {!isUser && msg.source && (
            <span className="rounded-full border border-[#dce5ef] bg-white px-2 py-0.5 text-[10px] text-[#7f93a8]">
              {msg.source}
            </span>
          )}
          {!isUser && (
            <>
              <button
                type="button"
                onClick={onCopy}
                className="rounded p-1 text-[#9ab0c5] opacity-0 transition-all hover:text-[#5f748c] group-hover:opacity-100"
                title="Copy response"
              >
                <Copy size={11} />
              </button>
              {isLastAssistant && onRegenerate && (
                <button
                  type="button"
                  onClick={onRegenerate}
                  className="rounded p-1 text-[#9ab0c5] opacity-0 transition-all hover:text-[#5f748c] group-hover:opacity-100"
                  title="Regenerate response"
                >
                  <RefreshCw size={11} />
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function TypingBubble() {
  return (
    <div className="flex max-w-4xl items-start gap-3 animate-fade-in">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#e9f2fb] text-[#3c5876]">
        <Sparkles size={14} />
      </div>
      <div className="rounded-2xl border border-[#dce5ef] bg-[#f8fbff] px-4 py-3">
        <div className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-[#6e87a2] animate-bounce" style={{ animationDelay: '-0.2s' }} />
          <span className="h-1.5 w-1.5 rounded-full bg-[#6e87a2] animate-bounce" style={{ animationDelay: '-0.1s' }} />
          <span className="h-1.5 w-1.5 rounded-full bg-[#6e87a2] animate-bounce" />
          <span className="ml-1 text-xs text-[#5f748c]">Thinking...</span>
        </div>
      </div>
    </div>
  )
}

function renderMessageContent(content) {
  const safeText = String(content || '')
  const codeChunks = safeText.split(/```/)

  return codeChunks.map((chunk, chunkIndex) => {
    const isCode = chunkIndex % 2 === 1

    if (isCode) {
      return (
        <pre
          key={`code-${chunkIndex}`}
          className="my-2 overflow-x-auto rounded-lg border border-gray-200 bg-gray-900 px-3 py-2 text-xs text-gray-100"
        >
          <code>{chunk.trim()}</code>
        </pre>
      )
    }

    const lines = chunk.split('\n')
    return lines.map((line, lineIndex) => {
      const trimmed = line.trim()
      const key = `line-${chunkIndex}-${lineIndex}`

      if (!trimmed) return <div key={key} className="h-3" />

      if (/^\[attachment:/i.test(trimmed)) {
        const label = trimmed.replace(/^\[attachment:\s*/i, '').replace(/\]$/, '').trim()
        return (
          <div key={key} className="my-1 inline-flex items-center gap-1 rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-xs text-gray-700">
            <Paperclip size={12} />
            <span>Attachment: {label}</span>
          </div>
        )
      }

      if (/^[-*]\s+/.test(trimmed)) {
        const text = trimmed.replace(/^[-*]\s+/, '')
        return (
          <div key={key} className="mt-1 flex items-start gap-2">
            <span className="mt-[7px] h-1.5 w-1.5 rounded-full bg-gray-400" />
            <span>{renderInlineText(text)}</span>
          </div>
        )
      }

      return (
        <p key={key} className="mt-1.5 first:mt-0">
          {renderInlineText(line)}
        </p>
      )
    })
  })
}

function resizeInput(textarea) {
  textarea.style.height = 'auto'
  const nextHeight = Math.min(textarea.scrollHeight, MAX_TEXTAREA_HEIGHT)
  textarea.style.height = `${Math.max(nextHeight, MIN_TEXTAREA_HEIGHT)}px`
}

function formatFileSize(bytes = 0) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function getLastUserPrompt(messages) {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const msg = messages[i]
    if (msg.role !== 'user') continue
    const clean = String(msg.content || '')
      .split('\n')
      .filter((line) => !/^\[attachment:/i.test(line.trim()))
      .join('\n')
      .trim()
    if (clean) return clean
  }
  return ''
}

function renderInlineText(line) {
  return line.split(URL_REGEX).map((part, i) => {
    const isUrl = /^https?:\/\//.test(part)
    if (!isUrl) return <span key={`${part}-${i}`}>{part}</span>

    return (
      <a
        key={`${part}-${i}`}
        href={part}
        target="_blank"
        rel="noreferrer"
        className="break-all underline underline-offset-2 hover:opacity-80"
      >
        {part}
      </a>
    )
  })
}
