import { useState, useEffect, useRef, useCallback } from 'react'
import { X, Mic, MicOff, Send, ChevronDown, ChevronUp } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  getOtisStatus,
  startOtisSession,
  stopOtisSession,
  sendOtisCommandRest,
  voiceCommand,
} from '../../api/otis'
import useStore from '../../store/useStore'

// ── State machine ──────────────────────────────────────────────────────────────
const S = {
  IDLE:       'idle',
  CONNECTING: 'connecting',
  READY:      'ready',
  LISTENING:  'listening',
  PROCESSING: 'processing',
  SPEAKING:   'speaking',
  ERROR:      'error',
}

const LABEL = {
  [S.IDLE]:       'Say "Hey Jarvis" or tap the mic',
  [S.CONNECTING]: 'Connecting…',
  [S.READY]:      'Hey, I am Jarvis. How can I help?',
  [S.LISTENING]:  'Listening…',
  [S.PROCESSING]: 'Thinking…',
  [S.SPEAKING]:   'Speaking…',
  [S.ERROR]:      'Something went wrong — tap to retry',
}

// ── Audio MIME type detection (same as Chat page) ─────────────────────────────
const AUDIO_MIME_TYPES = [
  'audio/webm;codecs=opus', 'audio/webm',
  'audio/ogg;codecs=opus',  'audio/ogg',
  'audio/mp4',
]
function getSupportedMimeType() {
  if (typeof MediaRecorder === 'undefined') return null
  for (const mime of AUDIO_MIME_TYPES) {
    if (MediaRecorder.isTypeSupported(mime)) return mime
  }
  return null
}

// ── Browser TTS voice picker (fallback when ElevenLabs unavailable) ───────────
const VOICE_PRIORITY = [
  v => v.lang === 'hi-IN',
  v => v.lang === 'en-IN',
  v => v.name.toLowerCase().includes('india'),
  v => v.name.toLowerCase().includes('hindi'),
  v => v.name === 'Google UK English Male',
  v => v.name === 'Daniel',
  v => v.lang === 'en-GB',
  v => v.lang === 'en-US',
  v => v.lang.startsWith('en'),
]
function pickFallbackVoice() {
  const voices = window.speechSynthesis?.getVoices?.() || []
  for (const test of VOICE_PRIORITY) {
    const v = voices.find(test)
    if (v) return v
  }
  return null
}

// ── Waveform bar helpers ───────────────────────────────────────────────────────
function getBarColor(state, i, isDark) {
  if (state === S.IDLE)       return isDark ? 'rgba(255,255,255,0.18)' : '#cbd5e1'
  if (state === S.CONNECTING) return 'rgba(119,141,169,0.6)'
  if (state === S.READY)      return isDark ? 'rgba(76,201,240,0.3)' : 'rgba(26,86,219,0.4)'
  if (state === S.ERROR)      return 'rgba(239,68,68,0.5)'
  if (state === S.PROCESSING) return isDark ? '#fbbf24' : '#d97706'
  if (state === S.LISTENING) {
    if (i < 4)  return '#1a56db'
    if (i < 8)  return '#0ea5e9'
    if (i < 12) return '#4CC9F0'
    if (i < 16) return '#059669'
    if (i < 20) return '#10b981'
    if (i < 24) return '#a78bfa'
    return '#1a56db'
  }
  if (state === S.SPEAKING) {
    if (i < 7)  return '#0ea5e9'
    if (i < 14) return '#4CC9F0'
    if (i < 21) return '#059669'
    return '#1a56db'
  }
  return isDark ? 'rgba(255,255,255,0.18)' : '#cbd5e1'
}
function barDuration(i) {
  return `${(0.4 + (i % 7) * 0.043).toFixed(3)}s`
}

