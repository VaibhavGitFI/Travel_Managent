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

// Response interceptor — handle 401 globally
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clear any local auth state and redirect to login
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default client
