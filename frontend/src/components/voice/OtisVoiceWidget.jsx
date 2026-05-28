import { useState, useEffect, useRef, useCallback } from 'react'
import { X, Mic, MicOff, Send, MessageSquare, Clock, Wifi, WifiOff } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  getOtisStatus,
  startOtisSession,
  stopOtisSession,
  sendOtisCommandRest,
  transcribeOtisAudio,
  otisSpeak,
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
  [S.IDLE]:       'Tap the mic to talk',
  [S.CONNECTING]: 'Connecting…',
  [S.READY]:      'Ready',
  [S.LISTENING]:  'Listening…',
  [S.PROCESSING]: 'Thinking…',
  [S.SPEAKING]:   'Speaking…',
  [S.ERROR]:      'Error — tap to retry',
}

const SUBLABEL = {
  [S.IDLE]:       'Initialising Jarvis',
  [S.CONNECTING]: 'Starting session',
  [S.READY]:      'How can I help you today?',
  [S.LISTENING]:  'Speak naturally — I can hear you',
  [S.PROCESSING]: 'Processing your request with AI',
  [S.SPEAKING]:   'Playing response audio',
  [S.ERROR]:      'Something went wrong',
}

// ── Audio MIME helpers ─────────────────────────────────────────────────────────
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
function getSpeechRecognitionCtor() {
  if (typeof window === 'undefined') return null
  return window.SpeechRecognition || window.webkitSpeechRecognition || null
}
function normalizeTranscript(text) {
  return (text || '').replace(/\s+/g, ' ').trim()
}
function getRecognitionLanguage() {
  if (typeof navigator === 'undefined') return 'en-IN'
  const langs = [navigator.language, ...(navigator.languages || [])].filter(Boolean)
  return langs.find(l => /^en-in$/i.test(l)) || langs.find(l => /^en(?:-|$)/i.test(l)) || 'en-IN'
}

