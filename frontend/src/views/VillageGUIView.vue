<script setup>
/**
 * VillageGUIView - Village GUI Dashboard
 *
 * The main view for watching agents work in the village.
 * Supports 2D Canvas and 3D Isometric views with task tickers.
 *
 * "Where invisible computation becomes visible movement"
 */

import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useSound } from '@/composables/useSound'
import VillageCanvas from '@/components/village/VillageCanvas.vue'
import VillageIsometric from '@/components/village/VillageIsometric.vue'
import TaskTickerBar from '@/components/village/TaskTickerBar.vue'
import TaskDetailPanel from '@/components/village/TaskDetailPanel.vue'
import { ZONES, AGENT_COLORS } from '@/composables/useVillage'
import { ZONES_3D, AGENT_COLORS as AGENT_COLORS_3D } from '@/composables/useVillageIsometric'

const router = useRouter()
const { playTone, sounds } = useSound()

// Navigate to chat with selected agent
function handleAgentClick(agentId) {
  playTone(660, 0.05, 'sine', 0.1)
  router.push({ path: '/chat', query: { agent: agentId } })
}

// View mode
const viewMode = ref(localStorage.getItem('village-view-mode') || '2d')
const showTaskPanel = ref(true)

// Child component refs for layout reset
const canvasRef = ref(null)
const isometricRef = ref(null)

// Layout reset support
const layoutResetKey = ref(0)
const canResetLayout = computed(() => {
  // Re-evaluate when layoutResetKey changes (after reset)
  layoutResetKey.value
  const key = viewMode.value === '3d' ? 'village-layout-3d' : 'village-layout-2d'
  return !!localStorage.getItem(key)
})

function handleResetLayout() {
  if (viewMode.value === '2d' && canvasRef.value) {
    canvasRef.value.resetLayout()
  } else if (viewMode.value === '3d' && isometricRef.value) {
    isometricRef.value.resetLayout()
  }
  layoutResetKey.value++
}

// WebSocket connection
const ws = ref(null)
const status = reactive({
  connection: 'disconnected',
  eventCount: 0,
  lastTool: null
})

// Event log
const eventLog = ref([])

// Task tracking
const activeTasks = ref([])
const completedTasks = ref([])

// Zone configs based on view mode
const zoneConfig = computed(() => viewMode.value === '3d' ? ZONES_3D : ZONES)
const agentColors = computed(() => viewMode.value === '3d' ? AGENT_COLORS_3D : AGENT_COLORS)

// Save view mode preference
watch(viewMode, (mode) => {
  localStorage.setItem('village-view-mode', mode)
  playTone(mode === '3d' ? 660 : 440, 0.05, 'sine', 0.1)
})

// WebSocket connection with backoff
let wsRetryDelay = 3000
let wsAuthFailed = false
let wsFailCount = 0
const WS_MAX_RETRIES = 5

function isTokenExpired(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.exp && payload.exp < Date.now() / 1000
  } catch { return false }
}

