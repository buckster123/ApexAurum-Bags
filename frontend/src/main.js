import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/main.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')

// ═══════════════════════════════════════════════════════════════════════════════
// Global Error Reporting (fire-and-forget to backend)
// ═══════════════════════════════════════════════════════════════════════════════

function reportError(errorType, message, source, line) {
  try {
    let apiUrl = import.meta.env.VITE_API_URL || ''
    if (apiUrl && !apiUrl.startsWith('http://') && !apiUrl.startsWith('https://')) {
      apiUrl = 'https://' + apiUrl
    }
    const payload = {
      error_type: String(errorType || 'UnknownError').slice(0, 200),
      message: String(message || '').slice(0, 2000),
    }
    // Only send filename, not full path
    if (source) {
      const filename = String(source).split('/').pop().split('\\').pop()
      payload.source = filename.slice(0, 200)
    }
    if (line != null) payload.line = Number(line) || 0
    payload.page = window.location.pathname

    fetch(`${apiUrl}/api/v1/errors/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).catch(() => {}) // Silently ignore reporting failures
  } catch {
    // Never let error reporting cause more errors
  }
}

window.addEventListener('error', (event) => {
  reportError(
    event.error?.name || 'Error',
    event.message,
    event.filename,
    event.lineno,
  )
})

window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason
  reportError(
    reason?.name || 'UnhandledRejection',
    reason?.message || String(reason || '').slice(0, 2000),
  )
})
