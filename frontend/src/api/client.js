import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Helper to read a cookie by name
function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'))
  return match ? decodeURIComponent(match[2]) : null
}

// Request interceptor — attach CSRF token for state-changing requests
client.interceptors.request.use(
  (config) => {
    config.withCredentials = true
    const method = (config.method || 'get').toLowerCase()
    if (['post', 'put', 'patch', 'delete'].includes(method)) {
      const csrfToken = getCookie('csrf_token')
      if (csrfToken) {
        config.headers['X-CSRF-Token'] = csrfToken
      }
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor — handle 401 and 429 globally
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Only redirect if not already on login page and not a background check
      const isLoginPage = window.location.pathname === '/login' || window.location.pathname === '/'
      const isAuthCheck = error.config?.url?.includes('/auth/me') || error.config?.url?.includes('/auth/refresh')
      if (!isLoginPage && !isAuthCheck) {
        window.location.href = '/login'
      }
    }
    if (error.response?.status === 429) {
      const retryAfter = error.response.headers?.['retry-after']
      const msg = retryAfter
        ? `Too many requests. Please wait ${retryAfter}s before trying again.`
        : 'Too many requests. Please slow down and try again.'
      // Dynamically import toast to avoid circular dep
      import('react-hot-toast').then(({ default: toast }) => toast.error(msg))
    }
    return Promise.reject(error)
  }
)

export default client