function connectWebSocket() {
  // Don't connect without auth token - backend requires it (closes with 1008)
  const token = localStorage.getItem('accessToken')
  if (!token || token === 'undefined' || token === 'null') {
    status.connection = 'no-auth'
    return
  }

  // Don't retry if auth was explicitly rejected
  if (wsAuthFailed) return

  // Stop retrying with expired token - user needs to re-login
  if (isTokenExpired(token)) {
    console.log('Village: WebSocket token expired, not retrying')
    wsAuthFailed = true
    status.connection = 'no-auth'
    return
  }

  // Stop after too many consecutive failures
  if (wsFailCount >= WS_MAX_RETRIES) {
    console.log(`Village: WebSocket gave up after ${WS_MAX_RETRIES} failures`)
    wsAuthFailed = true
    status.connection = 'failed'
    return
  }

  let apiUrl = import.meta.env.VITE_API_URL || ''
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'

  // Ensure apiUrl has protocol prefix (same fix as api.js)
  if (apiUrl && !apiUrl.startsWith('http://') && !apiUrl.startsWith('https://')) {
    apiUrl = 'https://' + apiUrl
  }

  let wsUrl
  if (apiUrl) {
    wsUrl = apiUrl.replace(/^https?:/, wsProtocol) + '/ws/village'
  } else {
    wsUrl = `${wsProtocol}//${window.location.host}/ws/village`
  }

  wsUrl += `?token=${token}`

  console.log(`Village: Connecting to ${wsUrl.split('?')[0]}`)
  ws.value = new WebSocket(wsUrl)

  ws.value.onopen = () => {
    console.log('Village: WebSocket connected')
    status.connection = 'connected'
    wsRetryDelay = 3000 // Reset backoff on success
    wsFailCount = 0
    playTone(880, 0.05, 'sine', 0.1)
  }

  ws.value.onclose = (event) => {
    status.connection = 'disconnected'

    // 1008 = Policy Violation (backend sends this for auth failure)
    if (event.code === 1008) {
      console.log('Village: WebSocket auth rejected, not retrying')
      wsAuthFailed = true
      status.connection = 'no-auth'
      return
    }

    wsFailCount++
    console.log(`Village: WebSocket disconnected (code ${event.code}), attempt ${wsFailCount}/${WS_MAX_RETRIES}, retrying in ${wsRetryDelay / 1000}s`)
    setTimeout(connectWebSocket, wsRetryDelay)
    wsRetryDelay = Math.min(wsRetryDelay * 1.5, 30000) // Backoff, cap at 30s
  }

  ws.value.onerror = () => {
    // onclose fires after onerror, so just update status here
    status.connection = 'error'
  }

  ws.value.onmessage = (event) => {
    handleEvent(JSON.parse(event.data))
  }
}

function handleEvent(event) {
  status.eventCount++

  // Add to event log
  eventLog.value.unshift({
    ...event,
    id: `${event.tool}-${Date.now()}`,
    receivedAt: Date.now()
  })
  if (eventLog.value.length > 50) {
    eventLog.value.pop()
  }

  // Handle task tracking
  if (event.type === 'tool_start') {
    const taskId = `${event.agent_id}-${event.tool}-${Date.now()}`
    activeTasks.value.push({
      id: taskId,
      ...event,
      startTime: Date.now(),
      status: 'running'
    })
    status.lastTool = event.tool
    sounds.toolStartJingle()
  }
  else if (event.type === 'tool_complete' || event.type === 'tool_error') {
    // Find and update task
    const idx = activeTasks.value.findIndex(
      t => t.agent_id === event.agent_id && t.tool === event.tool && t.status === 'running'
    )
    if (idx !== -1) {
      const task = activeTasks.value[idx]
      task.status = event.type === 'tool_complete' && event.success ? 'complete' : 'error'
      task.endTime = Date.now()
      task.duration_ms = event.duration_ms || (task.endTime - task.startTime)
      task.result_preview = event.result_preview

      // Move to completed
      completedTasks.value.unshift(task)
      if (completedTasks.value.length > 50) {
        completedTasks.value.pop()
      }

      // Remove from active after animation delay
      setTimeout(() => {
        const removeIdx = activeTasks.value.findIndex(t => t.id === task.id)
        if (removeIdx !== -1) {
          activeTasks.value.splice(removeIdx, 1)
        }
      }, 1500)

      if (event.success) {
        sounds.toolCompleteJingle()
      } else {
        sounds.toolErrorJingle()
      }
    }
  }
}

function clearCompleted() {
  completedTasks.value = []
}

function handleTaskClick(task) {
  playTone(550, 0.03, 'sine', 0.05)
  // Could focus on agent in view
}

function handleWebGLError(error) {
  console.warn('WebGL not available, falling back to 2D mode')
  viewMode.value = '2d'
  localStorage.setItem('village-view-mode', '2d')
}

onMounted(() => {
  connectWebSocket()
})

onUnmounted(() => {
  if (ws.value) {
    ws.value.close()
  }
})
</script>

