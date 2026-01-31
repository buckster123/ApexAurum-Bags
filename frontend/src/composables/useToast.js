/**
 * useToast - Global toast notification system
 *
 * Singleton composable for showing transient notifications.
 * Types: success, error, warning, info
 */

import { ref } from 'vue'

const toasts = ref([])
let nextId = 0

function showToast(message, type = 'error', duration = 4000) {
  const id = nextId++
  toasts.value.push({ id, message, type })

  if (duration > 0) {
    setTimeout(() => removeToast(id), duration)
  }

  return id
}

function removeToast(id) {
  const idx = toasts.value.findIndex(t => t.id === id)
  if (idx !== -1) {
    toasts.value.splice(idx, 1)
  }
}

export function useToast() {
  return { toasts, showToast, removeToast }
}
