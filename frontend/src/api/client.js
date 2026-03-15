import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor
client.interceptors.request.use(
  (config) => {
    config.withCredentials = true
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor — handle 401 and 429 globally
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clear any local auth state and redirect to login
      window.location.href = '/login'
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
