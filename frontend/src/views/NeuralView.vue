<script setup>
/**
 * NeuralView - Neo-Cortex 3D Dashboard
 *
 * The main dashboard view for the Neo-Cortex memory visualization.
 * "Where memories glow like stars in the vast neural cosmos"
 */

import { ref, onMounted, watch } from 'vue'
import { useNeoCortexStore } from '@/stores/neocortex'
import { useSound } from '@/composables/useSound'
import StatsBar from '@/components/neural/StatsBar.vue'
import MemoryFilters from '@/components/neural/MemoryFilters.vue'
import MemoryDetailPanel from '@/components/neural/MemoryDetailPanel.vue'
import NeuralSpace from '@/components/neural/NeuralSpace.vue'
import MemoryList from '@/components/neural/MemoryList.vue'

const store = useNeoCortexStore()
const { playTone } = useSound()

const neuralSpaceRef = ref(null)
const showFilters = ref(true)
const showDetails = ref(true)

// Mobile responsive
const isMobile = ref(window.innerWidth < 768)

function handleResize() {
  isMobile.value = window.innerWidth < 768
  if (isMobile.value) {
    showFilters.value = false
    showDetails.value = false
  }
}

function toggleFilters() {
  showFilters.value = !showFilters.value
  if (isMobile.value && showFilters.value) {
    showDetails.value = false
  }
}

function toggleDetails() {
  showDetails.value = !showDetails.value
  if (isMobile.value && showDetails.value) {
    showFilters.value = false
  }
}

// Handle memory selection (for mobile)
function onMemorySelect(memory) {
  if (isMobile.value && memory) {
    showDetails.value = true
    showFilters.value = false
  }
}

// Initialize
onMounted(async () => {
  window.addEventListener('resize', handleResize)
  handleResize()

  // Play startup sound
  playTone(440, 0.1, 'sine', 0.1)
  setTimeout(() => playTone(554, 0.1, 'sine', 0.1), 100)
  setTimeout(() => playTone(659, 0.15, 'sine', 0.15), 200)

  // Load data
  await store.initialize()
})

// Watch for filter changes and reload data
watch(() => store.filters, async () => {
  await store.fetchGraphData()
}, { deep: true })
</script>

<template>
  <div class="neural-view h-screen flex flex-col bg-apex-dark overflow-hidden pt-16">
    <!-- Stats Bar -->
    <StatsBar />

    <!-- Main Content -->
    <div class="flex-1 flex overflow-hidden relative">
      <!-- Mobile Toggle Buttons -->
      <div class="md:hidden absolute top-2 left-2 z-20 flex gap-2">
        <button
          @click="toggleFilters"
          :class="[
            'p-2 rounded-lg transition-colors',
            showFilters ? 'bg-gold text-black' : 'bg-white/10 text-gray-400'
          ]"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
          </svg>
        </button>
      </div>

      <div class="md:hidden absolute top-2 right-2 z-20">
        <button
          @click="toggleDetails"
          :class="[
            'p-2 rounded-lg transition-colors',
            showDetails ? 'bg-gold text-black' : 'bg-white/10 text-gray-400'
          ]"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </button>
      </div>

      <!-- Left: Filters Panel -->
      <transition name="slide-left">
        <div
          v-show="showFilters"
          :class="[
            'w-64 flex-shrink-0 z-10',
            isMobile ? 'absolute inset-y-0 left-0 shadow-2xl' : ''
          ]"
        >
          <MemoryFilters />
        </div>
      </transition>

      <!-- Center: Visualization -->
      <div class="flex-1 relative">
        <!-- WebGL fallback notice -->
        <div
          v-if="!store.webglSupported"
          class="absolute top-4 left-1/2 -translate-x-1/2 z-10 bg-gold/10 border border-gold/30 text-gold px-4 py-2 rounded-lg text-sm flex items-center gap-2"
        >
          <span>🖥️</span>
          <span>3D mode unavailable (no GPU) - using list view</span>
        </div>

        <!-- 3D View - Only mount if WebGL is supported -->
        <NeuralSpace
          v-if="store.webglSupported && store.viewMode === '3d'"
          ref="neuralSpaceRef"
          :auto-rotate="store.autoRotate"
          :show-connections="store.showConnections"
          @select="onMemorySelect"
        />

        <!-- List View (fallback when no WebGL or list mode) -->
        <MemoryList v-else />

        <!-- Error display -->
        <div
          v-if="store.error"
          class="absolute bottom-4 left-1/2 -translate-x-1/2 bg-red-500/20 border border-red-500/50 text-red-300 px-4 py-2 rounded-lg text-sm"
        >
          {{ store.error }}
        </div>
      </div>

      <!-- Right: Details Panel -->
      <transition name="slide-right">
        <div
          v-show="showDetails"
          :class="[
            'w-80 flex-shrink-0 z-10',
            isMobile ? 'absolute inset-y-0 right-0 shadow-2xl' : ''
          ]"
        >
          <MemoryDetailPanel />
        </div>
      </transition>
    </div>

    <!-- Mobile backdrop -->
    <div
      v-if="isMobile && (showFilters || showDetails)"
      @click="showFilters = false; showDetails = false"
      class="absolute inset-0 bg-black/50 z-5"
    ></div>
  </div>
</template>

<style scoped>
.neural-view {
  background: radial-gradient(ellipse at center, #1a1a2e 0%, #0a0a0f 100%);
}

.slide-left-enter-active,
.slide-left-leave-active,
.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.3s ease;
}

.slide-left-enter-from,
.slide-left-leave-to {
  transform: translateX(-100%);
}

.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(100%);
}
</style>
