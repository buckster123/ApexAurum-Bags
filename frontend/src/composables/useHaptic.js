/**
 * useHaptic - Vibration feedback for mobile devices
 *
 * Provides haptic feedback patterns for various interactions.
 * Gracefully degrades on devices without vibration support.
 */

import { ref } from 'vue'

// Global setting (localStorage backed)
const hapticEnabled = ref(localStorage.getItem('apexaurum_haptic_enabled') !== 'false')

export function useHaptic() {
  // Check vibration support
  const isSupported = 'vibrate' in navigator

  // Toggle haptic globally
  function setEnabled(enabled) {
    hapticEnabled.value = enabled
    localStorage.setItem('apexaurum_haptic_enabled', enabled ? 'true' : 'false')
  }

  // Core vibration function
  function vibrate(pattern) {
    if (!isSupported || !hapticEnabled.value) return false

    try {
      navigator.vibrate(pattern)
      return true
    } catch {
      return false
    }
  }

  // Predefined patterns
  const haptics = {
    // Light tap - button press, selection
    light: () => vibrate([10]),

    // Medium tap - message sent, action confirmed
    medium: () => vibrate([20]),

    // Strong pulse - easter egg activation
    strong: () => vibrate([50]),

    // Success pattern - achievement, completion
    success: () => vibrate([10, 50, 10]),

    // Double tap - favorites, toggles
    double: () => vibrate([10, 30, 10]),

    // Error - validation failed
    error: () => vibrate([30, 50, 30]),

    // PAC activation - mystical pattern
    pac: () => vibrate([30, 80, 20, 80, 30]),

    // Dev mode activation
    devMode: () => vibrate([15, 30, 15, 30, 15, 80]),

    // Konami key press
    konamiKey: () => vibrate([8]),

    // AZOTH letter
    azothLetter: () => vibrate([12]),

    // Pull refresh threshold reached
    pullRefresh: () => vibrate([15]),

    // Sidebar opened/closed
    sidebarToggle: () => vibrate([12]),
  }

  return {
    isSupported,
    hapticEnabled,
    setEnabled,
    vibrate,
    haptics,
  }
}
