import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ── CSRF token cache ──────────────────────────────────────────────────────────
// In-memory cache so we always have the token even if the cookie is unavailable.
// Populated from: login response body, /auth/me response body, and the
// X-CSRF-Token response header that the backend sends on every authenticated reply.
let _csrfToken = null

function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'))
  return match ? decodeURIComponent(match[2]) : null
}

function getToken() {
  return _csrfToken || getCookie('csrf_token') || null
}

/** Call this after login / /me to seed the in-memory cache. */
export function updateCsrfToken(token) {
  if (token) _csrfToken = token
}

/**
 * Return the current CSRF token — checks in-memory cache first, then cookie.
 * Use this in raw fetch() calls that bypass the axios interceptor.
 */
export function getCsrfToken() {
  return _csrfToken || getCookie('csrf_token') || null
}

// ── Request interceptor — attach CSRF token ───────────────────────────────────
client.interceptors.request.use(
  (config) => {
    config.withCredentials = true
    const method = (config.method || 'get').toLowerCase()
    if (['post', 'put', 'patch', 'delete'].includes(method)) {
      const token = getToken()
      if (token) {
        config.headers['X-CSRF-Token'] = token
      }
    }
    return config
  },
  (error) => Promise.reject(error)
)

// ── Response interceptor — capture token + handle errors ─────────────────────
client.interceptors.response.use(
  (response) => {
    // Capture the CSRF token whenever the backend sends it back (every response)
    const headerToken = response.headers['x-csrf-token']
    if (headerToken) _csrfToken = headerToken

    // Also capture from response body (login / /me)
    const bodyToken = response.data?.csrf_token
    if (bodyToken) _csrfToken = bodyToken

    return response
  },
  async (error) => {
    const { response, config } = error

    // ── Auto-heal CSRF mismatch ────────────────────────────────────────────
    // When the CSRF token is missing or stale, transparently refresh it and
    // retry the original request once — the user never sees the 403.
    if (
      response?.status === 403 &&
      response?.data?.error?.toLowerCase().includes('csrf') &&
      !config._csrfRetried
    ) {
      config._csrfRetried = true
      try {
        // A GET to /auth/me triggers after_request which sets the new cookie
        // AND returns the token in the body — our response interceptor captures it.
        await client.get('/auth/me')
        const freshToken = getToken()
        if (freshToken) {
          config.headers['X-CSRF-Token'] = freshToken
          return client(config)
        }
      } catch {
        // If /auth/me fails (logged out), fall through to normal 401 handling
      }
    }

    // ── 401 — redirect to login ────────────────────────────────────────────
    if (response?.status === 401) {
      const isLoginPage = window.location.pathname === '/login' || window.location.pathname === '/'
      const isAuthCheck = config?.url?.includes('/auth/me') || config?.url?.includes('/auth/refresh')
      if (!isLoginPage && !isAuthCheck) {
        window.location.href = '/login'
      }
    }

    // ── 429 — rate limit toast ─────────────────────────────────────────────
    if (response?.status === 429) {
      const retryAfter = response.headers?.['retry-after']
      const msg = retryAfter
        ? `Too many requests. Please wait ${retryAfter}s before trying again.`
        : 'Too many requests. Please slow down and try again.'
      import('react-hot-toast').then(({ default: toast }) => toast.error(msg))
    }

    return Promise.reject(error)
  }
)

export default client
