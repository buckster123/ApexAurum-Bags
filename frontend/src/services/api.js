import axios from 'axios'

// Ensure baseURL has https:// prefix (Railway env var sometimes missing it)
let baseURL = import.meta.env.VITE_API_URL || ''
if (baseURL && !baseURL.startsWith('http://') && !baseURL.startsWith('https://')) {
  baseURL = 'https://' + baseURL
}

const api = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Separate instance for refresh - has baseURL but NO interceptors (avoids infinite 401 loop)
const refreshClient = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Graceful session expiry - emit event instead of hard redirect
function handleSessionExpiry(reason) {
  // Clear tokens gracefully
  localStorage.removeItem('accessToken')
  localStorage.removeItem('refreshToken')

  // Dispatch custom event for app to handle gracefully
  window.dispatchEvent(new CustomEvent('session-expired', {
    detail: { reason }
  }))

  // Only redirect if we're not already on login/register
  const path = window.location.pathname
  if (!path.includes('/login') && !path.includes('/register')) {
    // Small delay for any pending operations to complete
    setTimeout(() => {
      window.location.href = '/login?expired=true'
    }, 100)
  }
}

// Request interceptor - add auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('accessToken')
  if (token && token !== 'undefined' && token !== 'null') {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor - handle 401 errors with grace
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // If 401 and we haven't tried refreshing yet
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      const refreshToken = localStorage.getItem('refreshToken')

      // No refresh token available
      if (!refreshToken || refreshToken === 'undefined' || refreshToken === 'null') {
        handleSessionExpiry('no_refresh_token')
        return Promise.reject(new Error('Session expired. Please sign in again.'))
      }

      // Try refresh with retry on network errors
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const response = await refreshClient.post('/api/v1/auth/refresh', {
            refresh_token: refreshToken
          })

          const { access_token, refresh_token: new_refresh_token } = response.data
          localStorage.setItem('accessToken', access_token)
          localStorage.setItem('refreshToken', new_refresh_token)

          // Retry original request with new token
          originalRequest.headers.Authorization = `Bearer ${access_token}`
          return api(originalRequest)
        } catch (refreshError) {
          // If it's a network error and this is the first attempt, wait and retry
          if (attempt === 0 && !refreshError.response) {
            await new Promise(resolve => setTimeout(resolve, 1000))
            continue
          }

          // Refresh failed - handle gracefully
          const reason = refreshError.response?.status === 401
            ? 'refresh_token_expired'
            : 'refresh_failed'

          handleSessionExpiry(reason)
          return Promise.reject(new Error('Your session has ended. Please sign in to continue.'))
        }
      }
    }

    return Promise.reject(error)
  }
)

export default api
