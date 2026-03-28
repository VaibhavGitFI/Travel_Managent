import { useState, useEffect, useRef, useCallback } from 'react'
import OtisVoiceWidget from './OtisVoiceWidget'
import useStore from '../../store/useStore'

// ─────────────────────────────────────────────────────────────────────────────
// Wake-word phrases to match (all lower-case, partial-match)
// ─────────────────────────────────────────────────────────────────────────────
const WAKE_PHRASES = ['hey otis', 'otis', 'hi otis', 'hey jarvis', 'jarvis']

// ─────────────────────────────────────────────────────────────────────────────
// Module-level SR guard — Chrome only allows one SpeechRecognition at a time.
// React StrictMode (dev) double-mounts effects, which would start two instances
// simultaneously and cause an endless aborted→restart loop.
// This flag serialises access: if one instance is active, the next backs off.
// ─────────────────────────────────────────────────────────────────────────────
let _srBusy = false

// ─────────────────────────────────────────────────────────────────────────────
// useWakeWord — self-restarting speech-recognition loop
// ─────────────────────────────────────────────────────────────────────────────
// Max consecutive aborts before giving up (Chrome blocking mic)
const MAX_ABORTS = 5

function useWakeWord(phrases, onDetected, enabled) {
  const [listening, setListening]   = useState(false)
  const recRef       = useRef(null)
  const activeRef    = useRef(false)
  const abortCountRef = useRef(0)
  const timerRef     = useRef(null)

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

    // Back off if another instance is already running (StrictMode / widget conflict)
    if (_srBusy) {
      timerRef.current = setTimeout(start, 600)
      return
    }

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) {
      console.warn('[OTIS] SpeechRecognition not available in this browser')
      return
    }

    _srBusy = true
    const rec = new SR()
    rec.continuous      = false
    rec.interimResults  = true
    rec.lang            = 'en-IN'
    rec.maxAlternatives = 3

    rec.onstart = () => {
      abortCountRef.current = 0   // successful start resets the backoff counter
      setListening(true)
      console.log('[OTIS] 👂 wake mic open')
    }

    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        for (let j = 0; j < e.results[i].length; j++) {
          const text = e.results[i][j].transcript.toLowerCase()
          if (phrases.some(p => text.includes(p))) {
            console.log('[OTIS] ✅ wake phrase matched:', text)
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
        console.warn('[OTIS] mic permission denied — stopping wake listener')
        stop()
        return
      }
      if (e.error === 'aborted') {
        abortCountRef.current++
      }
      // onend fires after onerror and handles the restart
    }

    rec.onend = () => {
      _srBusy = false
      recRef.current = null
      setListening(false)

      if (!activeRef.current) return

      const aborts = abortCountRef.current
      if (aborts >= MAX_ABORTS) {
        console.warn('[OTIS] too many consecutive aborts — wake listener paused (tab may be hidden or mic blocked)')
        // Reset counter so it can retry when re-enabled
        abortCountRef.current = 0
        stop()
        return
      }

      // Exponential back-off: 800ms, 1.6s, 3.2s … capped at 8s
      const delay = aborts > 0 ? Math.min(800 * Math.pow(2, aborts - 1), 8000) : 800
      timerRef.current = setTimeout(start, delay)
    }

    recRef.current = rec
    try {
      rec.start()
    } catch (err) {
      console.error('[OTIS] failed to start wake recognition:', err)
      _srBusy = false
      recRef.current = null
      if (activeRef.current) {
        timerRef.current = setTimeout(start, 2000)
      }
    }
  }, [phrases, onDetected, stop])

  // Pause/resume on tab visibility so Chrome doesn't keep aborting in the background
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
    document.addEventListener('visibilitychange', () => {
      document.hidden ? onHidden() : onVisible()
    })
    return () => {
      document.removeEventListener('visibilitychange', () => {
        document.hidden ? onHidden() : onVisible()
      })
    }
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
// OtisLauncher — floating orb that opens the widget on click or voice
// ─────────────────────────────────────────────────────────────────────────────
export default function OtisLauncher() {
  const { auth }  = useStore()
  const [isOpen, setIsOpen] = useState(false)

  const handleDetected = useCallback(() => setIsOpen(true), [])

  // Wake word active when logged in and widget is closed
  const wakeEnabled = auth.isLoggedIn && !isOpen
  const listening   = useWakeWord(WAKE_PHRASES, handleDetected, wakeEnabled)

  if (!auth.isLoggedIn) return null

  return (
    <>
      {!isOpen && (
        <>
          <style>{`
            @keyframes otl-ring  { 0%,100%{transform:scale(1);opacity:.55} 50%{transform:scale(1.5);opacity:0} }
            @keyframes otl-ring2 { 0%,100%{transform:scale(1);opacity:.3}  50%{transform:scale(1.9);opacity:0} }
            @keyframes otl-glow  { 0%,100%{opacity:.85} 50%{opacity:1} }
            .otl-btn:hover { transform:scale(1.08)!important }
            .otl-btn:hover .otl-label { opacity:1!important; transform:translateX(-4px)!important }
          `}</style>

          <div style={{ position:'fixed', bottom:'100px', right:'28px', zIndex:9998 }}>

            {/* Pulsing rings — visible only while mic is open */}
            {listening && (
              <>
                <div style={{ position:'absolute', inset:'-10px', borderRadius:'50%', background:'rgba(167,139,250,0.35)', animation:'otl-ring 2s ease-out infinite', pointerEvents:'none' }} />
                <div style={{ position:'absolute', inset:'-22px', borderRadius:'50%', background:'rgba(96,165,250,0.2)',  animation:'otl-ring2 2s ease-out infinite 0.7s', pointerEvents:'none' }} />
              </>
            )}

            {/* Orb button */}
            <button
              className="otl-btn"
              onClick={() => setIsOpen(true)}
              aria-label="Open OTIS Voice Assistant"
              title={listening ? 'Say "Hey Otis" or click' : 'Open OTIS'}
              style={{
                width:'56px', height:'56px', borderRadius:'50%',
                border:'1.5px solid rgba(255,255,255,0.15)',
                cursor:'pointer', position:'relative', overflow:'hidden',
                background:'radial-gradient(circle at 32% 30%,rgba(96,165,250,0.95),transparent 52%),radial-gradient(circle at 68% 28%,rgba(167,139,250,0.9),transparent 52%),radial-gradient(circle at 50% 78%,rgba(244,114,182,0.85),transparent 48%),#0f0a2e',
                boxShadow:'0 0 20px rgba(167,139,250,0.4),0 8px 24px rgba(0,0,0,0.4)',
                animation:'otl-glow 3s ease-in-out infinite',
                transition:'transform 0.2s ease,box-shadow 0.2s ease',
              }}
            >
              <div style={{ position:'absolute', top:'14%', left:'18%', width:'30%', height:'30%', borderRadius:'50%', background:'rgba(255,255,255,0.4)', filter:'blur(4px)', pointerEvents:'none' }} />
              <div style={{ position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center', fontFamily:'-apple-system,BlinkMacSystemFont,"SF Pro Display",sans-serif', fontSize:'9px', fontWeight:'800', letterSpacing:'0.15em', color:'rgba(255,255,255,0.88)', textTransform:'uppercase' }}>
                OTIS
              </div>
            </button>

            {/* Hover label */}
            <div className="otl-label" style={{ position:'absolute', right:'64px', top:'50%', transform:'translateY(-50%)', whiteSpace:'nowrap', padding:'5px 10px', borderRadius:'10px', background:'rgba(8,8,18,0.9)', backdropFilter:'blur(12px)', border:'1px solid rgba(255,255,255,0.1)', color:'rgba(255,255,255,0.7)', fontSize:'11px', fontWeight:'500', opacity:0, transition:'opacity 0.2s,transform 0.2s', pointerEvents:'none', fontFamily:'-apple-system,BlinkMacSystemFont,sans-serif' }}>
              {listening ? 'Say "Hey Otis"' : 'Open OTIS'}
            </div>
          </div>
        </>
      )}

      {isOpen && <OtisVoiceWidget onClose={() => setIsOpen(false)} />}
    </>
  )
}
