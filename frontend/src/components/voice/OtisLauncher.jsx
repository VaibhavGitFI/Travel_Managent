import { useState, useEffect, useRef, useCallback } from 'react'
import OtisVoiceWidget from './OtisVoiceWidget'
import useStore from '../../store/useStore'

const WAKE_PHRASES = ['hey otis', 'otis', 'ey otis', 'hi otis']

/**
 * OTIS Launcher — Siri-style floating orb button.
 *
 * • Sits bottom-right of the screen as a gradient orb
 * • Browser-based wake word detection ("Hey Otis")
 * • Opens the Siri-like voice widget on click or wake word
 */
export default function OtisLauncher() {
  const { auth } = useStore()
  const [isOpen, setIsOpen] = useState(false)
  const [wakeListening, setWakeListening] = useState(false)
  const recognitionRef = useRef(null)
  const restartTimerRef = useRef(null)

  // ── Wake word detection ───────────────────────────────────────────────────
  const stopWake = useCallback(() => {
    if (restartTimerRef.current) { clearTimeout(restartTimerRef.current); restartTimerRef.current = null }
    if (recognitionRef.current) {
      try { recognitionRef.current.stop() } catch {}
      recognitionRef.current = null
    }
    setWakeListening(false)
  }, [])

  const startWake = useCallback(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return

    const rec = new SR()
    rec.continuous = true
    rec.interimResults = true
    rec.lang = 'en-IN'
    rec.maxAlternatives = 3

    rec.onstart = () => setWakeListening(true)

    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        for (let j = 0; j < e.results[i].length; j++) {
          const t = e.results[i][j].transcript.toLowerCase().trim()
          if (WAKE_PHRASES.some(p => t.includes(p))) {
            setIsOpen(true)
            return
          }
        }
      }
    }

    rec.onerror = (e) => {
      if (e.error !== 'no-speech' && e.error !== 'aborted') {
        setWakeListening(false)
      }
    }

    rec.onend = () => {
      if (recognitionRef.current && !isOpen) {
        restartTimerRef.current = setTimeout(() => {
          try { rec.start() } catch {}
        }, 600)
      }
    }

    recognitionRef.current = rec
    try { rec.start() } catch {}
  }, [isOpen])

  useEffect(() => {
    if (!auth.isLoggedIn || isOpen) { stopWake(); return }
    const t = setTimeout(() => startWake(), 2000)
    return () => { clearTimeout(t); stopWake() }
  }, [auth.isLoggedIn, isOpen, startWake, stopWake])

  useEffect(() => () => stopWake(), [stopWake])

  if (!auth.isLoggedIn) return null

  return (
    <>
      {/* Launcher button */}
      {!isOpen && (
        <>
          <style>{`
            @keyframes otl-ring {
              0%,100%{transform:scale(1);opacity:.55}
              50%{transform:scale(1.5);opacity:0}
            }
            @keyframes otl-ring2 {
              0%,100%{transform:scale(1);opacity:.3}
              50%{transform:scale(1.9);opacity:0}
            }
            @keyframes otl-glow {
              0%,100%{opacity:.85}
              50%{opacity:1}
            }
            .otl-btn:hover{transform:scale(1.08)!important}
            .otl-btn:hover .otl-label{opacity:1!important;transform:translateX(-4px)!important}
          `}</style>

          <div style={{ position: 'fixed', bottom: '100px', right: '28px', zIndex: 9998 }}>
            {/* Pulsing rings (only when wake listening) */}
            {wakeListening && (
              <>
                <div style={{
                  position: 'absolute', inset: '-10px', borderRadius: '50%',
                  background: 'rgba(167,139,250,0.35)',
                  animation: 'otl-ring 2s ease-out infinite',
                  pointerEvents: 'none',
                }} />
                <div style={{
                  position: 'absolute', inset: '-22px', borderRadius: '50%',
                  background: 'rgba(96,165,250,0.2)',
                  animation: 'otl-ring2 2s ease-out infinite 0.7s',
                  pointerEvents: 'none',
                }} />
              </>
            )}

            {/* The orb button */}
            <button
              className="otl-btn"
              onClick={() => setIsOpen(true)}
              aria-label="Open OTIS Voice Assistant"
              title={wakeListening ? 'Say "Hey Otis" or click' : 'Open OTIS'}
              style={{
                width: '56px',
                height: '56px',
                borderRadius: '50%',
                border: '1.5px solid rgba(255,255,255,0.15)',
                cursor: 'pointer',
                position: 'relative',
                overflow: 'hidden',
                background: 'radial-gradient(circle at 32% 30%, rgba(96,165,250,0.95), transparent 52%), radial-gradient(circle at 68% 28%, rgba(167,139,250,0.9), transparent 52%), radial-gradient(circle at 50% 78%, rgba(244,114,182,0.85), transparent 48%), #0f0a2e',
                boxShadow: '0 0 20px rgba(167,139,250,0.4), 0 8px 24px rgba(0,0,0,0.4)',
                animation: 'otl-glow 3s ease-in-out infinite',
                transition: 'transform 0.2s ease, box-shadow 0.2s ease',
              }}
            >
              {/* Specular */}
              <div style={{
                position: 'absolute', top: '14%', left: '18%',
                width: '30%', height: '30%',
                borderRadius: '50%',
                background: 'rgba(255,255,255,0.4)',
                filter: 'blur(4px)',
                pointerEvents: 'none',
              }} />

              {/* OTIS text inside orb */}
              <div style={{
                position: 'absolute', inset: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif',
                fontSize: '9px',
                fontWeight: '800',
                letterSpacing: '0.15em',
                color: 'rgba(255,255,255,0.88)',
                textTransform: 'uppercase',
              }}>
                OTIS
              </div>
            </button>

            {/* Tooltip label */}
            <div className="otl-label" style={{
              position: 'absolute',
              right: '64px',
              top: '50%',
              transform: 'translateY(-50%)',
              whiteSpace: 'nowrap',
              padding: '5px 10px',
              borderRadius: '10px',
              background: 'rgba(8,8,18,0.9)',
              backdropFilter: 'blur(12px)',
              border: '1px solid rgba(255,255,255,0.1)',
              color: 'rgba(255,255,255,0.7)',
              fontSize: '11px',
              fontWeight: '500',
              opacity: 0,
              transition: 'opacity 0.2s, transform 0.2s',
              pointerEvents: 'none',
              fontFamily: '-apple-system, BlinkMacSystemFont, sans-serif',
            }}>
              {wakeListening ? 'Say "Hey Otis"' : 'Open OTIS'}
            </div>
          </div>
        </>
      )}

      {/* Voice Widget */}
      {isOpen && <OtisVoiceWidget onClose={() => setIsOpen(false)} />}
    </>
  )
}
