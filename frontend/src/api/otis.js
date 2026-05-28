import client from './client'

/**
 * OTIS Voice Assistant API
 *
 * Follows TravelSync API patterns:
 * - Uses axios client with CSRF tokens
 * - Returns { data } from responses
 * - Handles authentication automatically
 */

// ── Status & Permissions ──────────────────────────────────────────────────────

/**
 * Check OTIS availability and user permissions
 * @returns {Promise<{success: boolean, enabled: boolean, available: boolean, permissions: object, services: object, session: object}>}
 */
export const getOtisStatus = async () => {
  const { data } = await client.get('/otis/status')
  return data
}

// ── Session Management ────────────────────────────────────────────────────────

/**
 * Start a new OTIS voice session
 * Rate limited: 10 per hour
 * @returns {Promise<{success: boolean, session_id: string, started_at: string}>}
 */
export const startOtisSession = async () => {
  const { data } = await client.post('/otis/start')
  return data
}

/**
 * Stop an active OTIS session
 * @param {string} [sessionId] - Session ID (optional, uses active session if omitted)
 * @returns {Promise<{success: boolean, session_id: string, duration_seconds: number, total_turns: number}>}
 */
export const stopOtisSession = async (sessionId = null) => {
  const { data } = await client.post('/otis/stop', { session_id: sessionId })
  return data
}

/**
 * List user's voice sessions
 * @param {number} [limit=20] - Number of sessions to return
 * @returns {Promise<{success: boolean, sessions: Array, total: number}>}
 */
export const listOtisSessions = async (limit = 20) => {
  const { data } = await client.get('/otis/sessions', { params: { limit } })
  return data
}

/**
 * Get detailed session information
 * @param {string} sessionId - Session ID
 * @returns {Promise<{success: boolean, session: object, conversation: Array, commands: Array}>}
 */
export const getOtisSession = async (sessionId) => {
  const { data } = await client.get(`/otis/sessions/${sessionId}`)
  return data
}

/**
 * Delete a voice session and all related data
 * @param {string} sessionId - Session ID
 * @returns {Promise<{success: boolean}>}
 */
export const deleteOtisSession = async (sessionId) => {
  const { data } = await client.delete(`/otis/sessions/${sessionId}`)
  return data
}

// ── Command History ───────────────────────────────────────────────────────────

/**
 * Get command execution history
 * @param {number} [limit=50] - Number of commands to return
 * @returns {Promise<{success: boolean, commands: Array, total: number}>}
 */
export const getOtisCommands = async (limit = 50) => {
  const { data } = await client.get('/otis/commands', { params: { limit } })
  return data
}

// ── Analytics ─────────────────────────────────────────────────────────────────

/**
 * Get voice usage analytics
 * @param {string} [period='7d'] - Time period (e.g., "7d", "30d")
 * @returns {Promise<{success: boolean, summary: object, daily: Array}>}
 */
export const getOtisAnalytics = async (period = '7d') => {
  const { data } = await client.get('/otis/analytics', { params: { period } })
  return data
}

// ── User Settings ─────────────────────────────────────────────────────────────

/**
 * Get user's OTIS settings
 * @returns {Promise<{success: boolean, settings: object}>}
 */
export const getOtisSettings = async () => {
  const { data } = await client.get('/otis/settings')
  return data
}

/**
 * Update user's OTIS settings
 * @param {object} settings - Settings object (voice_speed, voice_pitch, auto_listen, confirm_actions)
 * @returns {Promise<{success: boolean, settings: object}>}
 */
export const updateOtisSettings = async (settings) => {
  const { data } = await client.put('/otis/settings', settings)
  return data
}

// ── Command Validation ────────────────────────────────────────────────────────

/**
 * Pre-validate a voice command before sending to OTIS
 * @param {string} command - Command text to validate
 * @returns {Promise<{success: boolean, valid: boolean, needs_confirmation: boolean, risk_reason: string|null}>}
 */
