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
