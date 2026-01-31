/**
 * useSwipe - Touch swipe gesture detection
 *
 * Detects horizontal swipe gestures with configurable thresholds.
 * Used for mobile sidebar navigation.
 */

import { onMounted, onUnmounted, ref } from 'vue'

export function useSwipe(options = {}) {
  const {
    threshold = 50,          // Minimum swipe distance
    edgeThreshold = 30,      // Distance from edge for edge swipes
    velocityThreshold = 0.3, // Minimum velocity (px/ms)
  } = options

  const startX = ref(0)
  const startY = ref(0)
  const startTime = ref(0)
  const isEdgeSwipe = ref(false)
  const isSwiping = ref(false)

  // Callbacks
  let onSwipeLeft = null
  let onSwipeRight = null
  let onEdgeSwipeRight = null // Swipe from left edge

  function handleTouchStart(e) {
    const touch = e.touches[0]
    startX.value = touch.clientX
    startY.value = touch.clientY
    startTime.value = Date.now()

    // Check if starting from left edge
    isEdgeSwipe.value = touch.clientX <= edgeThreshold
    isSwiping.value = true
  }

  function handleTouchMove(e) {
    if (!isSwiping.value) return

    // Prevent scroll while swiping horizontally
    const touch = e.touches[0]
    const diffX = Math.abs(touch.clientX - startX.value)
    const diffY = Math.abs(touch.clientY - startY.value)

    // If mostly horizontal movement, prevent default
    if (diffX > diffY && diffX > 10) {
      // Don't prevent default - let scroll happen naturally
      // We'll just detect the swipe
    }
  }

  function handleTouchEnd(e) {
    if (!isSwiping.value) return
    isSwiping.value = false

    const touch = e.changedTouches[0]
    const diffX = touch.clientX - startX.value
    const diffY = touch.clientY - startY.value
    const timeDiff = Date.now() - startTime.value
    const velocity = Math.abs(diffX) / timeDiff

    // Ignore if mostly vertical
    if (Math.abs(diffY) > Math.abs(diffX)) return

    // Check threshold
    const meetsThreshold = Math.abs(diffX) > threshold || velocity > velocityThreshold
    if (!meetsThreshold) return

    if (diffX > 0) {
      // Swipe right
      if (isEdgeSwipe.value && onEdgeSwipeRight) {
        onEdgeSwipeRight()
      } else if (onSwipeRight) {
        onSwipeRight()
      }
    } else {
      // Swipe left
      if (onSwipeLeft) {
        onSwipeLeft()
      }
    }
  }

  function registerCallbacks(callbacks) {
    onSwipeLeft = callbacks.onSwipeLeft || null
    onSwipeRight = callbacks.onSwipeRight || null
    onEdgeSwipeRight = callbacks.onEdgeSwipeRight || null
  }

  function attachToElement(element) {
    if (!element) return

    element.addEventListener('touchstart', handleTouchStart, { passive: true })
    element.addEventListener('touchmove', handleTouchMove, { passive: true })
    element.addEventListener('touchend', handleTouchEnd, { passive: true })

    return () => {
      element.removeEventListener('touchstart', handleTouchStart)
      element.removeEventListener('touchmove', handleTouchMove)
      element.removeEventListener('touchend', handleTouchEnd)
    }
  }

  return {
    isSwiping,
    registerCallbacks,
    attachToElement,
  }
}
