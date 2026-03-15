import client from './client'

export const sendMessage = async (message, context = {}, file = null) => {
  if (file) {
    const formData = new FormData()
    formData.append('message', message || '')
    formData.append('context', JSON.stringify(context || {}))
    formData.append('file', file)
    const { data } = await client.post('/chat', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  }

  const { data } = await client.post('/chat', { message, context })
  return data
}

export const getChatHistory = async () => {
  const { data } = await client.get('/chat/history')
  return data
}

/**
 * Stream an AI response via SSE.
 * @param {string} message
 * @param {object} context
 * @param {(token: string) => void} onToken  — called for each text chunk
 * @param {(meta: object) => void} onDone    — called with {action_cards, intent, ai_powered}
 */
export const sendStreamingMessage = async (message, context = {}, onToken, onDone) => {
  const baseURL = import.meta.env.DEV ? 'http://localhost:3399/api' : '/api'
  const response = await fetch(`${baseURL}/chat/stream`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context }),
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

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() // keep any incomplete trailing line

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
        // malformed JSON chunk — skip
      }
    }
  }
}
