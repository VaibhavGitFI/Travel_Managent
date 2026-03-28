import { useState, useEffect, useRef, useCallback } from 'react'
import OtisVoiceWidget from './OtisVoiceWidget'
import useStore from '../../store/useStore'

// ─────────────────────────────────────────────────────────────────────────────
// Wake-word phrases (all lower-case, partial-match)
// ─────────────────────────────────────────────────────────────────────────────
const WAKE_PHRASES = ['hey jarvis', 'jarvis', 'hey otis', 'hi otis', 'otis']

// ─────────────────────────────────────────────────────────────────────────────
// Module-level SR guard — Chrome only allows one SpeechRecognition at a time.
// ─────────────────────────────────────────────────────────────────────────────
let _srBusy = false
const MAX_ABORTS = 5

// ─────────────────────────────────────────────────────────────────────────────
// useWakeWord — self-restarting speech-recognition loop (unchanged)
// ─────────────────────────────────────────────────────────────────────────────
function useWakeWord(phrases, onDetected, enabled) {
  const [listening, setListening] = useState(false)
  const recRef        = useRef(null)
  const activeRef     = useRef(false)
  const abortCountRef = useRef(0)
  const timerRef      = useRef(null)

  const clearTimer = () => {
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null }
  }

  const stop = useCallback(() => {
    activeRef.current = false
    setListening(false)
    clearTimer()
    if (recRef.current) {
      try { recRef.current.abort() } catch {}
      recRef.current = null
    }
    _srBusy = false
  }, [])

  const start = useCallback(() => {
    if (!activeRef.current) return
    if (recRef.current)     return
    if (_srBusy) { timerRef.current = setTimeout(start, 600); return }

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) { console.warn('[Jarvis] SpeechRecognition not available'); return }

    _srBusy = true
    const rec = new SR()
    rec.continuous      = false
    rec.interimResults  = true
    rec.lang            = 'en-IN'
    rec.maxAlternatives = 3

    rec.onstart = () => {
      abortCountRef.current = 0
      setListening(true)
      console.log('[Jarvis] 👂 wake mic open')
    }

    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        for (let j = 0; j < e.results[i].length; j++) {
          const text = e.results[i][j].transcript.toLowerCase()
          if (phrases.some(p => text.includes(p))) {
            console.log('[Jarvis] ✅ wake phrase matched:', text)
            stop()
            onDetected()
            return
          }
        }
      }
    }

    rec.onerror = (e) => {
      _srBusy = false
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        console.warn('[Jarvis] mic permission denied — stopping wake listener')
        stop()
        return
      }
      if (e.error === 'aborted') abortCountRef.current++
    }

    rec.onend = () => {
      _srBusy = false
      recRef.current = null
      setListening(false)
      if (!activeRef.current) return
      const aborts = abortCountRef.current
      if (aborts >= MAX_ABORTS) {
        console.warn('[Jarvis] too many consecutive aborts — wake listener paused')
        abortCountRef.current = 0
        stop()
        return
      }
      const delay = aborts > 0 ? Math.min(800 * Math.pow(2, aborts - 1), 8000) : 800
      timerRef.current = setTimeout(start, delay)
    }

    recRef.current = rec
    try {
      rec.start()
    } catch (err) {
      console.error('[Jarvis] failed to start wake recognition:', err)
      _srBusy = false
      recRef.current = null
      if (activeRef.current) timerRef.current = setTimeout(start, 2000)
    }
  }, [phrases, onDetected, stop])

  // Pause on tab hidden, resume on tab visible
  useEffect(() => {
    const onVisible = () => {
      if (enabled && activeRef.current && !recRef.current) {
        abortCountRef.current = 0
        clearTimer()
        timerRef.current = setTimeout(start, 500)
      }
    }
    const onHidden = () => {
      clearTimer()
      if (recRef.current) {
        try { recRef.current.abort() } catch {}
        recRef.current = null
      }
      _srBusy = false
      setListening(false)
    }
    const handler = () => { document.hidden ? onHidden() : onVisible() }
    document.addEventListener('visibilitychange', handler)
    return () => document.removeEventListener('visibilitychange', handler)
  }, [enabled, start])

  useEffect(() => {
    if (enabled) {
      abortCountRef.current = 0
      activeRef.current = true
      start()
    } else {
      stop()
    }
    return stop
  }, [enabled, start, stop])

  return listening
}

