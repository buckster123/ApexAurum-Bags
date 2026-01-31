import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useSound } from './useSound'
import { useHaptic } from './useHaptic'

// Singleton state - shared across all components
const devMode = ref(localStorage.getItem('devMode') === 'true')
const pacMode = ref(localStorage.getItem('pacMode') === 'true')

// Tier restriction message shown when non-Adept tries to activate
const tierRestrictionMessage = ref('')

// Sound system
const { sounds } = useSound()

// Haptic feedback
const { haptics } = useHaptic()

// Konami code sequence: ↑↑↓↓←→←→BA
const KONAMI_CODE = [
  'ArrowUp', 'ArrowUp',
  'ArrowDown', 'ArrowDown',
  'ArrowLeft', 'ArrowRight',
  'ArrowLeft', 'ArrowRight',
  'KeyB', 'KeyA'
]

// The sacred incantation: A-Z-O-T-H
const AZOTH_SEQUENCE = ['KeyA', 'KeyZ', 'KeyO', 'KeyT', 'KeyH']

// Alchemical symbols for the experience
const ALCHEMICAL_SYMBOLS = ['∴', '☿', '☉', '☽', '♀', '♂', '∞', '⚗', '🜏', '🝔']

export function useDevMode() {
  const konamiIndex = ref(0)
  const azothIndex = ref(0)
  const tapCount = ref(0)
  const tapTimeout = ref(null)
  const azothTimeout = ref(null)

  // Activation feedback state
  const justActivatedPac = ref(false)

  // Computed: current layer
  const alchemyLayer = computed(() => {
    if (pacMode.value) return 2  // The Adept
    if (devMode.value) return 1  // The Apprentice
    return 0                      // Mundane
  })

  const layerName = computed(() => {
    switch (alchemyLayer.value) {
      case 2: return 'The Adept'
      case 1: return 'The Apprentice'
      default: return 'Mundane'
    }
  })

  // === DEV MODE (Layer 1) ===

  function enableDevMode(skipTierCheck = false) {
    // Check tier restriction (Adept only) unless explicitly skipped
    if (!skipTierCheck) {
      // Dynamically import billing store to check tier
      import('@/stores/billing').then(({ useBillingStore }) => {
        const billing = useBillingStore()
        if (!billing.isOpus) {
          // Show restriction message
          tierRestrictionMessage.value = 'Dev Mode requires Adept tier. Upgrade to unlock!'
          console.log('%c🔒 Dev Mode requires Adept tier', 'color: #FFD700; font-size: 14px;')
          console.log('%cUpgrade to Adept to unlock developer features.', 'color: #888; font-style: italic;')

          // Clear message after 5 seconds
          setTimeout(() => {
            tierRestrictionMessage.value = ''
          }, 5000)
          return
        }
        // Tier check passed, actually enable
        doEnableDevMode()
      }).catch(() => {
        // If store fails to load, allow activation (fail open for testing)
        doEnableDevMode()
      })
      return
    }
    doEnableDevMode()
  }

  function doEnableDevMode() {
    devMode.value = true
    localStorage.setItem('devMode', 'true')

    // Play activation sound + haptic
    sounds.devModeActivate()
    haptics.devMode()

    console.log('%c🔧 Dev Mode activated!', 'color: #FFD700; font-size: 14px;')
    console.log('%cYou are now: The Apprentice', 'color: #888; font-style: italic;')
    console.log('%c💡 Hint: The Stone has a name...', 'color: #666; font-size: 11px;')
  }

  function disableDevMode() {
    devMode.value = false
    pacMode.value = false
    localStorage.removeItem('devMode')
    localStorage.removeItem('pacMode')
    console.log('Dev Mode deactivated')
  }

  function toggleDevMode() {
    if (devMode.value) {
      disableDevMode()
    } else {
      enableDevMode()
    }
  }

  // === PAC MODE (Layer 2) ===

  function enablePacMode() {
    if (!devMode.value) return // Must be in dev mode first

    pacMode.value = true
    localStorage.setItem('pacMode', 'true')
    justActivatedPac.value = true

    // Play ethereal activation sound + mystical haptic
    sounds.pacActivate()
    haptics.pac()

    // Epic console activation
    console.clear()
    console.log('%c' + '∴'.repeat(50), 'color: #FFD700; font-size: 8px;')
    console.log('%c', 'padding: 20px;')
    console.log('%c  ∴ A Z O T H ∴  ', 'background: linear-gradient(90deg, #1a0a2e, #16213e); color: #FFD700; font-size: 24px; font-weight: bold; padding: 20px 40px; border: 2px solid #FFD700; text-shadow: 0 0 10px #FFD700;')
    console.log('%c', 'padding: 10px;')
    console.log('%cThe Stone awakens...', 'color: #E8B4FF; font-size: 16px; font-style: italic;')
    console.log('%cYou have become: The Adept', 'color: #FFD700; font-size: 14px;')
    console.log('%c', 'padding: 10px;')
    console.log('%cThe Perfected Stones await in Settings → Agents', 'color: #888; font-size: 12px;')
    console.log('%c' + '∴'.repeat(50), 'color: #FFD700; font-size: 8px;')

    // Reset after animation
    setTimeout(() => {
      justActivatedPac.value = false
    }, 3000)
  }

  function disablePacMode() {
    pacMode.value = false
    localStorage.removeItem('pacMode')
    console.log('%cPAC Mode sealed', 'color: #666;')
  }

  // === KEYBOARD DETECTION ===

  function handleKeyDown(event) {
    // Guard against undefined event.code (mobile/IME events)
    if (!event.code) return
    // Konami code for Dev Mode
    if (!devMode.value) {
      const expectedKonami = KONAMI_CODE[konamiIndex.value]
      if (event.code === expectedKonami) {
        // Play ascending chime + haptic for each correct key
        sounds.konamiKey(konamiIndex.value)
        haptics.konamiKey()
        konamiIndex.value++
        if (konamiIndex.value === KONAMI_CODE.length) {
          enableDevMode()
          konamiIndex.value = 0
        }
      } else {
        konamiIndex.value = 0
      }
    }

    // AZOTH incantation for PAC Mode (only works in Dev Mode)
    if (devMode.value && !pacMode.value) {
      const expectedAzoth = AZOTH_SEQUENCE[azothIndex.value]

      if (event.code === expectedAzoth) {
        // Play deep resonance + haptic for each letter
        sounds.azothLetter(azothIndex.value)
        haptics.azothLetter()
        azothIndex.value++

        // Visual feedback - whisper the letters
        const letter = AZOTH_SEQUENCE[azothIndex.value - 1].replace('Key', '')
        console.log(`%c${letter}...`, 'color: #FFD700; font-size: 12px; opacity: 0.7;')

        // Clear timeout on progress
        if (azothTimeout.value) {
          clearTimeout(azothTimeout.value)
        }

        if (azothIndex.value === AZOTH_SEQUENCE.length) {
          // Incantation complete!
          enablePacMode()
          azothIndex.value = 0
        } else {
          // Reset after 3 seconds of no progress
          azothTimeout.value = setTimeout(() => {
            if (azothIndex.value > 0) {
              console.log('%c...the whisper fades', 'color: #444; font-size: 10px; font-style: italic;')
            }
            azothIndex.value = 0
          }, 3000)
        }
      } else if (event.code.startsWith('Key')) {
        // Wrong letter resets
        if (azothIndex.value > 0) {
          console.log('%c...the pattern breaks', 'color: #442; font-size: 10px; font-style: italic;')
        }
        azothIndex.value = 0
      }
    }
  }

  // === 7-TAP DETECTION ===

  function handleTap() {
    // Play rising tap sound
    sounds.auTap(tapCount.value)
    tapCount.value++

    if (tapTimeout.value) {
      clearTimeout(tapTimeout.value)
    }

    if (tapCount.value >= 7) {
      enableDevMode()
      tapCount.value = 0
      return
    }

    tapTimeout.value = setTimeout(() => {
      tapCount.value = 0
    }, 2000)
  }

  // === LIFECYCLE ===

  function setupListeners() {
    window.addEventListener('keydown', handleKeyDown)
  }

  function cleanupListeners() {
    window.removeEventListener('keydown', handleKeyDown)
    if (tapTimeout.value) clearTimeout(tapTimeout.value)
    if (azothTimeout.value) clearTimeout(azothTimeout.value)
  }

  onMounted(() => {
    setupListeners()

    // Whisper hint to console if in dev mode but not PAC
    if (devMode.value && !pacMode.value) {
      setTimeout(() => {
        console.log('%c💡 The Stone has a name... speak it.', 'color: #555; font-size: 11px; font-style: italic;')
      }, 2000)
    }
  })

  onUnmounted(() => {
    cleanupListeners()
  })

  return {
    // State
    devMode,
    pacMode,
    alchemyLayer,
    layerName,
    justActivatedPac,
    tapCount,
    tierRestrictionMessage,

    // Actions
    enableDevMode,
    disableDevMode,
    toggleDevMode,
    enablePacMode,
    disablePacMode,
    handleTap,

    // Utilities
    ALCHEMICAL_SYMBOLS,
    setupListeners,
    cleanupListeners
  }
}
