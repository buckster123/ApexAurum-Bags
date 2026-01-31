<script setup>
/**
 * VillageIsometric - Isometric 2.5D Village View
 *
 * Three.js isometric visualization of the village with zone buildings
 * and animated agent spheres. Now with particle effects and click handling!
 */

import { ref, computed, onMounted, watch } from 'vue'
import { useVillageIsometric, ZONES_3D, AGENT_COLORS } from '@/composables/useVillageIsometric'

const props = defineProps({
  events: {
    type: Array,
    default: () => []
  },
  status: {
    type: Object,
    default: () => ({ connection: 'disconnected', eventCount: 0 })
  }
})

const emit = defineEmits(['zone-click', 'agent-click', 'webgl-error'])

const containerRef = ref(null)
const showAgentPopup = ref(false)
const popupPosition = ref({ x: 0, y: 0 })

// Callback options for click handling
const villageOptions = {
  onAgentClick: (agentId, agent) => {
    emit('agent-click', agentId)
    showAgentPopup.value = true
    // Position popup near center-right of canvas
    if (containerRef.value) {
      const rect = containerRef.value.getBoundingClientRect()
      popupPosition.value = {
        x: rect.width / 2 + 50,
        y: rect.height / 2 - 100
      }
    }
  },
  onZoneClick: (zoneName, label) => {
    emit('zone-click', { name: zoneName, label })
  },
  onWebGLError: (error) => {
    emit('webgl-error', error)
  }
}

const {
  isInitialized,
  activeZone,
  selectedAgent,
  hoveredObject,
  webglError,
  agents,
  ensureAgent,
  handleToolStart,
  handleToolComplete,
  handleToolError,
  showBubble,
  dismissBubble,
  hasCustomLayout,
  resetLayout
} = useVillageIsometric(containerRef, villageOptions)

defineExpose({ hasCustomLayout, resetLayout })

// Get selected agent details
const selectedAgentData = computed(() => {
  if (!selectedAgent.value) return null
  const agent = agents.get(selectedAgent.value)
  if (!agent) return null
  return {
    id: agent.id,
    color: agent.color,
    state: agent.state,
    zone: agent.currentZone,
    tool: agent.currentTool
  }
})

function closeAgentPopup() {
  showAgentPopup.value = false
  selectedAgent.value = null
}

// Watch for new events
watch(() => props.events, (newEvents) => {
  if (newEvents.length === 0) return

  const latest = newEvents[0]
  if (!latest) return

  if (latest.type === 'tool_start') {
    handleToolStart(latest)
  } else if (latest.type === 'tool_complete') {
    handleToolComplete(latest)
  } else if (latest.type === 'tool_error') {
    handleToolError(latest)
  } else if (latest.type === 'approval_needed') {
    // Show approval bubble for this agent
    showBubble(latest.agent_id, latest.message || 'Approval needed', 'approval')
  } else if (latest.type === 'input_needed') {
    // Show input bubble for this agent
    showBubble(latest.agent_id, latest.message || 'Input required', 'input')
  }
}, { deep: true })

// Create default agent on mount
onMounted(() => {
  setTimeout(() => {
    if (isInitialized.value) {
      ensureAgent('CLAUDE')
    }
  }, 100)
})
</script>