// ── Browser TTS voice picker ───────────────────────────────────────────────────
const VOICE_PRIORITY = [
  v => v.lang === 'en-IN' && /male|man|david|george|rahul|ravi|aditya|aarav/i.test(v.name),
  v => /indian|india/.test(v.name.toLowerCase()) && /male|man/i.test(v.name),
  v => v.lang === 'en-IN',
  v => /indian|india/.test(v.name.toLowerCase()),
  v => v.name === 'Google UK English Male',
  v => v.name === 'Daniel',
  v => v.name === 'Microsoft George - English (United Kingdom)',
  v => v.name === 'Microsoft David - English (United States)',
  v => v.name === 'Alex',
  v => v.name.toLowerCase().includes('daniel'),
  v => v.name.toLowerCase().includes('david'),
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

// ── Waveform colour helpers ────────────────────────────────────────────────────
function getBarColor(state, i, isDark) {
  if (state === S.IDLE)       return isDark ? 'rgba(255,255,255,0.14)' : 'rgba(26,86,219,0.22)'
  if (state === S.CONNECTING) return 'rgba(119,141,169,0.55)'
  if (state === S.READY)      return isDark ? 'rgba(76,201,240,0.45)' : 'rgba(26,86,219,0.5)'
  if (state === S.ERROR)      return 'rgba(239,68,68,0.55)'
  if (state === S.PROCESSING) return isDark ? '#fbbf24' : '#d97706'
  if (state === S.LISTENING) {
    const p = ['#1a56db','#1a56db','#0ea5e9','#0ea5e9','#4CC9F0','#4CC9F0',
               '#059669','#10b981','#10b981','#a78bfa','#a78bfa','#0ea5e9']
    return p[i % p.length]
  }
  if (state === S.SPEAKING) {
    const p = ['#0ea5e9','#4CC9F0','#4CC9F0','#059669','#10b981','#1a56db','#0ea5e9']
    return p[i % p.length]
  }
  return isDark ? 'rgba(255,255,255,0.14)' : 'rgba(26,86,219,0.22)'
}
function barDuration(i) { return `${(0.4 + (i % 7) * 0.043).toFixed(3)}s` }
function fmtTime(d) {
  if (!d) return ''
  return new Date(d).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

// ── Component ──────────────────────────────────────────────────────────────────
export default function OtisVoiceWidget({ onClose, autoStart = false }) {
  const { theme } = useStore()
  const isDark = theme === 'dark'

  // ── State ────────────────────────────────────────────────────────────────────
  const [state, setState]                   = useState(S.IDLE)
  const [sessionId, setSessionId]           = useState(null)
  const [transcript, setTranscript]         = useState('')
  const [response, setResponse]             = useState('')
  const [history, setHistory]               = useState([])
  const [inputText, setInputText]           = useState('')
  const [displayedWords, setDisplayedWords] = useState([])

  // ── Refs ─────────────────────────────────────────────────────────────────────
  const stateRef               = useRef(S.IDLE)
  const sessionIdRef           = useRef(null)
  const historyEndRef          = useRef(null)
  const mediaRecRef            = useRef(null)
  const chunksRef              = useRef([])
  const streamRef              = useRef(null)
  const analyserRef            = useRef(null)
  const animFrameRef           = useRef(null)
  const silenceTimerRef        = useRef(null)
  const audioRef               = useRef(null)
  const cancelledRef           = useRef(false)
  const bootedRef              = useRef(false)
  const cleanupTimerRef        = useRef(null)
  const recognitionRef         = useRef(null)
  const recognitionTimerRef    = useRef(null)
  const recognitionFinalRef    = useRef('')
  const recognitionFallbackRef = useRef(false)
  const autoListenPendingRef   = useRef(Boolean(autoStart))
  const followUpPendingRef     = useRef(false)
  const followUpTimerRef       = useRef(null)
  const wordTimerRef           = useRef(null)

  // Sync refs
  useEffect(() => { stateRef.current = state },         [state])
  useEffect(() => { sessionIdRef.current = sessionId }, [sessionId])
  useEffect(() => { autoListenPendingRef.current = Boolean(autoStart) }, [autoStart])

  // Auto-scroll history
  useEffect(() => {
    historyEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history])

  // Word-by-word reveal when response changes
  useEffect(() => {
    if (wordTimerRef.current) { clearInterval(wordTimerRef.current); wordTimerRef.current = null }
    if (!response) { setDisplayedWords([]); return }
    const words = response.trim().split(/\s+/).filter(Boolean)
    setDisplayedWords([])
    let idx = 0
    wordTimerRef.current = setInterval(() => {
      idx += 1
      setDisplayedWords(words.slice(0, idx))
      if (idx >= words.length) { clearInterval(wordTimerRef.current); wordTimerRef.current = null }
    }, 62)
    return () => { if (wordTimerRef.current) clearInterval(wordTimerRef.current) }
  }, [response])

  // ESC to close
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') { e.preventDefault(); handleCloseRef.current() } }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Bootstrap session on mount
  useEffect(() => {
    if (cleanupTimerRef.current) { clearTimeout(cleanupTimerRef.current); cleanupTimerRef.current = null }
    if (!bootedRef.current) { bootedRef.current = true; initSession() }
    return () => {
      cleanupTimerRef.current = setTimeout(() => {
        bootedRef.current = false
        followUpPendingRef.current = false
        if (followUpTimerRef.current) { clearTimeout(followUpTimerRef.current); followUpTimerRef.current = null }
        if (wordTimerRef.current)     { clearInterval(wordTimerRef.current); wordTimerRef.current = null }
        stopListening(true)
        stopAudio()
        // Cancel ALL audio sources on unmount
        if (window.speechSynthesis) window.speechSynthesis.cancel()
        if (sessionIdRef.current) stopOtisSession(sessionIdRef.current).catch(() => {})
      }, 0)
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
      setTranscript('')
      setResponse(welcome)
      setHistory([{ role: 'assistant', text: welcome, time: new Date() }])
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

  // ── Audio helpers ─────────────────────────────────────────────────────────────
  const stopAudio = () => {
    if (audioRef.current) {
      try { audioRef.current.pause() } catch {}
      audioRef.current = null
    }
  }

  // ── stopListening ─────────────────────────────────────────────────────────────
  const stopListening = useCallback((cancel = false) => {
    cancelledRef.current = cancel
    recognitionFinalRef.current = ''
    recognitionFallbackRef.current = false
    if (recognitionTimerRef.current) { clearTimeout(recognitionTimerRef.current); recognitionTimerRef.current = null }
    if (recognitionRef.current) {
      const r = recognitionRef.current
      recognitionRef.current = null
      try { if (cancel) r.abort(); else r.stop() } catch {}
    }
    if (animFrameRef.current)    { cancelAnimationFrame(animFrameRef.current); animFrameRef.current = null }
    if (silenceTimerRef.current) { clearTimeout(silenceTimerRef.current); silenceTimerRef.current = null }
    if (analyserRef.current)     { analyserRef.current.audioCtx.close().catch(() => {}); analyserRef.current = null }
    if (streamRef.current)       { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null }
    if (mediaRecRef.current) {
      try { if (mediaRecRef.current.state === 'recording') mediaRecRef.current.stop() } catch {}
    }
  }, [])

  // ── startListening ────────────────────────────────────────────────────────────
  const startListening = useCallback(async () => {
    if ([S.LISTENING, S.PROCESSING, S.CONNECTING].includes(stateRef.current)) return
    autoListenPendingRef.current = false
    followUpPendingRef.current = false
    if (followUpTimerRef.current) { clearTimeout(followUpTimerRef.current); followUpTimerRef.current = null }

    const startRecorderFallback = async () => {
      const mimeType = getSupportedMimeType()
      if (!mimeType) { toast.error('Voice recording not supported in this browser'); return }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
          video: false,
        })
        streamRef.current = stream
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)()
        const source   = audioCtx.createMediaStreamSource(stream)
        const analyser = audioCtx.createAnalyser()
        analyser.fftSize = 512; analyser.smoothingTimeConstant = 0.3
        source.connect(analyser)
        analyserRef.current = { audioCtx, analyser }
        chunksRef.current = []; cancelledRef.current = false
        const recorder = new MediaRecorder(stream, { mimeType })
        recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
        recorder.onstop = async () => {
          mediaRecRef.current = null
          if (cancelledRef.current) { cancelledRef.current = false; if (stateRef.current === S.LISTENING) setState(S.READY); return }
          const blob = new Blob(chunksRef.current, { type: mimeType })
          if (blob.size < 250) { if ([S.LISTENING, S.PROCESSING].includes(stateRef.current)) setState(S.READY); return }
          setState(S.PROCESSING)
          try {
            const result = await transcribeOtisAudio(blob)
            if (result.success && result.text) { setTranscript(result.text); processCommand(result.text, { fromVoice: true }) }
            else if (result.silent) { if (stateRef.current === S.PROCESSING) setState(S.READY) }
            else { toast.error(result.error || 'Could not understand audio'); setResponse("I couldn't understand that clearly. Please try again."); setState(S.READY) }
          } catch { toast.error('Transcription failed'); setResponse('I had trouble hearing that. Please try again.'); setState(S.READY) }
        }
        recorder.onerror = () => {
          stream.getTracks().forEach(t => t.stop()); streamRef.current = null; mediaRecRef.current = null
          if (stateRef.current === S.LISTENING) setState(S.READY)
          toast.error('Recording failed')
        }
        mediaRecRef.current = recorder; recorder.start(120)
        setState(S.LISTENING); setTranscript('')
        const freqData = new Uint8Array(analyser.frequencyBinCount)
        const timeData = new Uint8Array(analyser.fftSize)
        let silentSince = 0, heardSpeech = false
        const startedAt = Date.now(), maxInit = 3500, postSpeech = 1350, bootstrap = 450
        const checkSilence = () => {
          if (!mediaRecRef.current || mediaRecRef.current.state !== 'recording') return
          if (Date.now() - startedAt > 60000) { stopListening(); return }
          analyser.getByteFrequencyData(freqData); analyser.getByteTimeDomainData(timeData)
          const avg  = freqData.reduce((s, v) => s + v, 0) / freqData.length
          const peak = freqData.reduce((max, v) => Math.max(max, v), 0)
          const rms  = Math.sqrt(timeData.reduce((s, v) => { const c=(v-128)/128; return s+c*c }, 0) / timeData.length)
          const hasSpeech = avg >= 16 || peak >= 40 || rms >= 0.055
          if (hasSpeech) { heardSpeech = true; silentSince = 0 }
          else if (!heardSpeech) { if (Date.now() - startedAt > maxInit) { stopListening(); return } }
          else { if (!silentSince) silentSince = Date.now(); else if (Date.now() - silentSince > postSpeech) { stopListening(); return } }
          animFrameRef.current = requestAnimationFrame(checkSilence)
        }
        silenceTimerRef.current = setTimeout(() => { animFrameRef.current = requestAnimationFrame(checkSilence) }, bootstrap)
      } catch (err) {
        if ([S.LISTENING, S.CONNECTING].includes(stateRef.current)) setState(S.READY)
        toast.error(err.name === 'NotAllowedError' ? 'Mic access denied' : 'Could not access microphone')
      }
    }

    const SpeechRecognition = getSpeechRecognitionCtor()
    if (SpeechRecognition) {
      try {
        const recognition = new SpeechRecognition()
        recognitionRef.current = recognition
        recognitionFinalRef.current = ''; recognitionFallbackRef.current = false; cancelledRef.current = false
        recognition.continuous = false; recognition.interimResults = true
        recognition.lang = getRecognitionLanguage(); recognition.maxAlternatives = 3
        recognition.onresult = (event) => {
          let finalText = recognitionFinalRef.current, interimText = ''
          for (let i = event.resultIndex; i < event.results.length; i++) {
            const value = normalizeTranscript(event.results[i][0]?.transcript)
            if (!value) continue
            if (event.results[i].isFinal) finalText = normalizeTranscript(`${finalText} ${value}`)
            else interimText = normalizeTranscript(`${interimText} ${value}`)
          }
          recognitionFinalRef.current = finalText
          const liveText = normalizeTranscript(`${finalText} ${interimText}`)
          if (liveText) setTranscript(liveText)
        }
        recognition.onerror = (event) => {
          const code = event?.error || 'unknown'
          if (code === 'aborted') return
          if (code === 'not-allowed' || code === 'service-not-allowed') { toast.error('Mic access denied'); return }
          if (code === 'network') { recognitionFallbackRef.current = true; return }
          if (code !== 'no-speech') toast.error('Voice recognition failed')
        }
        recognition.onend = () => {
          if (recognitionTimerRef.current) { clearTimeout(recognitionTimerRef.current); recognitionTimerRef.current = null }
          if (recognitionRef.current === recognition) recognitionRef.current = null
          const finalText = normalizeTranscript(recognitionFinalRef.current)
          const shouldFallback = recognitionFallbackRef.current && !finalText && !cancelledRef.current
          recognitionFinalRef.current = ''; recognitionFallbackRef.current = false
          if (cancelledRef.current) { cancelledRef.current = false; if (stateRef.current === S.LISTENING) setState(S.READY); return }
          if (finalText) { processCommand(finalText, { fromVoice: true }); return }
          if (shouldFallback) { void startRecorderFallback(); return }
          if (stateRef.current === S.LISTENING) setState(S.READY)
        }
        setTranscript(''); setState(S.LISTENING); recognition.start()
        recognitionTimerRef.current = setTimeout(() => {
          if (!recognitionRef.current || recognitionRef.current !== recognition) return
          try { recognition.stop() } catch {}
        }, 9000)
        return
      } catch { recognitionRef.current = null }
    }
    await startRecorderFallback()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Command processing ────────────────────────────────────────────────────────
  const processCommand = useCallback(async (command, { fromVoice = false } = {}) => {
    if (!command.trim()) return
    const userText = command.trim()
    setState(S.PROCESSING); setTranscript(userText); setResponse('')
    setHistory(h => [...h, { role: 'user', text: userText, time: new Date() }])
    try {
      const result = await sendOtisCommandRest(userText, sessionIdRef.current)
      const text = result.response || 'Done.'
      if (result.session_id && result.session_id !== sessionIdRef.current) setSessionId(result.session_id)
      followUpPendingRef.current = fromVoice
      setResponse(text)
      setHistory(h => [...h, { role: 'assistant', text, time: new Date() }])
      speakAndReturn(text)
    } catch (err) {
      console.error('[Jarvis] Command failed:', err)
      const errText = 'Sorry, something went wrong. Please try again.'
      followUpPendingRef.current = false
      setResponse(errText)
      setHistory(h => [...h, { role: 'assistant', text: errText, time: new Date() }])
      setState(S.READY); toast.error('Jarvis command failed')
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── speakAndReturn — DUAL AUDIO FIX: cancel browser TTS first, always ────────
  const speakAndReturn = useCallback(async (text) => {
    setState(S.SPEAKING)
    stopAudio()
    // ── FIX: Always cancel browser speech before starting any new TTS. ──────────
    // Without this, if ElevenLabs plays AND old browser SpeechSynthesis is
    // lingering from a previous turn, both audio streams play simultaneously.
    if (window.speechSynthesis) window.speechSynthesis.cancel()

    const safetyTimer = setTimeout(() => {
      if (stateRef.current === S.SPEAKING) {
        const a = autoListenPendingRef.current, f = followUpPendingRef.current
        setState(S.READY)
        if (a || f) {
          followUpTimerRef.current = setTimeout(() => {
            autoListenPendingRef.current = false; followUpPendingRef.current = false
            followUpTimerRef.current = null; startListening()
          }, f ? 650 : 250)
        }
      }
    }, 12000)

    const done = () => {
      const a = autoListenPendingRef.current, f = followUpPendingRef.current
      clearTimeout(safetyTimer)
      setState(S.READY)
      if (a || f) {
        if (followUpTimerRef.current) clearTimeout(followUpTimerRef.current)
        followUpTimerRef.current = setTimeout(() => {
          autoListenPendingRef.current = false; followUpPendingRef.current = false
          followUpTimerRef.current = null; startListening()
        }, f ? 650 : 250)
      }
    }

    // ── Try ElevenLabs ────────────────────────────────────────────────────────
    try {
      const audioBlob = await otisSpeak(text)
      if (audioBlob && audioBlob.size > 100) {
        const url = URL.createObjectURL(audioBlob)
        const audio = new Audio(url)
        audioRef.current = audio
        audio.onended = () => { URL.revokeObjectURL(url); audioRef.current = null; done() }
        audio.onerror = () => { URL.revokeObjectURL(url); audioRef.current = null; done() }
        await audio.play()
        return   // ElevenLabs handled — do NOT fall through to browser TTS
      }
    } catch (err) {
      console.warn('[Jarvis] ElevenLabs TTS unavailable, using browser fallback:', err)
    }

    // ── Fallback: browser SpeechSynthesis ─────────────────────────────────────
    if (!('speechSynthesis' in window)) { done(); return }
    // Already cancelled above — safe to start fresh
    const doSpeak = () => {
      const utt = new SpeechSynthesisUtterance(text)
      const voice = pickFallbackVoice()
      if (voice) utt.voice = voice
      utt.lang = voice?.lang || 'en-IN'
      utt.rate = 0.95; utt.pitch = 0.85; utt.volume = 1.0
      utt.onend = done; utt.onerror = done
      window.speechSynthesis.speak(utt)
    }
    const voices = window.speechSynthesis.getVoices()
    if (voices.length > 0) { doSpeak() }
    else {
      const t = setTimeout(() => { window.speechSynthesis.onvoiceschanged = null; done() }, 2000)
      window.speechSynthesis.onvoiceschanged = () => { clearTimeout(t); window.speechSynthesis.onvoiceschanged = null; doSpeak() }
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Handlers ──────────────────────────────────────────────────────────────────
  const handleSend = () => {
    const cmd = inputText.trim()
    if (!cmd) return
    setInputText('')
    processCommand(cmd, { fromVoice: false })
  }

  const handleMicClick = () => {
    if (state === S.ERROR)     { initSession(); return }
    if (state === S.LISTENING) { stopListening(true); return }
    if (state === S.READY)     { startListening(); return }
    if (state === S.SPEAKING)  {
      followUpPendingRef.current = false
      if (followUpTimerRef.current) { clearTimeout(followUpTimerRef.current); followUpTimerRef.current = null }
      stopAudio(); window.speechSynthesis?.cancel()
      setState(S.READY); setTimeout(startListening, 300)
    }
  }

  const handleClose = async () => {
    followUpPendingRef.current = false
    if (followUpTimerRef.current) { clearTimeout(followUpTimerRef.current); followUpTimerRef.current = null }
    stopListening(true); stopAudio()
    if (window.speechSynthesis) window.speechSynthesis.cancel()
    if (sessionId) stopOtisSession(sessionId).catch(() => {})
    onClose()
  }

  // Keep handleClose accessible in ESC effect without re-registering
  const handleCloseRef = useRef(handleClose)
  useEffect(() => { handleCloseRef.current = handleClose }) // update each render

  // ── Derived values ────────────────────────────────────────────────────────────
  const isActive   = state === S.LISTENING || state === S.SPEAKING
  const totalWords = response ? response.trim().split(/\s+/).length : 0
  const isTyping   = displayedWords.length < totalWords

  const dotColor = state === S.ERROR ? '#ef4444'
    : state === S.CONNECTING ? '#fbbf24'
    : [S.LISTENING, S.SPEAKING, S.PROCESSING].includes(state) ? '#10b981'
    : isDark ? '#4CC9F0' : '#1a56db'

  const labelColor = state === S.LISTENING ? '#10b981'
    : state === S.SPEAKING ? (isDark ? '#4CC9F0' : '#0ea5e9')
    : state === S.PROCESSING ? (isDark ? '#fbbf24' : '#d97706')
    : state === S.ERROR ? '#ef4444'
    : isDark ? '#94a8c4' : '#64748b'

  // ── Waveform renderer ─────────────────────────────────────────────────────────
  const renderWaveform = () => {
    const bars = Array.from({ length: 44 }, (_, i) => i)
    return (
      <div
        onClick={handleMicClick}
        style={{
          height: '80px', width: '100%',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          overflow: 'hidden', position: 'relative',
          cursor: [S.READY, S.LISTENING, S.ERROR, S.SPEAKING].includes(state) ? 'pointer' : 'default',
        }}
      >
        {isActive && (
          <div style={{
            position: 'absolute', bottom: 0, left: '50%',
            transform: 'translateX(-50%)',
            width: '280px', height: '48px', pointerEvents: 'none',
            background: isDark
              ? 'radial-gradient(ellipse 280px 48px, rgba(76,201,240,0.22), transparent)'
              : 'radial-gradient(ellipse 280px 48px, rgba(26,86,219,0.16), transparent)',
          }} />
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: '3.5px' }}>
          {bars.map(i => {
            let anim = 'none', height = '6px'
            const d = `${(i * 0.04).toFixed(2)}s`
            const color = getBarColor(state, i, isDark)
            if      (state === S.IDLE)       { anim = `jv-idle 3.5s ease-in-out ${d} infinite` }
            else if (state === S.CONNECTING) { height = '10px'; anim = `jv-connecting 1.2s ease-in-out ${d} infinite` }
            else if (state === S.READY)      { height = '10px'; anim = `jv-ready 4s ease-in-out ${d} infinite` }
            else if (state === S.LISTENING)  { height = '48px'; anim = `jv-bar ${barDuration(i)} ease-in-out ${d} infinite` }
            else if (state === S.SPEAKING)   { height = '48px'; anim = `jv-bar ${barDuration(i)} ease-in-out ${d} infinite` }
            else if (state === S.PROCESSING) { height = '22px'; anim = `jv-shimmer 1.4s ease-in-out ${d} infinite` }
            else if (state === S.ERROR)      { height = '18px'; anim = `jv-error 2.5s ease-in-out ${d} infinite` }
            return (
              <div key={i} style={{
                width: '3.5px', height, borderRadius: '2px',
                backgroundColor: color, animation: anim,
                transformOrigin: 'bottom center', flexShrink: 0,
              }} />
            )
          })}
        </div>
      </div>
    )
  }

  // ── CSS colors (used in style tag) ────────────────────────────────────────────
  const border = isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)'
  const scrollThumb = isDark ? 'rgba(255,255,255,0.14)' : '#cbd5e1'

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <>
      <style>{`
        /* Entry */
        @keyframes jv-backdrop-in { from{opacity:0} to{opacity:1} }
        @keyframes jv-modal-in    { from{opacity:0;transform:scale(0.97) translateY(12px)} to{opacity:1;transform:scale(1) translateY(0)} }

        /* Waveform */
        @keyframes jv-idle       { 0%,100%{height:6px}  50%{height:9px}  }
        @keyframes jv-connecting { 0%,100%{height:10px} 50%{height:24px} }
        @keyframes jv-ready      { 0%,100%{height:10px} 50%{height:16px} }
        @keyframes jv-bar        { 0%,100%{transform:scaleY(0.1)} 50%{transform:scaleY(1)} }
        @keyframes jv-shimmer    { 0%,100%{filter:brightness(0.7)} 50%{filter:brightness(1.7) hue-rotate(30deg)} }
        @keyframes jv-error      { 0%,100%{opacity:0.4} 50%{opacity:1} }

        /* Orbital rings */
        @keyframes jv-orbit     { from{transform:translate(-50%,-50%) rotate(0deg)}   to{transform:translate(-50%,-50%) rotate(360deg)}  }
        @keyframes jv-orbit-ccw { from{transform:translate(-50%,-50%) rotate(0deg)}   to{transform:translate(-50%,-50%) rotate(-360deg)} }

        /* Text */
        @keyframes jv-word-in { from{opacity:0;transform:translateY(5px)} to{opacity:1;transform:translateY(0)} }
        @keyframes jv-msg-in  { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
        @keyframes jv-blink   { 0%,100%{opacity:1} 50%{opacity:0} }

        /* Dot pulse */
        @keyframes jv-dot-pulse {
          0%  { box-shadow:0 0 0 0 ${dotColor}66; }
          70% { box-shadow:0 0 0 7px transparent; }
          100%{ box-shadow:0 0 0 0 transparent; }
        }

        /* Mic button ring pulse */
        @keyframes jv-ring-pulse {
          0%  { box-shadow:0 0 0 0 rgba(239,68,68,0.5); }
          70% { box-shadow:0 0 0 14px transparent; }
          100%{ box-shadow:0 0 0 0 transparent; }
        }

        /* Scrollbars */
        .jv-scroll::-webkit-scrollbar { width:4px; }
        .jv-scroll::-webkit-scrollbar-track { background:transparent; }
        .jv-scroll::-webkit-scrollbar-thumb { border-radius:4px; background:${scrollThumb}; }
        .jv-scroll::-webkit-scrollbar-thumb:hover { background:${isDark ? 'rgba(255,255,255,0.22)' : '#94a3b8'}; }

        /* Input */
        .jv-input::placeholder { opacity:0.38; }
        .jv-input:focus {
          border-color:${isDark ? 'rgba(76,201,240,0.55)' : '#1a56db'} !important;
          box-shadow:${isDark ? '0 0 0 3px rgba(76,201,240,0.12)' : '0 0 0 3px rgba(26,86,219,0.12)'} !important;
        }

        /* Close btn */
        .jv-close:hover {
          background:${isDark ? 'rgba(239,68,68,0.16)' : 'rgba(239,68,68,0.09)'} !important;
          color:#ef4444 !important;
        }

        /* Mic btn */
        .jv-mic-btn:not(:disabled):hover { filter:brightness(1.1); transform:scale(1.05); }

        /* Responsive */
        @media (max-width:900px) { .jv-left  { display:none !important; } }
        @media (max-width:600px) { .jv-right { width:0 !important; min-width:0 !important; overflow:hidden !important; border:none !important; } }
      `}</style>

      {/* ── Full-screen backdrop ─────────────────────────────────────────────── */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        animation: 'jv-backdrop-in 0.18s ease forwards',
      }}>
        {/* Click-away */}
        <div onClick={handleClose} style={{
          position: 'absolute', inset: 0,
          background: isDark ? 'rgba(3,8,20,0.88)' : 'rgba(8,20,46,0.55)',
          backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)',
        }} />

        {/* ── Modal — fills full viewport ───────────────────────────────────── */}
        <div style={{
          position: 'relative',
          width: '100%', height: '100%',
          display: 'flex', flexDirection: 'column',
          fontFamily: "'Inter', system-ui, sans-serif",
          animation: 'jv-modal-in 0.3s cubic-bezier(0.34,1.2,0.64,1) forwards',
          background: isDark
            ? 'linear-gradient(160deg, #0d2040 0%, #070e1c 50%, #0a1830 100%)'
            : 'linear-gradient(160deg, #ffffff 0%, #f8fafc 50%, #f0f4ff 100%)',
        }}>

          {/* ── Header ────────────────────────────────────────────────────── */}
          <div style={{
            padding: '0 24px', height: '58px', flexShrink: 0,
            display: 'flex', alignItems: 'center', gap: '12px',
            borderBottom: `1px solid ${border}`,
            background: isDark ? 'rgba(0,0,0,0.28)' : 'rgba(255,255,255,0.72)',
            backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
          }}>
            <span style={{
              fontSize: '12px', fontWeight: 800, letterSpacing: '0.24em', textTransform: 'uppercase',
              background: 'linear-gradient(90deg,#1a56db,#0ea5e9,#4CC9F0)',
              WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text',
            }}>JARVIS</span>

            <span style={{
              fontSize: '11px', fontWeight: 500, borderRadius: '20px', padding: '2px 10px',
              background: isDark ? 'rgba(76,201,240,0.1)' : 'rgba(26,86,219,0.07)',
              border: `1px solid ${isDark ? 'rgba(76,201,240,0.2)' : 'rgba(26,86,219,0.13)'}`,
              color: isDark ? '#4CC9F0' : '#1a56db',
            }}>Voice AI</span>

            {/* Live status dot */}
            <div style={{
              width: '8px', height: '8px', borderRadius: '50%', background: dotColor,
              animation: [S.LISTENING, S.SPEAKING].includes(state) ? 'jv-dot-pulse 1.4s ease infinite' : 'none',
            }} />

            {sessionId && (
              <span style={{ fontSize: '10px', fontFamily: 'monospace', color: isDark ? 'rgba(255,255,255,0.17)' : 'rgba(0,0,0,0.2)' }}>
                {sessionId.slice(-8)}
              </span>
            )}

            <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontSize: '11px', color: isDark ? 'rgba(255,255,255,0.28)' : 'rgba(0,0,0,0.3)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <MessageSquare size={11} />
                {history.length}
              </span>

              {/* Connection icon */}
              {state !== S.ERROR
                ? <Wifi size={13} color={isDark ? 'rgba(76,201,240,0.6)' : 'rgba(26,86,219,0.5)'} />
                : <WifiOff size={13} color="#ef4444" />
              }

              <button className="jv-close" onClick={handleClose} title="Close (Esc)" style={{
                width: '30px', height: '30px', borderRadius: '50%',
                border: 'none',
                background: isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.05)',
                color: isDark ? '#94a8c4' : '#64748b',
                cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'all 0.15s ease',
              }}>
                <X size={14} />
              </button>
            </div>
          </div>

          {/* ── Three-panel body ──────────────────────────────────────────── */}
          <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

            {/* ════════════════════════════════════════════════════════════
                PANEL 1 — CONVERSATION HISTORY (left)
            ════════════════════════════════════════════════════════════ */}
            <div className="jv-left" style={{
              width: '260px', minWidth: '260px', flexShrink: 0,
              borderRight: `1px solid ${border}`,
              display: 'flex', flexDirection: 'column',
              background: isDark ? 'rgba(0,0,0,0.2)' : 'rgba(0,0,0,0.025)',
            }}>
              {/* Panel header */}
              <div style={{
                padding: '14px 18px 11px', flexShrink: 0,
                borderBottom: `1px solid ${border}`,
                display: 'flex', alignItems: 'center', gap: '7px',
              }}>
                <MessageSquare size={12} color={isDark ? '#94a8c4' : '#64748b'} />
                <span style={{
                  fontSize: '11px', fontWeight: 600, letterSpacing: '0.12em',
                  textTransform: 'uppercase',
                  color: isDark ? '#94a8c4' : '#64748b',
                }}>Conversation</span>
                {history.length > 0 && (
                  <span style={{
                    marginLeft: 'auto', fontSize: '10px', fontWeight: 600,
                    padding: '1px 7px', borderRadius: '10px',
                    background: isDark ? 'rgba(76,201,240,0.12)' : 'rgba(26,86,219,0.08)',
                    color: isDark ? '#4CC9F0' : '#1a56db',
                  }}>{history.length}</span>
                )}
              </div>

              {/* Message list */}
              <div className="jv-scroll" style={{
                flex: 1, overflowY: 'auto',
                padding: '14px 12px 20px',
                display: 'flex', flexDirection: 'column', gap: '12px',
              }}>
                {history.length === 0 ? (
                  <div style={{
                    textAlign: 'center', padding: '40px 14px',
                    fontSize: '13px', lineHeight: 1.5,
                    color: isDark ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.22)',
                  }}>
                    Your conversation<br />will appear here
                  </div>
                ) : history.map((msg, i) => (
                  <div key={i} style={{
                    alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    maxWidth: '92%',
                    animation: 'jv-msg-in 0.2s ease forwards',
                  }}>
                    {/* Role + time label */}
                    <div style={{
                      fontSize: '10px', fontWeight: 600, letterSpacing: '0.1em',
                      marginBottom: '4px',
                      display: 'flex', alignItems: 'center', gap: '4px',
                      justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                      color: msg.role === 'user'
                        ? (isDark ? '#93c5fd' : '#3b82f6')
                        : (isDark ? '#4CC9F0' : '#0ea5e9'),
                    }}>
                      {msg.role === 'user' ? 'YOU' : 'JARVIS'}
                      {msg.time && (
                        <span style={{
                          fontWeight: 400, display: 'flex', alignItems: 'center', gap: '2px',
                          color: isDark ? 'rgba(255,255,255,0.22)' : 'rgba(0,0,0,0.3)',
                        }}>
                          <Clock size={9} />{fmtTime(msg.time)}
                        </span>
                      )}
                    </div>
                    {/* Bubble */}
                    <div style={{
                      padding: '8px 13px',
                      fontSize: '13px', lineHeight: 1.55,
                      borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                      ...(msg.role === 'user' ? {
                        background: isDark
                          ? 'linear-gradient(135deg,rgba(26,86,219,0.28),rgba(14,165,233,0.2))'
                          : 'linear-gradient(135deg,rgba(26,86,219,0.1),rgba(14,165,233,0.08))',
                        border: `1px solid ${isDark ? 'rgba(76,201,240,0.2)' : 'rgba(26,86,219,0.14)'}`,
                        color: isDark ? '#93c5fd' : '#1e40af',
                      } : {
                        background: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.9)',
                        border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : '#e2e8f0'}`,
                        color: isDark ? '#e2e8f0' : '#0f172a',
                        boxShadow: isDark ? 'none' : '0 1px 3px rgba(0,0,0,0.05)',
                      }),
                    }}>
                      {msg.text}
                    </div>
                  </div>
                ))}
                <div ref={historyEndRef} />
              </div>
            </div>

            {/* ════════════════════════════════════════════════════════════
                PANEL 2 — RESPONSE & QUESTION (centre)
            ════════════════════════════════════════════════════════════ */}
            <div style={{
              flex: 1, minWidth: 0,
              display: 'flex', flexDirection: 'column',
              borderRight: `1px solid ${border}`,
            }}>
              {/* Panel header */}
              <div style={{
                padding: '12px 24px 10px', flexShrink: 0,
                borderBottom: `1px solid ${border}`,
                background: isDark ? 'rgba(0,0,0,0.12)' : 'rgba(255,255,255,0.5)',
              }}>
                <div style={{
                  fontSize: '11px', fontWeight: 600, letterSpacing: '0.12em',
                  textTransform: 'uppercase',
                  color: isDark ? '#94a8c4' : '#64748b',
                }}>
                  {state === S.LISTENING ? '⬤ Listening' :
                   state === S.PROCESSING ? '⬤ Processing' :
                   state === S.SPEAKING ? '⬤ Response' :
                   'Active Session'}
                </div>
              </div>

              {/* Transcript area */}
              {transcript && ![S.IDLE, S.CONNECTING].includes(state) && (
                <div style={{
                  padding: '16px 24px 0', flexShrink: 0,
                }}>
                  <div style={{
                    padding: '10px 16px',
                    borderRadius: '12px 12px 4px 12px',
                    fontSize: '14px', fontWeight: 500, lineHeight: 1.5,
                    background: isDark ? 'rgba(26,86,219,0.13)' : '#eff6ff',
                    border: `1px solid ${isDark ? 'rgba(26,86,219,0.28)' : '#bfdbfe'}`,
                    color: isDark ? '#93c5fd' : '#1e40af',
                    animation: 'jv-msg-in 0.2s ease forwards',
                    maxWidth: '100%',
                  }}>
                    <span style={{
                      fontSize: '10px', fontWeight: 600, letterSpacing: '0.12em',
                      textTransform: 'uppercase', opacity: 0.7, display: 'block', marginBottom: '3px',
                    }}>You said</span>
                    &ldquo;{transcript}&rdquo;
                  </div>
                </div>
              )}

              {/* Response display — word by word, main content area */}
              <div className="jv-scroll" style={{
                flex: 1, overflowY: 'auto',
                padding: '20px 24px',
                display: 'flex', alignItems: displayedWords.length ? 'flex-start' : 'center',
                justifyContent: 'center',
              }}>
                {displayedWords.length > 0 ? (
                  <div style={{ width: '100%' }}>
                    {/* Response text — properly sized and formatted */}
                    <div style={{
                      fontSize: '15px', lineHeight: 1.75,
                      color: isDark ? '#f0f1ed' : '#0f172a',
                      fontWeight: 400,
                      letterSpacing: '0.01em',
                    }}>
                      {/* Render paragraphs if response has line breaks */}
                      {response.split(/\n\n+/).map((para, pi) => (
                        <p key={pi} style={{
                          margin: pi === 0 ? '0 0 12px' : '0 0 12px',
                          fontSize: pi === 0 && response.split(/\n\n+/).length > 1 ? '16px' : '15px',
                          fontWeight: pi === 0 && response.split(/\n\n+/).length > 1 ? 500 : 400,
                        }}>
                          {/* Show words only up to what's been revealed */}
                          {(() => {
                            const paraWords = para.trim().split(/\s+/)
                            const paraStart = response.split(/\n\n+/).slice(0, pi).reduce((acc, p) => acc + p.trim().split(/\s+/).length, 0)
                            return paraWords.map((word, wi) => {
                              const globalIdx = paraStart + wi
                              if (globalIdx >= displayedWords.length) return null
                              return (
                                <span
                                  key={wi}
                                  style={{
                                    display: 'inline',
                                    ...(globalIdx === displayedWords.length - 1 ? {
                                      animation: 'jv-word-in 0.16s ease forwards',
                                    } : {}),
                                  }}
                                >
                                  {word}{' '}
                                </span>
                              )
                            })
                          })()}
                        </p>
                      ))}
                      {/* Blinking cursor while typing */}
                      {isTyping && (
                        <span style={{
                          display: 'inline-block', width: '2px', height: '16px',
                          background: isDark ? '#4CC9F0' : '#1a56db',
                          marginLeft: '2px', verticalAlign: 'text-bottom',
                          animation: 'jv-blink 0.7s ease infinite', borderRadius: '1px',
                        }} />
                      )}
                    </div>
                  </div>
                ) : (
                  <div style={{
                    textAlign: 'center',
                    color: isDark ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.2)',
                    userSelect: 'none',
                  }}>
                    {state === S.CONNECTING ? (
                      <div style={{ fontSize: '14px' }}>Connecting to Jarvis…</div>
                    ) : state === S.READY ? (
                      <>
                        <div style={{ fontSize: '15px', fontWeight: 500, marginBottom: '6px', color: isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.4)' }}>
                          Ask me anything
                        </div>
                        <div style={{ fontSize: '13px' }}>
                          Speak using the mic, or type below
                        </div>
                      </>
                    ) : state === S.PROCESSING ? (
                      <div style={{ fontSize: '14px', color: isDark ? '#fbbf24' : '#d97706' }}>
                        Processing your request…
                      </div>
                    ) : null}
                  </div>
                )}
              </div>

              {/* ── Text input row (bottom of centre panel) ──────────────── */}
              <div style={{
                padding: '14px 20px 18px', flexShrink: 0,
                borderTop: `1px solid ${border}`,
                background: isDark ? 'rgba(0,0,0,0.18)' : 'rgba(255,255,255,0.55)',
                backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
              }}>
                {/* Input + send */}
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  <input
                    className="jv-input"
                    type="text"
                    value={inputText}
                    onChange={e => setInputText(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
                    placeholder="Type a message or command…"
                    disabled={state === S.PROCESSING || state === S.CONNECTING}
                    style={{
                      flex: 1, borderRadius: '22px', padding: '11px 18px',
                      fontSize: '14px', fontFamily: "'Inter',system-ui,sans-serif",
                      outline: 'none', transition: 'border-color 0.15s, box-shadow 0.15s',
                      background: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.9)',
                      border: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : '#e2e8f0'}`,
                      color: isDark ? '#f0f1ed' : '#0f172a',
                      boxShadow: isDark ? 'none' : '0 1px 4px rgba(0,0,0,0.04)',
                    }}
                  />
                  <button
                    className="jv-mic-btn"
                    onClick={inputText.trim() ? handleSend : handleMicClick}
                    disabled={state === S.PROCESSING || state === S.CONNECTING}
                    title={inputText.trim() ? 'Send message' : state === S.LISTENING ? 'Stop' : 'Speak'}
                    style={{
                      width: '44px', height: '44px', borderRadius: '50%', flexShrink: 0,
                      border: 'none',
                      cursor: (state === S.PROCESSING || state === S.CONNECTING) ? 'not-allowed' : 'pointer',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      transition: 'all 0.16s ease',
                      ...(inputText.trim()
                        ? { background: 'linear-gradient(135deg,#1a56db,#0ea5e9)', color: 'white', boxShadow: '0 4px 16px rgba(26,86,219,0.35)' }
                        : state === S.LISTENING
                          ? { background: '#ef4444', color: 'white', boxShadow: '0 4px 16px rgba(239,68,68,0.4)', animation: 'jv-ring-pulse 1.5s ease infinite' }
                          : { background: isDark ? 'rgba(76,201,240,0.12)' : 'rgba(26,86,219,0.09)', color: isDark ? '#4CC9F0' : '#1a56db' }
                      ),
                    }}
                  >
                    {inputText.trim() ? <Send size={17} /> : state === S.LISTENING ? <MicOff size={17} /> : <Mic size={17} />}
                  </button>
                </div>
              </div>
            </div>

            {/* ════════════════════════════════════════════════════════════
                PANEL 3 — JARVIS WAVEFORM (right)
            ════════════════════════════════════════════════════════════ */}
            <div className="jv-right" style={{
              width: '280px', minWidth: '280px', flexShrink: 0,
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0',
              background: isDark
                ? 'linear-gradient(175deg, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0.15) 100%)'
                : 'linear-gradient(175deg, #f0f4ff 0%, #e8efff 100%)',
              backgroundImage: isDark
                ? `linear-gradient(175deg,rgba(0,0,0,0.35),rgba(0,0,0,0.15)),
                   linear-gradient(rgba(76,201,240,0.04) 1px, transparent 1px),
                   linear-gradient(90deg, rgba(76,201,240,0.04) 1px, transparent 1px)`
                : `linear-gradient(175deg,#f0f4ff,#e8efff),
                   linear-gradient(rgba(26,86,219,0.05) 1px, transparent 1px),
                   linear-gradient(90deg, rgba(26,86,219,0.05) 1px, transparent 1px)`,
              backgroundSize: isDark ? 'auto, 22px 22px, 22px 22px' : 'auto, 22px 22px, 22px 22px',
            }}>

              {/* JARVIS branding */}
              <div style={{
                width: '100%', padding: '24px 24px 0',
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px',
              }}>
                <div style={{
                  fontSize: '20px', fontWeight: 800, letterSpacing: '0.3em',
                  textTransform: 'uppercase',
                  background: 'linear-gradient(90deg,#1a56db,#0ea5e9,#4CC9F0)',
                  WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text',
                }}>JARVIS</div>
                <div style={{
                  fontSize: '11px', fontWeight: 400, letterSpacing: '0.16em',
                  textTransform: 'uppercase',
                  color: isDark ? 'rgba(255,255,255,0.35)' : 'rgba(26,86,219,0.5)',
                }}>Voice Assistant</div>
              </div>

              {/* Waveform + orbital rings */}
              <div style={{
                flex: 1, width: '100%',
                display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                padding: '8px 16px',
                position: 'relative',
              }}>
                {/* Outer orbital ring */}
                {isActive && (
                  <div style={{
                    position: 'absolute', top: '50%', left: '50%',
                    width: '220px', height: '220px', borderRadius: '50%',
                    border: `1px solid ${isDark ? 'rgba(76,201,240,0.1)' : 'rgba(26,86,219,0.08)'}`,
                    animation: 'jv-orbit 16s linear infinite',
                    pointerEvents: 'none',
                  }}>
                    <div style={{
                      position: 'absolute', top: '5px', left: '50%',
                      width: '6px', height: '6px', borderRadius: '50%',
                      background: isDark ? '#4CC9F0' : '#1a56db',
                      transform: 'translateX(-50%)',
                      boxShadow: `0 0 10px ${isDark ? '#4CC9F0' : '#1a56db'}`,
                    }} />
                  </div>
                )}
                {/* Inner orbital ring */}
                {isActive && (
                  <div style={{
                    position: 'absolute', top: '50%', left: '50%',
                    width: '160px', height: '160px', borderRadius: '50%',
                    border: `1px solid ${isDark ? 'rgba(14,165,233,0.08)' : 'rgba(14,165,233,0.08)'}`,
                    animation: 'jv-orbit-ccw 10s linear infinite',
                    pointerEvents: 'none',
                  }}>
                    <div style={{
                      position: 'absolute', bottom: '4px', right: '4px',
                      width: '4px', height: '4px', borderRadius: '50%',
                      background: '#0ea5e9', boxShadow: '0 0 7px #0ea5e9',
                    }} />
                  </div>
                )}

                {/* Waveform (clickable) */}
                <div style={{ width: '100%', zIndex: 1 }}>
                  {renderWaveform()}
                </div>

                {/* State label */}
                <div style={{
                  marginTop: '10px',
                  fontSize: '13px', fontWeight: 600, letterSpacing: '0.04em',
                  textAlign: 'center', color: labelColor,
                  transition: 'color 0.3s ease',
                }}>
                  {LABEL[state]}
                </div>
                <div style={{
                  marginTop: '4px',
                  fontSize: '12px', fontWeight: 400,
                  textAlign: 'center',
                  color: isDark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.35)',
                }}>
                  {SUBLABEL[state]}
                </div>
              </div>

              {/* Big mic button */}
              <div style={{
                width: '100%', padding: '0 24px 28px',
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px',
              }}>
                <button
                  className="jv-mic-btn"
                  onClick={handleMicClick}
                  disabled={state === S.PROCESSING || state === S.CONNECTING}
                  title={state === S.LISTENING ? 'Stop recording' : state === S.SPEAKING ? 'Interrupt' : 'Start speaking'}
                  style={{
                    width: '72px', height: '72px', borderRadius: '50%',
                    border: 'none',
                    cursor: (state === S.PROCESSING || state === S.CONNECTING) ? 'not-allowed' : 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    transition: 'all 0.18s ease',
                    ...(state === S.LISTENING
                      ? {
                          background: '#ef4444', color: 'white',
                          boxShadow: '0 0 0 0 rgba(239,68,68,0.5)',
                          animation: 'jv-ring-pulse 1.4s ease infinite',
                        }
                      : state === S.SPEAKING
                        ? {
                            background: isDark ? 'rgba(76,201,240,0.2)' : 'rgba(14,165,233,0.15)',
                            color: isDark ? '#4CC9F0' : '#0ea5e9',
                            border: `2px solid ${isDark ? 'rgba(76,201,240,0.4)' : 'rgba(14,165,233,0.35)'}`,
                            boxShadow: isDark ? '0 0 24px rgba(76,201,240,0.2)' : '0 0 24px rgba(14,165,233,0.15)',
                          }
                        : [S.PROCESSING, S.CONNECTING].includes(state)
                          ? {
                              background: isDark ? 'rgba(251,191,36,0.12)' : 'rgba(217,119,6,0.08)',
                              color: isDark ? '#fbbf24' : '#d97706',
                              border: `2px solid ${isDark ? 'rgba(251,191,36,0.25)' : 'rgba(217,119,6,0.2)'}`,
                            }
                          : {
                              background: 'linear-gradient(135deg,#1a56db,#0ea5e9)',
                              color: 'white',
                              boxShadow: '0 6px 24px rgba(26,86,219,0.4)',
                            }
                    ),
                  }}
                >
                  {state === S.LISTENING
                    ? <MicOff size={26} />
                    : <Mic size={26} />
                  }
                </button>

                {/* Mic label */}
                <div style={{
                  fontSize: '11px', fontWeight: 500, letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  color: state === S.LISTENING ? '#ef4444'
                    : state === S.SPEAKING ? (isDark ? '#4CC9F0' : '#0ea5e9')
                    : isDark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.35)',
                  transition: 'color 0.25s ease',
                }}>
                  {state === S.LISTENING ? 'Tap to stop'
                    : state === S.SPEAKING ? 'Tap to interrupt'
                    : state === S.PROCESSING ? 'Processing…'
                    : state === S.CONNECTING ? 'Connecting…'
                    : state === S.ERROR ? 'Tap to retry'
                    : 'Tap to speak'}
                </div>
              </div>

            </div>
          </div>
        </div>
      </div>
    </>
  )
}
