/**
 * useSound - Web Audio API composable for ApexAurum
 *
 * Generates mystical tones for easter egg activations and UI feedback.
 * No external audio files needed - pure synthesis.
 */

import { ref } from 'vue'

// Singleton audio context (created on first user interaction)
let audioContext = null

// Sound enabled state (persisted to localStorage)
const soundEnabled = ref(localStorage.getItem('apexaurum_sounds') !== 'false')

/**
 * Initialize audio context (must be called after user interaction)
 */
function initAudio() {
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)()
  }
  // Resume if suspended (browser autoplay policy)
  if (audioContext.state === 'suspended') {
    audioContext.resume()
  }
  return audioContext
}

/**
 * Play a simple tone
 */
function playTone(frequency, duration, type = 'sine', volume = 0.3) {
  if (!soundEnabled.value) return

  try {
    const ctx = initAudio()
    const oscillator = ctx.createOscillator()
    const gainNode = ctx.createGain()

    oscillator.connect(gainNode)
    gainNode.connect(ctx.destination)

    oscillator.frequency.value = frequency
    oscillator.type = type

    // Envelope: quick attack, natural decay
    gainNode.gain.setValueAtTime(0, ctx.currentTime)
    gainNode.gain.linearRampToValueAtTime(volume, ctx.currentTime + 0.01)
    gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + duration)

    oscillator.start(ctx.currentTime)
    oscillator.stop(ctx.currentTime + duration)
  } catch (e) {
    // Audio not available, fail silently
  }
}

/**
 * Play a chord (multiple frequencies)
 */
function playChord(frequencies, duration, type = 'sine', volume = 0.15) {
  frequencies.forEach((freq, i) => {
    setTimeout(() => playTone(freq, duration, type, volume), i * 20)
  })
}

/**
 * Play an arpeggio (frequencies in sequence)
 */
function playArpeggio(frequencies, noteDuration, type = 'sine', volume = 0.25) {
  frequencies.forEach((freq, i) => {
    setTimeout(() => playTone(freq, noteDuration, type, volume), i * (noteDuration * 400))
  })
}

// ═══════════════════════════════════════════════════════════════
// SOUND LIBRARY - The Alchemical Tones
// ═══════════════════════════════════════════════════════════════