<template>
  <div class="village-isometric-wrapper relative w-full h-full">
    <!-- Three.js Container -->
    <div
      ref="containerRef"
      class="village-isometric-canvas w-full h-full"
    ></div>

    <!-- WebGL Error overlay -->
    <div
      v-if="webglError"
      class="absolute inset-0 flex items-center justify-center bg-apex-dark"
    >
      <div class="text-center max-w-md px-6">
        <div class="text-4xl mb-4">⚠️</div>
        <p class="text-red-400 font-medium mb-2">3D Not Available</p>
        <p class="text-gray-400 text-sm mb-4">{{ webglError }}</p>
        <p class="text-gray-500 text-xs">Your device doesn't support WebGL. The 2D Canvas view works great!</p>
      </div>
    </div>

    <!-- Loading overlay -->
    <div
      v-else-if="!isInitialized"
      class="absolute inset-0 flex items-center justify-center bg-apex-dark"
    >
      <div class="text-center">
        <div class="text-4xl mb-4 animate-pulse">🏘️</div>
        <p class="text-gray-400">Loading Isometric Village...</p>
      </div>
    </div>

    <!-- Connection status -->
    <div class="absolute top-3 left-3 flex items-center gap-2 bg-black/50 backdrop-blur rounded px-3 py-1.5">
      <span
        class="w-2 h-2 rounded-full"
        :class="{
          'bg-green-400': status.connection === 'connected',
          'bg-yellow-400': status.connection === 'no-auth',
          'bg-red-400': status.connection !== 'connected' && status.connection !== 'no-auth'
        }"
      ></span>
      <span class="text-xs text-gray-300">{{ status.connection === 'no-auth' ? 'offline' : status.connection }}</span>
      <span class="text-xs text-gray-500">|</span>
      <span class="text-xs text-gray-400">{{ status.eventCount }} events</span>
    </div>

    <!-- Active zone indicator -->
    <div
      v-if="activeZone"
      class="absolute top-3 right-3 bg-black/50 backdrop-blur rounded px-3 py-1.5"
    >
      <div class="flex items-center gap-2">
        <span
          class="w-3 h-3 rounded"
          :style="{ backgroundColor: ZONES_3D[activeZone]?.color || '#888' }"
        ></span>
        <span class="text-sm text-white">{{ ZONES_3D[activeZone]?.label || activeZone }}</span>
      </div>
    </div>

    <!-- Mini event log -->
    <div class="absolute bottom-3 left-3 w-64 max-h-32 overflow-hidden bg-black/50 backdrop-blur rounded">
      <div class="p-2 border-b border-white/10">
        <span class="text-xs text-gray-400">Recent Activity</span>
      </div>
      <div class="p-2 space-y-1 max-h-24 overflow-auto">
        <div
          v-for="(event, index) in events.slice(0, 5)"
          :key="index"
          class="flex items-center gap-2 text-xs"
        >
          <span
            class="w-2 h-2 rounded-full flex-shrink-0"
            :style="{ backgroundColor: AGENT_COLORS[event.agent_id] || '#888' }"
          ></span>
          <span class="text-gray-400 truncate">{{ event.agent_id }}</span>
          <span class="text-gray-600">→</span>
          <span class="text-white truncate">{{ event.tool }}</span>
          <span
            v-if="event.type === 'tool_complete'"
            :class="event.success ? 'text-green-400' : 'text-red-400'"
          >
            {{ event.success ? '✓' : '✗' }}
          </span>
        </div>
        <div v-if="events.length === 0" class="text-gray-600 text-center py-2">
          No activity yet
        </div>
      </div>
    </div>

    <!-- Hover tooltip -->
    <div
      v-if="hoveredObject && !showAgentPopup"
      class="absolute bottom-3 right-3 bg-black/70 backdrop-blur rounded px-3 py-2"
    >
      <div class="flex items-center gap-2 text-sm">
        <span
          v-if="hoveredObject.type === 'agent'"
          class="w-3 h-3 rounded-full"
          :style="{ backgroundColor: AGENT_COLORS[hoveredObject.id] || '#888' }"
        ></span>
        <span
          v-else-if="hoveredObject.type === 'zone'"
          class="w-3 h-3 rounded"
          :style="{ backgroundColor: ZONES_3D[hoveredObject.name]?.color || '#888' }"
        ></span>
        <span class="text-white">
          {{ hoveredObject.type === 'agent' ? hoveredObject.id : hoveredObject.label }}
        </span>
        <span class="text-gray-500 text-xs">Click for details</span>
      </div>
    </div>

    <!-- Agent Detail Popup -->
    <transition name="popup">
      <div
        v-if="showAgentPopup && selectedAgentData"
        class="agent-popup absolute bg-apex-dark/95 backdrop-blur-lg border border-apex-border rounded-lg shadow-2xl p-4 w-72"
        :style="{ left: popupPosition.x + 'px', top: popupPosition.y + 'px' }"
      >
        <!-- Header -->
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-3">
            <div
              class="w-10 h-10 rounded-full flex items-center justify-center text-black font-bold"
              :style="{ backgroundColor: selectedAgentData.color }"
            >
              {{ selectedAgentData.id.charAt(0) }}
            </div>
            <div>
              <h3 class="font-medium text-white">{{ selectedAgentData.id }}</h3>
              <span
                class="text-xs px-2 py-0.5 rounded"
                :class="{
                  'bg-green-500/20 text-green-400': selectedAgentData.state === 'working',
                  'bg-blue-500/20 text-blue-400': selectedAgentData.state === 'moving',
                  'bg-gray-500/20 text-gray-400': selectedAgentData.state === 'idle'
                }"
              >
                {{ selectedAgentData.state }}
              </span>
            </div>
          </div>
          <button
            @click="closeAgentPopup"
            class="text-gray-500 hover:text-white transition-colors"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- Location -->
        <div class="space-y-2 text-sm">
          <div class="flex items-center justify-between">
            <span class="text-gray-500">Location</span>
            <div class="flex items-center gap-2">
              <span
                class="w-2 h-2 rounded"
                :style="{ backgroundColor: ZONES_3D[selectedAgentData.zone]?.color || '#888' }"
              ></span>
              <span class="text-white">{{ ZONES_3D[selectedAgentData.zone]?.label || selectedAgentData.zone }}</span>
            </div>
          </div>

          <!-- Current Tool -->
          <div v-if="selectedAgentData.tool" class="flex items-center justify-between">
            <span class="text-gray-500">Running</span>
            <span class="text-gold">{{ selectedAgentData.tool }}</span>
          </div>

          <!-- No Activity -->
          <div v-else class="text-center py-3 text-gray-500">
            <span class="text-2xl block mb-1">💤</span>
            <span class="text-xs">Agent is idle</span>
          </div>
        </div>

        <!-- Actions -->
        <div class="mt-4 pt-3 border-t border-apex-border flex gap-2">
          <button
            class="flex-1 text-xs px-3 py-2 bg-white/5 hover:bg-white/10 rounded transition-colors text-gray-300"
            @click="closeAgentPopup"
          >
            Close
          </button>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.village-isometric-wrapper {
  background: radial-gradient(ellipse at center, #1a1a2e 0%, #0a0a0f 100%);
}

.agent-popup {
  z-index: 50;
  max-height: calc(100% - 100px);
  overflow-y: auto;
}

.popup-enter-active,
.popup-leave-active {
  transition: all 0.2s ease;
}

.popup-enter-from,
.popup-leave-to {
  opacity: 0;
  transform: scale(0.95) translateY(-10px);
}
</style>
