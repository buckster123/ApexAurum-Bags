<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useDevMode } from '@/composables/useDevMode'

const { pacMode, ALCHEMICAL_SYMBOLS } = useDevMode()

const particles = ref([])
const intervalId = ref(null)

// Generate a random particle
function createParticle() {
  const symbol = ALCHEMICAL_SYMBOLS[Math.floor(Math.random() * ALCHEMICAL_SYMBOLS.length)]
  const id = Date.now() + Math.random()
  const left = Math.random() * 100 // percentage
  const duration = 15 + Math.random() * 20 // 15-35 seconds
  const delay = Math.random() * 5 // 0-5 seconds delay
  const size = 16 + Math.random() * 16 // 16-32px
  const opacity = 0.08 + Math.random() * 0.12 // 0.08-0.2

  return {
    id,
    symbol,
    style: {
      left: `${left}%`,
      animationDuration: `${duration}s`,
      animationDelay: `${delay}s`,
      fontSize: `${size}px`,
      opacity: opacity,
    }
  }
}

// Initialize particles
function initParticles() {
  // Start with a few particles at random positions
  const initialCount = 8
  for (let i = 0; i < initialCount; i++) {
    const p = createParticle()
    // Stagger initial positions
    p.style.animationDelay = `${i * 2}s`
    particles.value.push(p)
  }
}

// Add new particles periodically
function startParticleLoop() {
  intervalId.value = setInterval(() => {
    if (particles.value.length < 15) {
      particles.value.push(createParticle())
    }

    // Remove old particles (those that have completed animation)
    const now = Date.now()
    particles.value = particles.value.filter(p => {
      const age = now - p.id
      const duration = parseFloat(p.style.animationDuration) * 1000
      const delay = parseFloat(p.style.animationDelay) * 1000
      return age < duration + delay + 5000 // 5s buffer
    })
  }, 3000) // Add new particle every 3 seconds
}

function stopParticleLoop() {
  if (intervalId.value) {
    clearInterval(intervalId.value)
    intervalId.value = null
  }
  particles.value = []
}

// Watch PAC mode changes
watch(pacMode, (active) => {
  if (active) {
    initParticles()
    startParticleLoop()
  } else {
    stopParticleLoop()
  }
}, { immediate: true })

onMounted(() => {
  if (pacMode.value) {
    initParticles()
    startParticleLoop()
  }
})

onUnmounted(() => {
  stopParticleLoop()
})
</script>

<template>
  <Teleport to="body">
    <div v-if="pacMode" class="alchemical-particles">
      <span
        v-for="particle in particles"
        :key="particle.id"
        class="alchemical-symbol"
        :style="particle.style"
      >
        {{ particle.symbol }}
      </span>
    </div>
  </Teleport>
</template>

<style scoped>
/* Styles are in main.css, but we add some component-specific ones here */
.alchemical-particles {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: -1;
  overflow: hidden;
}

.alchemical-symbol {
  position: absolute;
  bottom: -50px;
  color: rgba(255, 215, 0, 0.12);
  text-shadow: 0 0 10px rgba(255, 215, 0, 0.3);
  animation: float-up linear forwards;
  will-change: transform;
}

@keyframes float-up {
  0% {
    transform: translateY(0) rotate(0deg) scale(1);
    opacity: 0;
  }
  5% {
    opacity: var(--particle-opacity, 0.12);
  }
  50% {
    transform: translateY(-50vh) rotate(180deg) scale(1.1);
  }
  95% {
    opacity: var(--particle-opacity, 0.12);
  }
  100% {
    transform: translateY(-110vh) rotate(360deg) scale(1);
    opacity: 0;
  }
}
</style>