export const validateOtisCommand = async (command) => {
  const { data } = await client.post('/otis/validate', { command })
  return data
}

/**
 * Send a voice/text command to OTIS via REST (primary channel)
 * More reliable than WebSocket for command processing.
 * @param {string} command - Command text
 * @param {string|null} sessionId - Active session ID
 * @returns {Promise<{success: boolean, response: string, session_id: string, timestamp: string}>}
 */
export const sendOtisCommandRest = async (command, sessionId = null) => {
  const { data } = await client.post('/otis/command', {
    command,
    session_id: sessionId,
  })
  return data
}

// ── WebSocket Connection ──────────────────────────────────────────────────────

/**
 * Create OTIS WebSocket connection
 * @param {object} socket - Socket.io instance
 * @param {string} sessionId - OTIS session ID
 * @param {object} callbacks - Event callbacks
 * @returns {object} - Event handlers for cleanup
 */
export const connectOtisWebSocket = (socket, sessionId, callbacks = {}) => {
  const {
    onSessionStarted = () => {},
    onProcessing = () => {},
    onResponse = () => {},
    onError = () => {},
    onSessionStopped = () => {},
    onConfirmRequired = () => {},
  } = callbacks

  // Register event listeners
  socket.on('otis:session_started', onSessionStarted)
  socket.on('otis:processing', onProcessing)
  socket.on('otis:response', onResponse)
  socket.on('otis:error', onError)
  socket.on('otis:session_stopped', onSessionStopped)
  socket.on('otis:confirm_required', onConfirmRequired)

  // Start session
  socket.emit('otis:start_session', { session_id: sessionId })

  // Return cleanup function
  return () => {
    socket.off('otis:session_started', onSessionStarted)
    socket.off('otis:processing', onProcessing)
    socket.off('otis:response', onResponse)
    socket.off('otis:error', onError)
    socket.off('otis:session_stopped', onSessionStopped)
    socket.off('otis:confirm_required', onConfirmRequired)
  }
}

/**
 * Send voice command via WebSocket
 * @param {object} socket - Socket.io instance
 * @param {string} sessionId - OTIS session ID
 * @param {string} command - Command text
 */
export const sendOtisCommand = (socket, sessionId, command) => {
  socket.emit('otis:process_command', {
    session_id: sessionId,
    command: command,
  })
}

/**
 * Stop OTIS session via WebSocket
 * @param {object} socket - Socket.io instance
 * @param {string} sessionId - OTIS session ID
 */
export const stopOtisWebSocket = (socket, sessionId) => {
  socket.emit('otis:stop_session', { session_id: sessionId })
}

// ── Voice I/O (Deepgram STT + ElevenLabs TTS) ────────────────────────────────

/**
 * Transcribe a voice audio blob using Deepgram (falls back to Gemini).
 * Mirrors the Chat page transcribeAudio pattern.
 * @param {Blob} audioBlob - Recorded audio blob (webm/ogg/mp4)
 * @returns {Promise<{success: boolean, text: string, provider: string}>}
 */
export const transcribeOtisAudio = async (audioBlob) => {
  const formData = new FormData()
  formData.append('audio', audioBlob, 'voice.webm')
  const { data } = await client.post('/otis/transcribe', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/**
 * Synthesise text to speech using ElevenLabs (Indian English voice).
 * Returns an audio Blob (audio/mpeg) ready for playback, or null on failure.
 * @param {string} text - Text to speak
 * @returns {Promise<Blob|null>}
 */
export const otisSpeak = async (text) => {
  try {
    const response = await client.post(
      '/otis/speak',
      { text },
      { responseType: 'blob' },
    )
    // Verify we got audio back (not a JSON error blob)
    if (response.data && response.data.type && response.data.type.includes('audio')) {
      return response.data
    }
    return null
  } catch {
    return null
  }
}
