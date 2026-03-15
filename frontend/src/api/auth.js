import client from './client'

// ── JWT token management (in-memory; cookie for session is also sent automatically) ──
let _accessToken = null

export const setAccessToken = (token) => {
  _accessToken = token
  if (token) {
    client.defaults.headers.common['Authorization'] = `Bearer ${token}`
  } else {
    delete client.defaults.headers.common['Authorization']
  }
}

export const getAccessToken = () => _accessToken

export const login = async (username, password) => {
  const { data } = await client.post('/auth/login', { username, password })
  if (data.access_token) {
    setAccessToken(data.access_token)
    // Persist refresh token in sessionStorage for page-refresh recovery
    if (data.refresh_token) {
      sessionStorage.setItem('ts_refresh', data.refresh_token)
    }
  }
  return data
}

export const logout = async () => {
  setAccessToken(null)
  sessionStorage.removeItem('ts_refresh')
  const { data } = await client.post('/auth/logout')
  return data
}

export const refreshTokens = async () => {
  const refresh_token = sessionStorage.getItem('ts_refresh')
  if (!refresh_token) return null
  try {
    const { data } = await client.post('/auth/refresh', { refresh_token })
    if (data.access_token) {
      setAccessToken(data.access_token)
      if (data.refresh_token) sessionStorage.setItem('ts_refresh', data.refresh_token)
    }
    return data
  } catch {
    sessionStorage.removeItem('ts_refresh')
    return null
  }
}

export const getMe = async () => {
  const { data } = await client.get('/auth/me')
  return data
}