// ─────────────────────────────────────────────────────────────────────────────
// OtisLauncher — Siri-style JARVIS floating launcher
// ─────────────────────────────────────────────────────────────────────────────
export default function OtisLauncher() {
  const { auth, theme } = useStore()
  const isDark = theme === 'dark'
  const [isOpen, setIsOpen] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [openMode, setOpenMode] = useState('manual')

  const handleDetected = useCallback(() => {
    setOpenMode('wake')
    setIsOpen(true)
  }, [])

  const wakeEnabled = auth.isLoggedIn && !isOpen
  const listening   = useWakeWord(WAKE_PHRASES, handleDetected, wakeEnabled)

  if (!auth.isLoggedIn) return null

  return (
    <>
      <style>{`
        @keyframes jarvis-ring {
          0%,100% { transform: scale(1); opacity: 0.7; }
          50%     { transform: scale(1.5); opacity: 0; }
        }
        @keyframes jarvis-fade-in {
          from { opacity: 0; transform: translateY(-50%) translateX(6px); }
          to   { opacity: 1; transform: translateY(-50%) translateX(0); }
        }
        @keyframes jarvis-launcher-glow {
          0%,100% { box-shadow: ${isDark
            ? '0 4px 20px rgba(76,201,240,0.3), 0 2px 8px rgba(0,0,0,0.4)'
            : '0 4px 16px rgba(26,86,219,0.35), 0 2px 6px rgba(0,0,0,0.12)'}; }
          50%     { box-shadow: ${isDark
            ? '0 4px 30px rgba(76,201,240,0.5), 0 2px 8px rgba(0,0,0,0.4)'
            : '0 4px 24px rgba(14,165,233,0.6), 0 2px 6px rgba(0,0,0,0.12)'}; }
        }
      `}</style>

      {/* ── Launcher button ───────────────────────────────────────────────── */}
      {!isOpen && (
        <div style={{
          position: 'fixed',
          bottom: '28px',
          right: '28px',
          zIndex: 9998,
          width: '56px',
          height: '56px',
        }}>
          {/* Pulsing rings — only while wake mic is open */}
          {listening && (
            <>
              <div style={{
                position: 'absolute',
                inset: '-10px',
                borderRadius: '50%',
                background: isDark ? 'rgba(76,201,240,0.25)' : 'rgba(14,165,233,0.2)',
                animation: 'jarvis-ring 2s ease-out infinite',
                pointerEvents: 'none',
              }} />
              <div style={{
                position: 'absolute',
                inset: '-22px',
                borderRadius: '50%',
                background: isDark ? 'rgba(76,201,240,0.15)' : 'rgba(26,86,219,0.12)',
                animation: 'jarvis-ring 2s 0.6s ease-out infinite',
                pointerEvents: 'none',
              }} />
            </>
          )}

          {/* Main button */}
          <button
            onClick={() => {
              setOpenMode('manual')
              setIsOpen(true)
            }}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
            aria-label="Open Jarvis Voice Assistant"
            title={listening ? 'Say "Hey Jarvis" or click' : 'Open Jarvis'}
            style={{
              width: '56px', height: '56px',
              borderRadius: '50%',
              border: isDark ? '2px solid rgba(255,255,255,0.15)' : '2px solid rgba(255,255,255,0.5)',
              cursor: 'pointer',
              position: 'relative',
              overflow: 'hidden',
              background: 'linear-gradient(135deg, #1a56db 0%, #0ea5e9 50%, #4CC9F0 100%)',
              animation: 'jarvis-launcher-glow 3s ease-in-out infinite',
              transform: hovered ? 'scale(1.06)' : 'scale(1)',
              transition: 'transform 0.15s ease',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            {/* Specular highlight */}
            <div style={{
              position: 'absolute',
              top: 0, left: 0,
              width: '100%', height: '100%',
              background: 'radial-gradient(circle at 30% 30%, rgba(255,255,255,0.3) 0%, transparent 60%)',
              filter: 'blur(4px)',
              pointerEvents: 'none',
            }} />

            {/* JARVIS wordmark */}
            <span style={{
              fontSize: '9px',
              fontWeight: 800,
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: 'rgba(255,255,255,0.95)',
              fontFamily: "'Inter', system-ui, sans-serif",
              position: 'relative',
              zIndex: 1,
            }}>
              JARVIS
            </span>
          </button>

          {/* Hover tooltip */}
          {hovered && (
            <div style={{
              position: 'absolute',
              right: '64px',
              top: '50%',
              transform: 'translateY(-50%)',
              whiteSpace: 'nowrap',
              pointerEvents: 'none',
              padding: '6px 12px',
              borderRadius: '10px',
              fontSize: '12px',
              fontWeight: 500,
              fontFamily: "'Inter', system-ui, sans-serif",
              background: isDark ? '#0d2244' : '#ffffff',
              border: `1px solid ${isDark ? '#1e3a72' : '#e2e8f0'}`,
              color: isDark ? '#f0f1ed' : '#0f172a',
              boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
              animation: 'jarvis-fade-in 0.15s ease',
            }}>
              {listening ? 'Jarvis is listening…' : 'Say "Hey Jarvis"'}
            </div>
          )}
        </div>
      )}

      {/* ── Widget panel ─────────────────────────────────────────────────────── */}
      {isOpen && (
        <OtisVoiceWidget
          autoStart
          entryMode={openMode}
          onClose={() => {
            setIsOpen(false)
            setOpenMode('manual')
          }}
        />
      )}
    </>
  )
}
