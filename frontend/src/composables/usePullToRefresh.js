/**
 * usePullToRefresh - Pull-down gesture for refreshing content
 *
 * Attaches to a scrollable element and triggers refresh callback
 * when pulled down past threshold while at top.
 */

import { ref, onUnmounted } from 'vue'
import { useHaptic } from './useHaptic'

export function usePullToRefresh(options = {}) {
  const {
    threshold = 80,      // Pull distance to trigger refresh
    resistance = 2.5,    // Pull resistance (higher = harder to pull)
    maxPull = 120,       // Maximum visual pull distance
  } = options

  const { haptics } = useHaptic()

  const isPulling = ref(false)
  const pullDistance = ref(0)
  const isRefreshing = ref(false)
  const passedThreshold = ref(false)

  let startY = 0
  let scrollTop = 0
  let onRefresh = null
  let cleanup = null

  function handleTouchStart(e) {
    if (isRefreshing.value) return

    const touch = e.touches[0]
    startY = touch.clientY
    scrollTop = e.currentTarget.scrollTop
  }

  function handleTouchMove(e) {
    if (isRefreshing.value) return

    // Only activate if at top of scroll
    if (e.currentTarget.scrollTop > 0) {
      isPulling.value = false
      pullDistance.value = 0
      return
    }

    const touch = e.touches[0]
    const deltaY = touch.clientY - startY

    // Only handle pull down
    if (deltaY <= 0) {
      isPulling.value = false
      pullDistance.value = 0
      return
    }

    isPulling.value = true

    // Apply resistance
    const pull = Math.min(deltaY / resistance, maxPull)
    pullDistance.value = pull

    // Haptic when passing threshold
    if (pull >= threshold && !passedThreshold.value) {
      passedThreshold.value = true
      haptics.pullRefresh()
    } else if (pull < threshold) {
      passedThreshold.value = false
    }
  }

  async function handleTouchEnd() {
    if (!isPulling.value || isRefreshing.value) return

    if (pullDistance.value >= threshold && onRefresh) {
      isRefreshing.value = true
      pullDistance.value = threshold // Lock at threshold during refresh

      try {
        await onRefresh()
      } finally {
        isRefreshing.value = false
        pullDistance.value = 0
        passedThreshold.value = false
      }
    } else {
      pullDistance.value = 0
      passedThreshold.value = false
    }

    isPulling.value = false
  }

  function attach(element, refreshCallback) {
    if (!element) return

    onRefresh = refreshCallback

    element.addEventListener('touchstart', handleTouchStart, { passive: true })
    element.addEventListener('touchmove', handleTouchMove, { passive: false })
    element.addEventListener('touchend', handleTouchEnd, { passive: true })

    cleanup = () => {
      element.removeEventListener('touchstart', handleTouchStart)
      element.removeEventListener('touchmove', handleTouchMove)
      element.removeEventListener('touchend', handleTouchEnd)
    }

    return cleanup
  }

  onUnmounted(() => {
    if (cleanup) cleanup()
  })

  return {
    isPulling,
    pullDistance,
    isRefreshing,
    passedThreshold,
    threshold,
    attach,
  }
}
