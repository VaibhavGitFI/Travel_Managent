import { useState, useEffect, useRef, useCallback } from 'react'
import { X, Mic, MicOff, Send, ChevronDown, ChevronUp } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  getOtisStatus,
  startOtisSession,
  stopOtisSession,
  sendOtisCommandRest,
} from '../../api/otis'
import useStore from '../../store/useStore'

const S = {
  IDLE: 'idle',
  CONNECTING: 'connecting',
  READY: 'ready',
  LISTENING: 'listening',
  PROCESSING: 'processing',
  SPEAKING: 'speaking',
  ERROR: 'error',
}

// Orb visual config per state
const ORB = {
  [S.IDLE]:       { grad: 'radial-gradient(circle at 35% 30%, #60a5fa, #1d4ed8 55%, #0f172a)', glow: 'rgba(59,130,246,0.25)', dur: '3s', anim: 'ot-breathe' },
  [S.CONNECTING]: { grad: 'radial-gradient(circle at 35% 30%, #94a3b8, #475569 55%, #0f172a)', glow: 'rgba(148,163,184,0.2)', dur: '1s', anim: 'ot-breathe' },
  [S.READY]:      { grad: 'radial-gradient(circle at 35% 30%, #34d399, #059669 55%, #064e3b)', glow: 'rgba(52,211,153,0.25)', dur: '3s', anim: 'ot-breathe' },
  [S.LISTENING]:  { grad: 'radial-gradient(circle at 30% 30%, rgba(96,165,250,0.95), transparent 52%), radial-gradient(circle at 72% 28%, rgba(167,139,250,0.9), transparent 52%), radial-gradient(circle at 50% 78%, rgba(244,114,182,0.85), transparent 48%), #0f0a2e', glow: 'rgba(167,139,250,0.45)', dur: '0.55s', anim: 'ot-listen' },
  [S.PROCESSING]: { grad: 'radial-gradient(circle at 28% 28%, rgba(251,191,36,0.95), transparent 52%), radial-gradient(circle at 72% 28%, rgba(251,146,60,0.9), transparent 52%), radial-gradient(circle at 50% 78%, rgba(239,68,68,0.7), transparent 48%), #1a0800', glow: 'rgba(251,191,36,0.35)', dur: '0.9s', anim: 'ot-spin' },
  [S.SPEAKING]:   { grad: 'radial-gradient(circle at 30% 30%, rgba(52,211,153,0.95), transparent 52%), radial-gradient(circle at 70% 30%, rgba(96,165,250,0.85), transparent 52%), radial-gradient(circle at 50% 78%, rgba(167,139,250,0.75), transparent 48%), #021a14', glow: 'rgba(52,211,153,0.4)', dur: '0.7s', anim: 'ot-speak' },
  [S.ERROR]:      { grad: 'radial-gradient(circle at 35% 30%, #f87171, #dc2626 55%, #450a0a)', glow: 'rgba(248,113,113,0.3)', dur: '2s', anim: 'ot-breathe' },
}

const LABEL = {
  [S.IDLE]:       'Initializing…',
  [S.CONNECTING]: 'Connecting…',
  [S.READY]:      'Tap orb to speak',
  [S.LISTENING]:  'Listening…',
  [S.PROCESSING]: 'Thinking…',
  [S.SPEAKING]:   'Speaking…',
  [S.ERROR]:      'Error — tap to retry',
}