<template>
  <div class="village-gui-view h-screen flex flex-col bg-apex-dark overflow-hidden pt-16">
    <!-- Header with View Toggle -->
    <div class="h-12 bg-apex-dark/80 backdrop-blur border-b border-apex-border flex items-center justify-between px-4">
      <div class="flex items-center gap-3">
        <span class="text-lg">🏘️</span>
        <span class="font-medium text-white">Village GUI</span>
        <span class="text-xs text-gray-500 hidden sm:inline">Agent Activity Visualization</span>
      </div>

      <div class="flex items-center gap-4">
        <!-- View Toggle -->
        <div class="flex bg-white/5 rounded-lg p-0.5">
          <button
            @click="viewMode = '2d'"
            class="px-3 py-1 text-xs rounded transition-colors"
            :class="viewMode === '2d' ? 'bg-gold text-black' : 'text-gray-400 hover:text-white'"
          >
            2D
          </button>
          <button
            @click="viewMode = '3d'"
            class="px-3 py-1 text-xs rounded transition-colors"
            :class="viewMode === '3d' ? 'bg-gold text-black' : 'text-gray-400 hover:text-white'"
          >
            3D
          </button>
        </div>

        <!-- Reset Layout -->
        <button
          v-if="canResetLayout"
          @click="handleResetLayout"
          class="text-xs text-gray-400 hover:text-gold transition-colors"
        >
          Reset Layout
        </button>

        <!-- Task Panel Toggle -->
        <button
          @click="showTaskPanel = !showTaskPanel"
          class="text-xs text-gray-400 hover:text-white transition-colors hidden md:block"
        >
          {{ showTaskPanel ? 'Hide' : 'Show' }} Tasks
        </button>
      </div>
    </div>

    <!-- Task Ticker Bar -->
    <TaskTickerBar
      :active-tasks="activeTasks"
      :agent-colors="agentColors"
      @task-click="handleTaskClick"
    />

    <!-- Main Content -->
    <div class="flex-1 flex overflow-hidden">
      <!-- Village View -->
      <div class="flex-1 relative">
        <!-- 2D Canvas View -->
        <div v-if="viewMode === '2d'" class="w-full h-full flex items-center justify-center">
          <VillageCanvas
            ref="canvasRef"
            :events="eventLog"
            :status="status"
            @agentClick="handleAgentClick"
          />
        </div>

        <!-- 3D Isometric View -->
        <div v-if="viewMode === '3d'" class="w-full h-full">
          <VillageIsometric
            ref="isometricRef"
            :events="eventLog"
            :status="status"
            @agent-click="handleAgentClick"
            @webgl-error="handleWebGLError"
          />
        </div>
      </div>

      <!-- Right Sidebar: Task Detail Panel -->
      <transition name="slide-right">
        <div v-if="showTaskPanel" class="w-80 flex-shrink-0 hidden md:block">
          <TaskDetailPanel
            :active-tasks="activeTasks"
            :completed-tasks="completedTasks"
            :agent-colors="agentColors"
            :zone-config="zoneConfig"
            @task-click="handleTaskClick"
            @clear-completed="clearCompleted"
          />
        </div>
      </transition>
    </div>

    <!-- Mobile Task Panel Toggle -->
    <button
      @click="showTaskPanel = !showTaskPanel"
      class="md:hidden fixed bottom-4 right-4 w-12 h-12 bg-gold text-black rounded-full shadow-lg flex items-center justify-center z-20"
    >
      <span class="text-lg">{{ showTaskPanel ? '×' : '📋' }}</span>
    </button>

    <!-- Mobile Task Panel Overlay -->
    <transition name="slide-up">
      <div
        v-if="showTaskPanel"
        class="md:hidden fixed inset-x-0 bottom-0 h-2/3 bg-apex-dark border-t border-apex-border z-10"
      >
        <TaskDetailPanel
          :active-tasks="activeTasks"
          :completed-tasks="completedTasks"
          :agent-colors="agentColors"
          :zone-config="zoneConfig"
          @task-click="handleTaskClick"
          @clear-completed="clearCompleted"
        />
      </div>
    </transition>
  </div>
</template>

<style scoped>
.village-gui-view {
  background: radial-gradient(ellipse at center, #1a1a2e 0%, #0f0f1a 100%);
}

.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.3s ease;
}

.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(100%);
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: transform 0.3s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
}
</style>
