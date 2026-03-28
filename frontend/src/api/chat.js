import client, { getCsrfToken } from './client'

// ── Session CRUD ──────────────────────────────────────────────────────────────

export const listSessions = async () => {
  const { data } = await client.get('/chat/sessions')
  return data
}

export const createSession = async (title = 'New Chat') => {
  const { data } = await client.post('/chat/sessions', { title })
  return data
}

export const renameSession = async (sessionId, title) => {
  const { data } = await client.patch(`/chat/sessions/${sessionId}`, { title })
  return data
}

export const deleteSession = async (sessionId) => {
  const { data } = await client.delete(`/chat/sessions/${sessionId}`)
  return data
}

// ── Messages ──────────────────────────────────────────────────────────────────

export const sendMessage = async (message, context = {}, file = null, sessionId = null) => {
  if (file) {
    const formData = new FormData()
    formData.append('message', message || '')
    formData.append('context', JSON.stringify(context || {}))
    formData.append('file', file)
    if (sessionId) formData.append('session_id', sessionId)
    const { data } = await client.post('/chat', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  }

  const { data } = await client.post('/chat', { message, context, session_id: sessionId })
  return data
}

export const getChatHistory = async (sessionId = null) => {
  const params = {}
  if (sessionId) params.session_id = sessionId
  const { data } = await client.get('/chat/history', { params })
  return data
}

export const transcribeAudio = async (audioBlob) => {
  const formData = new FormData()
  formData.append('audio', audioBlob, 'voice.webm')
  const { data } = await client.post('/chat/transcribe', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/**
 * Stream an AI response via SSE.
 */
export const sendStreamingMessage = async (message, context = {}, onToken, onDone, sessionId = null) => {
  const { getAccessToken } = await import('./auth')
  const baseURL = '/api'
  const headers = { 'Content-Type': 'application/json' }
  const token = getAccessToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  } else {
    // No JWT in memory — cookie/session auth is active; must include CSRF token
    const csrf = getCsrfToken()
    if (csrf) headers['X-CSRF-Token'] = csrf
  }

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 90000)

  const response = await fetch(`${baseURL}/chat/stream`, {
    method: 'POST',
    credentials: 'include',
    headers,
    body: JSON.stringify({ message, context, session_id: sessionId }),
    signal: controller.signal,
  })

  if (response.status === 401) {
    window.location.href = '/login'
    return
  }

  if (!response.ok) {
    throw new Error(`Stream request failed: HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const processLines = (lines) => {
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const raw = line.slice(6).trim()
      if (!raw) continue
      try {
        const event = JSON.parse(raw)
        if (event.done) {
          onDone?.(event)
        } else if (event.token) {
          onToken?.(event.token)
        }
      } catch {
        // partial JSON chunk
      }
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      processLines(lines)
    }
    if (buffer.trim()) processLines([buffer])
  } finally {
    clearTimeout(timeout)
  }
}