export default function OtisVoiceWidget({ onClose }) {
  useStore()
  const [state, setState] = useState(S.IDLE)
  const [sessionId, setSessionId] = useState(null)
  const [transcript, setTranscript] = useState('')
  const [response, setResponse] = useState('')
  const [history, setHistory] = useState([])
  const [showHistory, setShowHistory] = useState(false)
  const [inputText, setInputText] = useState('')

  const recognitionRef = useRef(null)
  const stateRef = useRef(S.IDLE)
  const sessionIdRef = useRef(null)
  const historyEndRef = useRef(null)

  // Keep refs in sync
  useEffect(() => { stateRef.current = state }, [state])
  useEffect(() => { sessionIdRef.current = sessionId }, [sessionId])

  // Auto-scroll history
  useEffect(() => {
    if (showHistory) historyEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history, showHistory])

  // Bootstrap session on mount, clean up on unmount
  useEffect(() => {
    initSession()
    return () => {
      stopListening()
      if (window.speechSynthesis) window.speechSynthesis.cancel()
      if (sessionIdRef.current) {
        stopOtisSession(sessionIdRef.current).catch(() => {})
      }
    }
  }, [])

  const initSession = async () => {
    setState(S.CONNECTING)
    try {
      const status = await getOtisStatus()
      if (!status.available) {
        toast.error(status.reason || 'OTIS unavailable')
        setState(S.ERROR)
        return
      }
      const session = await startOtisSession()
      setSessionId(session.session_id)
      setState(S.READY)
      setResponse("Hi! I'm OTIS. How can I help?")
      speakAndReturn("Hi! I'm OTIS. How can I help?")
    } catch {
      setState(S.ERROR)
    }
  }

  // ── Voice input ─────────────────────────────────────────────────────────────

  const startListening = useCallback(() => {
    if (stateRef.current === S.LISTENING || stateRef.current === S.PROCESSING || stateRef.current === S.CONNECTING) return

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) {
      toast.error('Speech recognition not supported in this browser')
      return
    }

    const rec = new SR()
    rec.continuous = false
    rec.interimResults = true
    rec.lang = 'en-IN'
    rec.maxAlternatives = 1

    rec.onstart = () => {
      setState(S.LISTENING)
      setTranscript('')
    }

    rec.onresult = (e) => {
      let interim = ''
      let final = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript
        if (e.results[i].isFinal) final += t
        else interim += t
      }
      setTranscript(final || interim)
      if (final) {
        recognitionRef.current = null
        processCommand(final)
      }
    }

    rec.onerror = (e) => {
      if (e.error !== 'no-speech' && e.error !== 'aborted') {
        toast.error(`Mic error: ${e.error}`)
      }
      if (stateRef.current === S.LISTENING) setState(S.READY)
    }

    rec.onend = () => {
      if (stateRef.current === S.LISTENING) setState(S.READY)
    }

    recognitionRef.current = rec
    try { rec.start() } catch { setState(S.READY) }
  }, [])

  const stopListening = () => {
    if (recognitionRef.current) {
      try { recognitionRef.current.stop() } catch {}
      recognitionRef.current = null
    }
  }

  // ── Command processing ──────────────────────────────────────────────────────

  const processCommand = useCallback(async (command) => {
    if (!command.trim()) return
    stopListening()
    setState(S.PROCESSING)
    setTranscript(command)
    setResponse('')

    try {
      const result = await sendOtisCommandRest(command, sessionIdRef.current)
      const text = result.response || 'Done.'
      setResponse(text)
      setHistory(h => [...h, { role: 'user', text: command }, { role: 'assistant', text }])
      speakAndReturn(text)
    } catch (err) {
      console.error('[OTIS] Command failed:', err)
      const errText = 'Sorry, something went wrong. Please try again.'
      setResponse(errText)
      setState(S.READY)
      toast.error('OTIS command failed')
    }
  }, [])

  const speakAndReturn = (text) => {
    setState(S.SPEAKING)
    if (!('speechSynthesis' in window)) {
      setState(S.READY)
      setTimeout(startListening, 500)
      return
    }
    window.speechSynthesis.cancel()
    const utt = new SpeechSynthesisUtterance(text)
    utt.lang = 'en-IN'
    utt.rate = 1.05
    utt.pitch = 1.0
    utt.onend = () => {
      setState(S.READY)
      setTimeout(startListening, 600)
    }
    utt.onerror = () => {
      setState(S.READY)
      setTimeout(startListening, 600)
    }
    window.speechSynthesis.speak(utt)
  }

  // ── Text input fallback ─────────────────────────────────────────────────────

  const handleSend = () => {
    const cmd = inputText.trim()
    if (!cmd) return
    setInputText('')
    processCommand(cmd)
  }

  // ── Orb click ───────────────────────────────────────────────────────────────

  const handleOrbClick = () => {
    if (state === S.ERROR) { initSession(); return }
    if (state === S.LISTENING) { stopListening(); setState(S.READY); return }
    if (state === S.READY) { startListening(); return }
    if (state === S.SPEAKING) {
      window.speechSynthesis?.cancel()
      setState(S.READY)
      setTimeout(startListening, 300)
    }
  }

  // ── Close ───────────────────────────────────────────────────────────────────

  const handleClose = async () => {
    stopListening()
    window.speechSynthesis?.cancel()
    if (sessionId) stopOtisSession(sessionId).catch(() => {})
    onClose()
  }

  const orb = ORB[state] || ORB[S.IDLE]
  const showRings = state === S.LISTENING || state === S.SPEAKING

  return (
    <>
      {/* Keyframes */}
      <style>{`
        @keyframes ot-breathe {
          0%,100%{transform:scale(1);opacity:.88}
          50%{transform:scale(1.04);opacity:1}
        }
        @keyframes ot-listen {
          0%{transform:scale(1);filter:brightness(1)}
          20%{transform:scale(1.07);filter:brightness(1.12)}
          50%{transform:scale(1.03);filter:brightness(1.18)}
          80%{transform:scale(1.09);filter:brightness(1.12)}
          100%{transform:scale(1);filter:brightness(1)}
        }
        @keyframes ot-spin {
          0%{filter:hue-rotate(0deg) brightness(1.1)}
          100%{filter:hue-rotate(360deg) brightness(1.1)}
        }
        @keyframes ot-speak {
          0%,100%{transform:scale(1)}
          30%{transform:scale(1.06)}
          65%{transform:scale(0.96)}
        }
        @keyframes ot-ring1 {
          0%,100%{transform:scale(1);opacity:.5}
          50%{transform:scale(1.45);opacity:0}
        }
        @keyframes ot-ring2 {
          0%,100%{transform:scale(1);opacity:.3}
          50%{transform:scale(1.8);opacity:0}
        }
        .ot-input::placeholder{color:rgba(255,255,255,0.3)}
        .ot-input:focus{outline:none;border-color:rgba(255,255,255,0.25)!important}
        .ot-scroll::-webkit-scrollbar{width:3px}
        .ot-scroll::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.15);border-radius:2px}
      `}</style>

      {/* Widget container */}
      <div style={{
        position: 'fixed',
        bottom: '32px',
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 9999,
        width: 'min(400px, calc(100vw - 32px))',
        background: 'rgba(8, 8, 18, 0.93)',
        backdropFilter: 'blur(28px)',
        WebkitBackdropFilter: 'blur(28px)',
        borderRadius: '32px',
        border: '1px solid rgba(255,255,255,0.09)',
        boxShadow: `0 32px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04), 0 0 40px ${orb.glow}`,
        transition: 'box-shadow 0.6s ease',
        fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif',
      }}>

        {/* ── Header ──────────────────────────────────────────────────────── */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 20px 0',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{
              fontSize: '13px',
              fontWeight: '700',
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              background: 'linear-gradient(135deg, #60a5fa 0%, #a78bfa 50%, #f472b6 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}>OTIS</span>
            <span style={{
              padding: '2px 8px',
              borderRadius: '100px',
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.1)',
              fontSize: '10px',
              color: 'rgba(255,255,255,0.4)',
              fontWeight: '500',
              letterSpacing: '0.05em',
            }}>Voice AI</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button
              onClick={() => setShowHistory(h => !h)}
              title={showHistory ? 'Hide history' : 'Show history'}
              style={{
                padding: '5px 10px',
                borderRadius: '10px',
                background: 'rgba(255,255,255,0.07)',
                border: '1px solid rgba(255,255,255,0.09)',
                color: 'rgba(255,255,255,0.45)',
                fontSize: '11px',
                cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: '4px',
                transition: 'all 0.15s',
              }}
            >
              {showHistory ? <ChevronDown size={12} /> : <ChevronUp size={12} />}
              {history.length > 0 ? `${Math.floor(history.length / 2)} turns` : 'History'}
            </button>
            <button
              onClick={handleClose}
              style={{
                width: '28px', height: '28px',
                borderRadius: '50%',
                background: 'rgba(255,255,255,0.08)',
                border: '1px solid rgba(255,255,255,0.1)',
                color: 'rgba(255,255,255,0.5)',
                cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'all 0.15s',
              }}
            >
              <X size={13} />
            </button>
          </div>
        </div>

        {/* ── Orb + Status ─────────────────────────────────────────────────── */}
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '28px 24px 20px',
        }}>
          {/* Orb with rings */}
          <div style={{ position: 'relative', marginBottom: '22px' }}>
            {showRings && (
              <>
                <div style={{
                  position: 'absolute', inset: '-14px', borderRadius: '50%',
                  background: orb.glow,
                  animation: `ot-ring1 ${parseFloat(orb.dur) * 1.5}s ease-out infinite`,
                  pointerEvents: 'none',
                }} />
                <div style={{
                  position: 'absolute', inset: '-28px', borderRadius: '50%',
                  background: orb.glow,
                  animation: `ot-ring2 ${parseFloat(orb.dur) * 1.5}s ease-out infinite 0.55s`,
                  pointerEvents: 'none',
                }} />
              </>
            )}

            {/* Main orb */}
            <div
              onClick={handleOrbClick}
              title={state === S.READY ? 'Click to speak' : state === S.LISTENING ? 'Click to stop' : ''}
              style={{
                width: '92px',
                height: '92px',
                borderRadius: '50%',
                background: orb.grad,
                animation: `${orb.anim} ${orb.dur} ease-in-out infinite`,
                cursor: (state === S.READY || state === S.LISTENING || state === S.SPEAKING || state === S.ERROR) ? 'pointer' : 'default',
                boxShadow: `0 0 28px ${orb.glow}, 0 0 56px ${orb.glow}`,
                position: 'relative',
                overflow: 'hidden',
                transition: 'box-shadow 0.4s ease',
                userSelect: 'none',
              }}
            >
              {/* Specular highlight */}
              <div style={{
                position: 'absolute', top: '14%', left: '18%',
                width: '32%', height: '32%',
                borderRadius: '50%',
                background: 'rgba(255,255,255,0.38)',
                filter: 'blur(5px)',
                pointerEvents: 'none',
              }} />
              {/* Mic icon overlay when listening */}
              {state === S.LISTENING && (
                <div style={{
                  position: 'absolute', inset: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  pointerEvents: 'none',
                }}>
                  <Mic size={28} color="rgba(255,255,255,0.9)" strokeWidth={2} />
                </div>
              )}
              {/* Stop icon when processing */}
              {state === S.PROCESSING && (
                <div style={{
                  position: 'absolute', inset: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  pointerEvents: 'none',
                }}>
                  <div style={{
                    width: '22px', height: '22px',
                    border: '2px solid rgba(255,255,255,0.85)',
                    borderTopColor: 'transparent',
                    borderRadius: '50%',
                    animation: 'ot-spin 0.7s linear infinite',
                  }} />
                </div>
              )}
            </div>
          </div>

          {/* Status label */}
          <div style={{
            fontSize: '13px',
            color: 'rgba(255,255,255,0.5)',
            fontWeight: '500',
            letterSpacing: '0.02em',
            marginBottom: transcript || response ? '12px' : '0',
            transition: 'all 0.3s',
          }}>
            {LABEL[state]}
          </div>

          {/* Transcript (what user said) */}
          {transcript && state !== S.IDLE && state !== S.CONNECTING && (
            <div style={{
              maxWidth: '340px',
              textAlign: 'center',
              fontSize: '15px',
              fontWeight: '600',
              color: 'rgba(255,255,255,0.9)',
              padding: '0 8px',
              lineHeight: 1.4,
              marginBottom: '8px',
            }}>
              &ldquo;{transcript}&rdquo;
            </div>
          )}

          {/* Response (what OTIS said) */}
          {response && (
            <div style={{
              maxWidth: '340px',
              textAlign: 'center',
              fontSize: '13px',
              color: 'rgba(255,255,255,0.52)',
              padding: '0 8px',
              lineHeight: 1.55,
              transition: 'all 0.3s',
            }}>
              {response.length > 140 ? response.slice(0, 140) + '…' : response}
            </div>
          )}
        </div>

        {/* ── History panel ──────────────────────────────────────────────────── */}
        {showHistory && history.length > 0 && (
          <div className="ot-scroll" style={{
            maxHeight: '190px',
            overflowY: 'auto',
            padding: '0 16px 8px',
            borderTop: '1px solid rgba(255,255,255,0.06)',
          }}>
            {history.map((msg, i) => (
              <div key={i} style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                marginTop: '10px',
              }}>
                <div style={{
                  maxWidth: '78%',
                  padding: '8px 13px',
                  borderRadius: msg.role === 'user' ? '18px 18px 6px 18px' : '18px 18px 18px 6px',
                  background: msg.role === 'user'
                    ? 'rgba(96,165,250,0.22)'
                    : 'rgba(255,255,255,0.07)',
                  border: '1px solid rgba(255,255,255,0.06)',
                  color: 'rgba(255,255,255,0.82)',
                  fontSize: '12px',
                  lineHeight: 1.45,
                }}>
                  {msg.text}
                </div>
              </div>
            ))}
            <div ref={historyEndRef} />
          </div>
        )}

        {/* ── Text input ─────────────────────────────────────────────────────── */}
        <div style={{
          display: 'flex',
          gap: '8px',
          padding: '12px 16px 20px',
          borderTop: '1px solid rgba(255,255,255,0.06)',
        }}>
          <input
            className="ot-input"
            type="text"
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSend()}
            placeholder="Or type a command…"
            disabled={state === S.PROCESSING || state === S.CONNECTING}
            style={{
              flex: 1,
              padding: '11px 15px',
              borderRadius: '16px',
              background: 'rgba(255,255,255,0.07)',
              border: '1px solid rgba(255,255,255,0.12)',
              color: 'rgba(255,255,255,0.88)',
              fontSize: '13px',
            }}
          />
          <button
            onClick={state === S.LISTENING ? () => { stopListening(); setState(S.READY) } : (inputText.trim() ? handleSend : startListening)}
            disabled={state === S.PROCESSING || state === S.CONNECTING}
            style={{
              width: '44px', height: '44px',
              borderRadius: '14px',
              background: state === S.LISTENING
                ? 'rgba(239,68,68,0.8)'
                : inputText.trim()
                  ? 'linear-gradient(135deg, #3b82f6, #8b5cf6)'
                  : 'rgba(255,255,255,0.09)',
              border: 'none',
              color: 'rgba(255,255,255,0.9)',
              cursor: (state === S.PROCESSING || state === S.CONNECTING) ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.2s',
              flexShrink: 0,
            }}
            title={state === S.LISTENING ? 'Stop' : inputText.trim() ? 'Send' : 'Tap to speak'}
          >
            {state === S.LISTENING ? <MicOff size={18} /> : inputText.trim() ? <Send size={16} /> : <Mic size={18} />}
          </button>
        </div>
      </div>
    </>
  )
}