// ── Component ──────────────────────────────────────────────────────────────────
export default function OtisVoiceWidget({ onClose, autoStart = false, entryMode = 'manual' }) {
  const { theme } = useStore()
  const isDark = theme === 'dark'

  // ── State (exact same names as original) ────────────────────────────────────
  const [state, setState]           = useState(S.IDLE)
  const [sessionId, setSessionId]   = useState(null)
  const [transcript, setTranscript] = useState('')
  const [response, setResponse]     = useState('')
  const [history, setHistory]       = useState([])
  const [showHistory, setShowHistory] = useState(false)
  const [inputText, setInputText]   = useState('')
  const [language, setLanguage]     = useState('en-IN')
  const [latencyMs, setLatencyMs]   = useState(null)

  // ── Refs — originals (unchanged) ────────────────────────────────────────────
  const stateRef       = useRef(S.IDLE)
  const sessionIdRef   = useRef(null)
  const historyEndRef  = useRef(null)

  // ── Refs — new (MediaRecorder + ElevenLabs) ──────────────────────────────────
  const mediaRecRef     = useRef(null)   // MediaRecorder instance
  const chunksRef       = useRef([])     // audio data chunks
  const streamRef       = useRef(null)   // MediaStream
  const analyserRef     = useRef(null)   // { audioCtx, analyser }
  const animFrameRef    = useRef(null)   // requestAnimationFrame id
  const silenceTimerRef = useRef(null)   // silence timeout id
  const audioRef        = useRef(null)   // HTMLAudioElement (ElevenLabs playback)
  const cancelledRef    = useRef(false)  // true = user manually stopped → discard audio
  const bootedRef       = useRef(false)
  const cleanupTimerRef = useRef(null)
  const autoListenPendingRef = useRef(Boolean(autoStart))
  const followUpPendingRef = useRef(false)
  const followUpTimerRef = useRef(null)
  const wakeWordRef     = useRef(null)   // SpeechRecognition for wake word
  const audioLevelRef   = useRef(0)      // live audio level 0-100
  const isWidgetOpenRef = useRef(true)   // always open in widget mode

  // Keep refs in sync
  useEffect(() => { stateRef.current = state },       [state])
  useEffect(() => { sessionIdRef.current = sessionId }, [sessionId])
  useEffect(() => { autoListenPendingRef.current = Boolean(autoStart) }, [autoStart])

  // Auto-scroll history
  useEffect(() => {
    if (showHistory) historyEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history, showHistory])

  // Bootstrap session on mount, clean up on unmount
  useEffect(() => {
    if (cleanupTimerRef.current) {
      clearTimeout(cleanupTimerRef.current)
      cleanupTimerRef.current = null
    }

    if (!bootedRef.current) {
      bootedRef.current = true
      initSession()
    }

    return () => {
      // Delay destructive cleanup by one tick so React StrictMode's
      // dev-only mount/unmount simulation does not double-start OTIS.
      cleanupTimerRef.current = setTimeout(() => {
        bootedRef.current = false
        followUpPendingRef.current = false
        if (followUpTimerRef.current) {
          clearTimeout(followUpTimerRef.current)
          followUpTimerRef.current = null
        }
        stopListening(true)
        stopAudio()
        if (window.speechSynthesis) window.speechSynthesis.cancel()
        if (sessionIdRef.current) stopOtisSession(sessionIdRef.current).catch(() => {})
      }, 0)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Wake word detection using browser SpeechRecognition
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) return

    const sr = new SpeechRecognition()
    sr.continuous = true
    sr.interimResults = true
    sr.lang = 'en-IN'   // Indian English as default
    wakeWordRef.current = sr

    sr.onresult = (event) => {
      const last = event.results[event.results.length - 1]
      const heard = last[0].transcript.toLowerCase().trim()
      const wakeWords = ['hey jarvis', 'ok jarvis', 'jarvis', 'hey otis', 'otis']
      const triggered = wakeWords.some(w => heard.includes(w))
      if (triggered && stateRef.current === S.READY) {
        sr.stop()
        setTimeout(() => startListening(), 200)
      }
    }
    sr.onerror = () => {}
    sr.onend = () => {
      // Restart continuous wake word listening
      if (stateRef.current === S.READY || stateRef.current === S.IDLE) {
        try { sr.start() } catch {}
      }
    }

    // Start wake word listening
    try { sr.start() } catch {}

    return () => {
      try { sr.stop() } catch {}
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Session init ─────────────────────────────────────────────────────────────
  const initSession = async () => {
    setState(S.CONNECTING)
    try {
      const session = await startOtisSession()
      const welcome = 'Hey, I am Jarvis. How can I help?'
      setSessionId(session.session_id)
      setState(S.READY)
      setTimeout(startWakeWord, 500)
      setTranscript('')
      setResponse(welcome)
      speakAndReturn(welcome)
    } catch {
      try {
        const status = await getOtisStatus()
        toast.error(status.reason || 'Jarvis unavailable')
      } catch {
        toast.error('Jarvis unavailable')
      }
      setState(S.ERROR)
    }
  }

  // ── ElevenLabs audio helpers ─────────────────────────────────────────────────
  const stopAudio = () => {
    if (audioRef.current) {
      try { audioRef.current.pause() } catch {}
      audioRef.current = null
    }
  }

  const playBase64Audio = useCallback((b64, mime = 'audio/mpeg') => {
    stopAudio()
    try {
      const byteString = atob(b64)
      const ab = new ArrayBuffer(byteString.length)
      const ia = new Uint8Array(ab)
      for (let i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i)
      const blob = new Blob([ab], { type: mime })
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audioRef.current = audio
      audio.onended = () => { URL.revokeObjectURL(url); audioRef.current = null; done() }
      audio.onerror = () => { URL.revokeObjectURL(url); audioRef.current = null; done() }
      audio.play().catch(() => done())
    } catch { done() }

    function done() {
      const shouldAutoStart = autoListenPendingRef.current
      const shouldFollowUp = followUpPendingRef.current
      setState(S.READY)
      if (shouldAutoStart || shouldFollowUp) {
        if (followUpTimerRef.current) clearTimeout(followUpTimerRef.current)
        followUpTimerRef.current = setTimeout(() => {
          autoListenPendingRef.current = false
          followUpPendingRef.current = false
          followUpTimerRef.current = null
          startListening()
        }, 600)
      }
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── MediaRecorder helpers ────────────────────────────────────────────────────
  const startWakeWord = useCallback(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return
    try {
      const rec = new SR()
      rec.continuous = true
      rec.interimResults = true
      rec.lang = 'en-IN'
      rec.onresult = (e) => {
        const text = Array.from(e.results).map(r => r[0].transcript).join(' ').toLowerCase()
        if (text.includes('hey jarvis') || text.includes('jarvis') || text.includes('hey otis')) {
          rec.stop()
          if (stateRef.current === S.READY || stateRef.current === S.IDLE) {
            startListening()
          }
        }
      }
      rec.onerror = () => { setTimeout(startWakeWord, 3000) }
      rec.onend   = () => {
        if (stateRef.current === S.READY || stateRef.current === S.IDLE) {
          setTimeout(startWakeWord, 1000)
        }
      }
      rec.start()
      wakeWordRef.current = rec
    } catch {}
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * stopListening — halt any active recording.
   * @param {boolean} cancel  true = discard audio (user clicked stop)
   *                          false = process audio (silence detected)
   */
  const stopListening = useCallback((cancel = false) => {
    cancelledRef.current = cancel
    if (animFrameRef.current)    { cancelAnimationFrame(animFrameRef.current); animFrameRef.current = null }
    if (silenceTimerRef.current) { clearTimeout(silenceTimerRef.current); silenceTimerRef.current = null }
    if (mediaRecRef.current) {
      try {
        if (mediaRecRef.current.state === 'recording') mediaRecRef.current.stop()
      } catch {}
    }
  }, [])

  /**
   * startListening — record mic audio → Deepgram transcription → processCommand.
   * Silence detection auto-stops after 1.8 s of quiet (same threshold as Chat page).
   */
  const startListening = useCallback(async () => {
    if ([S.LISTENING, S.PROCESSING, S.CONNECTING].includes(stateRef.current)) return
    autoListenPendingRef.current = false
    followUpPendingRef.current = false
    if (followUpTimerRef.current) {
      clearTimeout(followUpTimerRef.current)
      followUpTimerRef.current = null
    }

    const mimeType = getSupportedMimeType()
    if (!mimeType) {
      toast.error('Voice recording not supported in this browser')
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      })
      streamRef.current = stream

      // AudioContext for silence detection
      const audioCtx  = new (window.AudioContext || window.webkitAudioContext)()
      const source    = audioCtx.createMediaStreamSource(stream)
      const analyser  = audioCtx.createAnalyser()
      analyser.fftSize              = 512
      analyser.smoothingTimeConstant = 0.3
      source.connect(analyser)
      analyserRef.current = { audioCtx, analyser }

      chunksRef.current  = []
      cancelledRef.current = false
      const recorder = new MediaRecorder(stream, { mimeType })

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = async () => {
        // Clean up stream + audio context
        stream.getTracks().forEach(t => t.stop())
        streamRef.current = null
        if (analyserRef.current) {
          analyserRef.current.audioCtx.close().catch(() => {})
          analyserRef.current = null
        }
        if (animFrameRef.current)    { cancelAnimationFrame(animFrameRef.current); animFrameRef.current = null }
        if (silenceTimerRef.current) { clearTimeout(silenceTimerRef.current); silenceTimerRef.current = null }
        mediaRecRef.current = null

        // User clicked cancel — discard
        if (cancelledRef.current) {
          cancelledRef.current = false
          if (stateRef.current === S.LISTENING) setState(S.READY)
          return
        }

        // ── NEW: single all-in-one call ───────────────────────────────────────────
        setState(S.PROCESSING)
        try {
          const blob = new Blob(chunksRef.current, { type: mimeType })
          if (blob.size < 250) {
            setResponse("I didn't catch that. Please ask again.")
            setState(S.READY)
            return
          }
          const result = await voiceCommand(blob, sessionIdRef.current, true)
          if (!result.success) {
            setResponse(result.error || "Couldn't understand — please try again.")
            setState(S.READY)
            return
          }
          // Show transcript immediately
          setTranscript(result.transcript || '')
          setLanguage(result.language || 'en-IN')
          setLatencyMs(result.latency_ms || null)
          if (result.session_id) setSessionId(result.session_id)

          const responseText = result.response || 'Done.'
          setResponse(responseText)
          setHistory(h => [...h, { role: 'user', text: result.transcript }, { role: 'assistant', text: responseText }])
          followUpPendingRef.current = true

          // Play audio if included in response
          if (result.audio_b64) {
            setState(S.SPEAKING)
            playBase64Audio(result.audio_b64, result.audio_mime || 'audio/mpeg')
          } else {
            speakFallback(responseText)
          }
        } catch (err) {
          console.error('[Jarvis] Voice command failed:', err)
          setResponse('Sorry, something went wrong. Please try again.')
          setState(S.READY)
        }
      }

      recorder.onerror = () => {
        stream.getTracks().forEach(t => t.stop())
        streamRef.current = null
        mediaRecRef.current = null
        if (stateRef.current === S.LISTENING) setState(S.READY)
        toast.error('Recording failed')
      }

      mediaRecRef.current = recorder
      recorder.start(200)      // collect chunks every 200 ms
      setState(S.LISTENING)
      setTranscript('')

      // ── Silence detection ─────────────────────────────────────────────────
      const dataArr   = new Uint8Array(analyser.frequencyBinCount)
      let silentSince = 0
      let heardSpeech = false
      const startedAt = Date.now()

      const checkSilence = () => {
        if (!mediaRecRef.current || mediaRecRef.current.state !== 'recording') return
        if (Date.now() - startedAt > 60000) { stopListening(); return }   // 60 s max
        analyser.getByteFrequencyData(dataArr)
        const avg = dataArr.reduce((s, v) => s + v, 0) / dataArr.length
        if (avg >= 12) {
          heardSpeech = true
          silentSince = 0
        } else if (!heardSpeech) {
          if (Date.now() - startedAt > 5000) { stopListening(); return }
        } else {
          if (!silentSince) silentSince = Date.now()
          else if (Date.now() - silentSince > 1000) { stopListening(); return }
        }
        animFrameRef.current = requestAnimationFrame(checkSilence)
      }

      // Give the microphone a moment to stabilize before evaluating silence.
      silenceTimerRef.current = setTimeout(
        () => { animFrameRef.current = requestAnimationFrame(checkSilence) },
        600,
      )

    } catch (err) {
      if ([S.LISTENING, S.CONNECTING].includes(stateRef.current)) setState(S.READY)
      toast.error(err.name === 'NotAllowedError' ? 'Mic access denied' : 'Could not access microphone')
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Command processing ───────────────────────────────────────────────────────
  const processCommand = useCallback(async (command, { fromVoice = false } = {}) => {
    if (!command.trim()) return
    const userText = command.trim()
    setState(S.PROCESSING)
    setTranscript(userText)
    setResponse('')
    setHistory(h => [...h, { role: 'user', text: userText }])

    try {
      const result = await sendOtisCommandRest(userText, sessionIdRef.current)
      const text   = result.response || 'Done.'
      if (result.session_id && result.session_id !== sessionIdRef.current) {
        setSessionId(result.session_id)
      }
      followUpPendingRef.current = fromVoice
      setResponse(text)
      setHistory(h => [...h, { role: 'assistant', text }])
      speakAndReturn(text)
    } catch (err) {
      console.error('[Jarvis] Command failed:', err)
      const errText = 'Sorry, something went wrong. Please try again.'
      followUpPendingRef.current = false
      setResponse(errText)
      setHistory(h => [...h, { role: 'assistant', text: errText }])
      setState(S.READY)
      toast.error('Jarvis command failed')
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const speakFallback = useCallback((text) => {
    setState(S.SPEAKING)
    if (!text || !('speechSynthesis' in window)) { setState(S.READY); return }
    window.speechSynthesis.cancel()
    const done = () => {
      setState(S.READY)
      if (followUpPendingRef.current) {
        followUpPendingRef.current = false
        setTimeout(() => startListening(), 500)
      }
    }
    const utt = new SpeechSynthesisUtterance(text)
    // Prefer Indian English voice
    const voices = window.speechSynthesis.getVoices()
    const indian = voices.find(v => v.lang === 'en-IN') || voices.find(v => v.lang.startsWith('en'))
    if (indian) utt.voice = indian
    utt.lang   = 'en-IN'
    utt.rate   = 0.95
    utt.onend  = done
    utt.onerror = done
    window.speechSynthesis.speak(utt)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * speakAndReturn — kept for backward compat (welcome message, error messages).
   * Routes through speakFallback.
   */
  const speakAndReturn = useCallback(async (text) => {
    speakFallback(text)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Text input fallback ──────────────────────────────────────────────────────
  const handleSend = () => {
    const cmd = inputText.trim()
    if (!cmd) return
    setInputText('')
    processCommand(cmd, { fromVoice: false })
  }

  // ── Waveform click (error → retry, listening → cancel, ready → start mic) ──
  const handleWaveformClick = () => {
    if (state === S.ERROR)     { initSession(); return }
    if (state === S.LISTENING) { stopListening(true); return }   // cancel, discard
    if (state === S.READY)     { startListening(); return }
    if (state === S.SPEAKING)  {
      followUpPendingRef.current = false
      if (followUpTimerRef.current) {
        clearTimeout(followUpTimerRef.current)
        followUpTimerRef.current = null
      }
      stopAudio()
      window.speechSynthesis?.cancel()
      setState(S.READY)
      setTimeout(startListening, 300)
    }
  }

  // ── Close ─────────────────────────────────────────────────────────────────────
  const handleClose = async () => {
    followUpPendingRef.current = false
    if (followUpTimerRef.current) {
      clearTimeout(followUpTimerRef.current)
      followUpTimerRef.current = null
    }
    stopListening(true)
    stopAudio()
    window.speechSynthesis?.cancel()
    if (sessionId) stopOtisSession(sessionId).catch(() => {})
    onClose()
  }

  // ── Waveform renderer ─────────────────────────────────────────────────────────
  const renderWaveform = () => {
    const bars     = Array.from({ length: 28 }, (_, i) => i)
    const isActive = state === S.LISTENING || state === S.SPEAKING

    return (
      <div
        onClick={handleWaveformClick}
        style={{
          height: '72px',
          width: '100%',
          padding: '20px 0 12px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          position: 'relative',
          cursor: [S.READY, S.LISTENING, S.ERROR, S.SPEAKING].includes(state)
            ? 'pointer' : 'default',
        }}
      >
        {isActive && (
          <div style={{
            position: 'absolute', bottom: 0, left: '50%',
            transform: 'translateX(-50%)',
            width: '200px', height: '30px',
            background: isDark
              ? 'radial-gradient(ellipse 200px 30px, rgba(26,86,219,0.35), transparent)'
              : 'radial-gradient(ellipse 200px 30px, rgba(76,201,240,0.25), transparent)',
            pointerEvents: 'none',
          }} />
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: '3.5px' }}>
          {bars.map(i => {
            let anim = 'none', height = '4px'
            // Delay is embedded in the animation shorthand to avoid the
            // React "conflicting shorthand / non-shorthand" warning.
            const d = `${(i * 0.04).toFixed(2)}s`
            const color = getBarColor(state, i, isDark)

            if      (state === S.IDLE)       { anim = `jarvis-idle 3.5s ease-in-out ${d} infinite` }
            else if (state === S.CONNECTING) { anim = `jarvis-connecting 1.2s ease-in-out ${d} infinite` }
            else if (state === S.READY)      { anim = `jarvis-ready 4s ease-in-out ${d} infinite`; height = '5px' }
            else if (state === S.LISTENING)  { anim = `jarvis-bar ${barDuration(i)} ease-in-out ${d} infinite` }
            else if (state === S.SPEAKING)   { anim = `jarvis-bar ${barDuration(i)} ease-in-out ${d} infinite` }
            else if (state === S.PROCESSING) { height = '16px'; anim = `jarvis-shimmer 1.4s ease-in-out ${d} infinite` }
            else if (state === S.ERROR)      { anim = `jarvis-error 2.5s ease-in-out ${d} infinite` }

            return (
              <div key={i} style={{
                width: '3px', height, borderRadius: '2px',
                backgroundColor: color,
                animation: anim,
                transformOrigin: 'bottom center', flexShrink: 0,
              }} />
            )
          })}
        </div>
      </div>
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <>
      <style>{`
        @keyframes jarvis-slide-in {
          from { opacity: 0; transform: translateY(12px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes jarvis-idle {
          0%,100% { height: 4px; } 50% { height: 6px; }
        }
        @keyframes jarvis-connecting {
          0%,100% { height: 4px; } 50% { height: 18px; }
        }
        @keyframes jarvis-ready {
          0%,100% { height: 5px; } 50% { height: 10px; }
        }
        @keyframes jarvis-bar {
          0%,100% { transform: scaleY(0.18); } 50% { transform: scaleY(1); }
        }
        @keyframes jarvis-shimmer {
          0%,100% { filter: brightness(0.7); }
          50%     { filter: brightness(1.6) hue-rotate(30deg); }
        }
        @keyframes jarvis-error {
          0%,100% { opacity: 0.5; } 50% { opacity: 1; }
        }
        @keyframes jarvis-fade-in {
          from { opacity: 0; transform: translateY(4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .jarvis-input::placeholder { opacity: 0.4; }
        .jarvis-scroll::-webkit-scrollbar { width: 3px; }
        .jarvis-scroll::-webkit-scrollbar-thumb {
          border-radius: 3px;
          background: ${isDark ? 'rgba(255,255,255,0.12)' : '#cbd5e1'};
        }
      `}</style>

      {/* ── Widget container ─────────────────────────────────────────────────── */}
      <div style={{
        position: 'fixed', bottom: '96px', right: '24px',
        width: '380px', maxWidth: 'calc(100vw - 32px)',
        zIndex: 9999, borderRadius: '24px', overflow: 'hidden',
        fontFamily: "'Inter', system-ui, sans-serif",
        animation: 'jarvis-slide-in 0.25s cubic-bezier(0.4,0,0.2,1) forwards',
        background: isDark ? 'rgba(13,34,68,0.88)' : 'rgba(255,255,255,0.92)',
        backdropFilter: 'blur(32px) saturate(160%)',
        WebkitBackdropFilter: 'blur(32px) saturate(160%)',
        border: `1px solid ${isDark ? '#1e3a72' : '#e2e8f0'}`,
        boxShadow: isDark
          ? '0 20px 60px rgba(0,0,0,0.5), 0 4px 16px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.04) inset'
          : '0 20px 60px rgba(15,23,42,0.12), 0 4px 16px rgba(15,23,42,0.06), 0 0 0 1px rgba(255,255,255,0.8) inset',
      }}>

        {/* Header */}
        <div style={{ padding: '16px 18px 0', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{
            fontSize: '11px', fontWeight: 700, letterSpacing: '0.2em',
            textTransform: 'uppercase',
            background: 'linear-gradient(90deg, #1a56db, #0ea5e9, #4CC9F0)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text',
          }}>JARVIS</span>

          <span style={{
            fontSize: '10px', fontWeight: 500, borderRadius: '20px', padding: '3px 10px',
            background: isDark ? 'rgba(255,255,255,0.06)' : '#f1f5f9',
            border: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : '#e2e8f0'}`,
            color: isDark ? '#94a8c4' : '#64748b',
          }}>Voice AI</span>

          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button
              onClick={() => setShowHistory(h => !h)}
              title={showHistory ? 'Hide history' : 'Show history'}
              style={{
                width: '24px', height: '24px', borderRadius: '8px',
                border: 'none', background: 'transparent',
                color: isDark ? '#94a8c4' : '#64748b',
                cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'background 0.15s',
              }}
              onMouseEnter={e => e.currentTarget.style.background = isDark ? 'rgba(255,255,255,0.07)' : '#f1f5f9'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              {showHistory ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
            </button>

            <button
              onClick={handleClose}
              style={{
                width: '28px', height: '28px', borderRadius: '50%',
                border: 'none',
                background: isDark ? 'rgba(255,255,255,0.07)' : '#f1f5f9',
                color: isDark ? '#94a8c4' : '#64748b',
                cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'background 0.15s',
              }}
              onMouseEnter={e => e.currentTarget.style.background = isDark ? 'rgba(255,255,255,0.12)' : '#e2e8f0'}
              onMouseLeave={e => e.currentTarget.style.background = isDark ? 'rgba(255,255,255,0.07)' : '#f1f5f9'}
            >
              <X size={13} />
            </button>
          </div>
        </div>

        {/* Siri waveform */}
        {renderWaveform()}

        {/* Status label */}
        <div style={{
          padding: '4px 0 8px', textAlign: 'center',
          fontSize: '12px', fontWeight: 400,
          color: isDark ? '#94a8c4' : '#64748b',
        }}>
          {LABEL[state]}
        </div>

        {/* Transcript + response */}
        {((transcript && state !== S.IDLE && state !== S.CONNECTING) || response) && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', animation: 'jarvis-fade-in 0.2s ease' }}>
            {transcript && state !== S.IDLE && state !== S.CONNECTING && (
              <div style={{
                margin: '0 16px 6px', padding: '8px 14px',
                borderRadius: '20px 20px 6px 20px', fontSize: '13px', fontWeight: 500,
                background: isDark ? 'rgba(26,86,219,0.15)' : '#eff6ff',
                border: `1px solid ${isDark ? 'rgba(26,86,219,0.3)' : '#bfdbfe'}`,
                color: isDark ? '#93c5fd' : '#1e40af',
              }}>
                &ldquo;{transcript}&rdquo;
              </div>
            )}
            {response && (
              <div style={{
                margin: '0 16px 10px', fontSize: '13px', lineHeight: 1.5,
                textAlign: 'center', color: isDark ? '#94a8c4' : '#64748b',
                display: '-webkit-box', WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical', overflow: 'hidden',
              }}>
                {response}
              </div>
            )}
          </div>
        )}

        {/* History panel */}
        {showHistory && history.length > 0 && (
          <div style={{ borderTop: `1px solid ${isDark ? '#1e3a72' : '#e2e8f0'}` }}>
            <div className="jarvis-scroll" style={{
              padding: '10px 14px', maxHeight: '180px', overflowY: 'auto',
              display: 'flex', flexDirection: 'column', gap: '8px',
            }}>
              {history.map((msg, i) => (
                <div key={i} style={{
                  alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: msg.role === 'user' ? '80%' : '85%',
                  padding: '7px 12px', fontSize: '12px', lineHeight: 1.45,
                  borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                  ...(msg.role === 'user' ? {
                    background: isDark ? 'rgba(26,86,219,0.18)' : '#eff6ff',
                    color: isDark ? '#93c5fd' : '#1e40af',
                  } : {
                    background: isDark ? 'rgba(255,255,255,0.05)' : '#f1f5f9',
                    border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : '#e2e8f0'}`,
                    color: isDark ? '#f0f1ed' : '#0f172a',
                  }),
                }}>
                  {msg.text}
                </div>
              ))}
              <div ref={historyEndRef} />
            </div>
          </div>
        )}

        {/* Voice hint bar */}
        <div style={{
          padding: '6px 16px', fontFamily: 'monospace', fontSize: '10px',
          borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.04)' : '#e2e8f0'}`,
          background: isDark ? 'rgba(0,0,0,0.2)' : '#f1f5f9',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          color: state === S.LISTENING
            ? '#059669'
            : state === S.SPEAKING
              ? '#fbbf24'
              : isDark ? '#94a8c4' : '#64748b',
        }}>
          {state === S.LISTENING
            ? 'Hands-free mode active. Speak naturally.'
            : `Say "Hey Jarvis" to wake, or tap the mic to talk.${latencyMs ? ` · ${latencyMs}ms` : ''}`}
        </div>

        {/* Text input row */}
        <div style={{
          padding: '12px 14px 16px', display: 'flex', gap: '8px', alignItems: 'center',
          borderTop: `1px solid ${isDark ? '#1e3a72' : '#e2e8f0'}`,
        }}>
          <input
            className="jarvis-input"
            type="text"
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSend()}
            placeholder="Or type a command…"
            disabled={state === S.PROCESSING || state === S.CONNECTING}
            style={{
              flex: 1, borderRadius: '20px', padding: '10px 14px',
              fontSize: '13px', fontFamily: "'Inter', system-ui, sans-serif",
              outline: 'none', transition: 'border-color 0.15s, box-shadow 0.15s',
              background: isDark ? 'rgba(255,255,255,0.05)' : '#f1f5f9',
              border: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : '#e2e8f0'}`,
              color: isDark ? '#f0f1ed' : '#0f172a',
            }}
            onFocus={e => {
              e.target.style.borderColor = isDark ? 'rgba(76,201,240,0.5)' : '#1a56db'
              e.target.style.boxShadow   = isDark ? '0 0 0 3px rgba(76,201,240,0.1)' : '0 0 0 3px rgba(26,86,219,0.15)'
            }}
            onBlur={e => {
              e.target.style.borderColor = isDark ? 'rgba(255,255,255,0.1)' : '#e2e8f0'
              e.target.style.boxShadow   = 'none'
            }}
          />

          {/* Mic / Send button */}
          <button
            onClick={
              state === S.LISTENING
                ? () => stopListening(true)   // cancel recording
                : inputText.trim() ? handleSend : startListening
            }
            disabled={state === S.PROCESSING || state === S.CONNECTING}
            title={state === S.LISTENING ? 'Stop' : inputText.trim() ? 'Send' : 'Tap to speak'}
            style={{
              width: '40px', height: '40px', borderRadius: '50%', flexShrink: 0,
              border: (state === S.LISTENING || inputText.trim())
                ? 'none'
                : `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : '#e2e8f0'}`,
              cursor: (state === S.PROCESSING || state === S.CONNECTING)
                ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.15s ease',
              ...(state === S.LISTENING
                ? { background: '#ef4444', color: 'white' }
                : inputText.trim()
                  ? { background: 'linear-gradient(135deg, #1a56db, #0ea5e9)', color: 'white' }
                  : { background: isDark ? 'rgba(255,255,255,0.07)' : '#f1f5f9',
                      color: isDark ? '#4CC9F0' : '#1a56db' }
              ),
            }}
          >
            {state === S.LISTENING
              ? <MicOff size={16} />
              : inputText.trim() ? <Send size={16} /> : <Mic size={16} />
            }
          </button>
        </div>

      </div>
    </>
  )
}