const sounds = {
  /**
   * Konami code - each key press
   * Ascending chime sequence (call with index 0-9)
   */
  konamiKey: (index) => {
    const baseFreq = 440 // A4
    const freq = baseFreq * Math.pow(2, index / 12) // Chromatic scale
    playTone(freq, 0.12, 'sine', 0.2)
  },

  /**
   * Dev Mode activation - The Apprentice awakens
   * Achievement unlock sound
   */
  devModeActivate: () => {
    // Major chord arpeggio: C5 - E5 - G5 - C6
    playArpeggio([523, 659, 784, 1047], 0.15, 'sine', 0.25)
  },

  /**
   * AZOTH letter typed - Deep resonance
   * Each letter builds the incantation
   */
  azothLetter: (index) => {
    // Deep tones, building tension: A2, Z, O, T, H
    const frequencies = [110, 123, 138, 155, 175] // Low register, ascending
    const freq = frequencies[index] || 110
    playTone(freq, 0.2, 'triangle', 0.3)
    // Add subtle harmonic
    playTone(freq * 2, 0.15, 'sine', 0.1)
  },

  /**
   * PAC Mode activation - The Adept's transformation
   * Ethereal choir swell
   */
  pacActivate: () => {
    if (!soundEnabled.value) return

    try {
      const ctx = initAudio()

      // Create ethereal pad sound
      const frequencies = [220, 277, 330, 440, 554] // Am7 spread

      frequencies.forEach((freq, i) => {
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()

        osc.connect(gain)
        gain.connect(ctx.destination)

        osc.frequency.value = freq
        osc.type = 'sine'

        // Slow swell envelope
        const startTime = ctx.currentTime + (i * 0.1)
        gain.gain.setValueAtTime(0, startTime)
        gain.gain.linearRampToValueAtTime(0.12, startTime + 0.5)
        gain.gain.exponentialRampToValueAtTime(0.01, startTime + 1.5)

        osc.start(startTime)
        osc.stop(startTime + 1.6)
      })

      // Add shimmering high tone
      setTimeout(() => {
        playTone(1760, 0.8, 'sine', 0.08) // A6
        playTone(2093, 0.6, 'sine', 0.05) // C7
      }, 300)

    } catch (e) {
      // Fail silently
    }
  },

  /**
   * Stone selection - Crystal ping
   * When selecting a PAC agent
   */
  stoneSelect: () => {
    // High crystalline ping
    playTone(1318, 0.15, 'sine', 0.2)  // E6
    setTimeout(() => playTone(1760, 0.2, 'sine', 0.15), 50) // A6
  },

  /**
   * Message sent - Subtle confirmation
   */
  messageSent: () => {
    playTone(880, 0.08, 'sine', 0.1)
  },

  /**
   * Error/warning tone
   */
  error: () => {
    playTone(220, 0.15, 'sawtooth', 0.15)
    setTimeout(() => playTone(196, 0.2, 'sawtooth', 0.12), 100)
  },

  /**
   * Success tone
   */
  success: () => {
    playChord([523, 659, 784], 0.3, 'sine', 0.15)
  },

  /**
   * Tap for Au logo (7-tap sequence)
   */
  auTap: (index) => {
    const freq = 660 + (index * 50) // Rising pitch
    playTone(freq, 0.08, 'sine', 0.15)
  },

  // ═══════════════ RPG Village Sounds ═══════════════

  /**
   * Footstep - soft tap when agent walks
   */
  footstep: () => {
    if (!soundEnabled.value) return
    try {
      const ctx = initAudio()
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      const filter = ctx.createBiquadFilter()

      osc.connect(filter)
      filter.connect(gain)
      gain.connect(ctx.destination)

      osc.type = 'square'
      osc.frequency.value = 80 + Math.random() * 40
      filter.type = 'lowpass'
      filter.frequency.value = 200

      gain.gain.setValueAtTime(0, ctx.currentTime)
      gain.gain.linearRampToValueAtTime(0.06, ctx.currentTime + 0.005)
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.06)

      osc.start(ctx.currentTime)
      osc.stop(ctx.currentTime + 0.07)
    } catch (e) {}
  },

  /**
   * Tool start jingle - ascending chiptune
   */
  toolStartJingle: () => {
    playArpeggio([330, 392, 523], 0.08, 'square', 0.1)
  },

  /**
   * Tool complete jingle - bright chiptune fanfare
   */
  toolCompleteJingle: () => {
    playArpeggio([523, 659, 784, 1047], 0.1, 'square', 0.12)
  },

  /**
   * Tool error jingle - descending buzz
   */
  toolErrorJingle: () => {
    playArpeggio([330, 262, 196], 0.12, 'sawtooth', 0.08)
  },
}

// ═══════════════════════════════════════════════════════════════
// COMPOSABLE EXPORT
// ═══════════════════════════════════════════════════════════════

export function useSound() {
  /**
   * Toggle sound on/off
   */
  function toggleSound() {
    soundEnabled.value = !soundEnabled.value
    localStorage.setItem('apexaurum_sounds', soundEnabled.value)

    // Play confirmation if turning on
    if (soundEnabled.value) {
      sounds.success()
    }
  }

  /**
   * Set sound enabled state
   */
  function setSound(enabled) {
    soundEnabled.value = enabled
    localStorage.setItem('apexaurum_sounds', enabled)
  }

  return {
    soundEnabled,
    toggleSound,
    setSound,
    sounds,
    playTone,
    playChord,
    initAudio,
  }
}
