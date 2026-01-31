import { ref } from 'vue'

/**
 * Format ISO date string to relative time (e.g., "5m ago", "2h ago", "3d ago")
 */
export function formatRelativeTime(isoStr) {
  if (!isoStr) return ''
  const diff = Date.now() - new Date(isoStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return new Date(isoStr).toLocaleDateString()
}

/**
 * Training job status -> Tailwind color classes
 */
export const statusColorMap = {
  pending: 'bg-gray-500/20 text-gray-400',
  uploading: 'bg-blue-500/20 text-blue-400',
  running: 'bg-amber-500/20 text-amber-400',
  completed: 'bg-green-500/20 text-green-400',
  failed: 'bg-red-500/20 text-red-400',
}

export function getStatusColor(status) {
  return statusColorMap[status] || 'bg-gray-500/20 text-gray-400'
}

/**
 * Composable for confirm-before-delete pattern.
 * First click sets confirmId, 3s timeout resets. Second click on same ID confirms.
 */
export function useConfirmDelete(timeout = 3000) {
  const confirmId = ref(null)
  let timer = null

  function requestDelete(id, onConfirm) {
    if (confirmId.value === id) {
      // Confirmed — execute delete
      if (timer) clearTimeout(timer)
      confirmId.value = null
      onConfirm(id)
    } else {
      // First click — ask for confirmation
      confirmId.value = id
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        confirmId.value = null
      }, timeout)
    }
  }

  function isConfirming(id) {
    return confirmId.value === id
  }

  return { confirmId, requestDelete, isConfirming }
}
