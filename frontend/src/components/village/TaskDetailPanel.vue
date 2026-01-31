<script setup>
/**
 * TaskDetailPanel - Detailed Task Sidebar
 *
 * Right sidebar showing detailed task information with full arguments,
 * progress, and results.
 */

import { computed } from 'vue'

const props = defineProps({
  activeTasks: {
    type: Array,
    default: () => []
  },
  completedTasks: {
    type: Array,
    default: () => []
  },
  agentColors: {
    type: Object,
    default: () => ({})
  },
  zoneConfig: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['task-click', 'clear-completed'])

// Running tasks
const runningTasks = computed(() =>
  props.activeTasks.filter(t => t.status === 'running')
)

// Recent completed (last 10)
const recentCompleted = computed(() =>
  props.completedTasks.slice(0, 10)
)

function getElapsed(task) {
  if (!task.startTime) return '0s'
  const endTime = task.endTime || Date.now()
  const elapsed = Math.floor((endTime - task.startTime) / 1000)
  if (elapsed < 60) return `${elapsed}s`
  if (elapsed < 3600) return `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`
  return `${Math.floor(elapsed / 3600)}h ${Math.floor((elapsed % 3600) / 60)}m`
}

function getProgress(task) {
  if (task.status === 'complete' || task.status === 'error') return 100
  if (!task.startTime) return 0
  const elapsed = Date.now() - task.startTime
  return Math.min(90, Math.floor((1 - Math.exp(-elapsed / 5000)) * 100))
}

function formatArgs(args) {
  if (!args) return 'No arguments'
  try {
    const str = JSON.stringify(args)
    return str.length > 100 ? str.slice(0, 100) + '...' : str
  } catch {
    return String(args).slice(0, 100)
  }
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
</script>

<template>
  <div class="task-detail-panel h-full flex flex-col bg-apex-dark border-l border-apex-border">
    <!-- Header -->
    <div class="p-4 border-b border-apex-border">
      <div class="flex items-center justify-between">
        <h3 class="font-medium text-white">Task Monitor</h3>
        <span class="text-xs bg-gold/20 text-gold px-2 py-0.5 rounded">
          {{ runningTasks.length }} active
        </span>
      </div>
    </div>

    <!-- Active Tasks -->
    <div class="flex-1 overflow-auto">
      <!-- Running section -->
      <div v-if="runningTasks.length > 0" class="p-4 space-y-3">
        <h4 class="text-xs text-gray-500 uppercase tracking-wider mb-2">Running</h4>

        <div
          v-for="task in runningTasks"
          :key="task.id"
          @click="emit('task-click', task)"
          class="task-card bg-white/5 hover:bg-white/10 rounded-lg p-3 cursor-pointer transition-colors border border-white/5"
        >
          <!-- Header: Agent + Tool -->
          <div class="flex items-center gap-2 mb-2">
            <span
              class="w-3 h-3 rounded-full animate-pulse"
              :style="{ backgroundColor: agentColors[task.agent_id] || '#888' }"
            ></span>
            <span class="text-sm font-medium text-white">{{ task.agent_id }}</span>
            <span class="text-gray-600">→</span>
            <span class="text-sm text-gold">{{ task.tool }}</span>
          </div>

          <!-- Zone badge -->
          <div class="flex items-center gap-2 mb-2">
            <span
              class="w-2 h-2 rounded"
              :style="{ backgroundColor: zoneConfig[task.zone]?.color || '#888' }"
            ></span>
            <span class="text-xs text-gray-400">{{ zoneConfig[task.zone]?.label || task.zone }}</span>
          </div>

          <!-- Progress bar -->
          <div class="mb-2">
            <div class="flex justify-between text-xs text-gray-500 mb-1">
              <span>Progress</span>
              <span>{{ getElapsed(task) }}</span>
            </div>
            <div class="h-1.5 bg-white/10 rounded-full overflow-hidden">
              <div
                class="h-full bg-gold transition-all duration-300"
                :style="{ width: getProgress(task) + '%' }"
              ></div>
            </div>
          </div>

          <!-- Arguments preview -->
          <div v-if="task.arguments" class="mt-2">
            <div class="text-xs text-gray-600 mb-1">Arguments:</div>
            <div class="text-xs text-gray-400 bg-black/30 rounded p-2 font-mono break-all">
              {{ formatArgs(task.arguments) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Empty running state -->
      <div v-else class="p-4">
        <div class="text-center py-8">
          <div class="text-3xl mb-2 opacity-50">💤</div>
          <p class="text-sm text-gray-500">No tasks running</p>
          <p class="text-xs text-gray-600 mt-1">Execute a tool to see activity</p>
        </div>
      </div>

      <!-- Completed section -->
      <div v-if="recentCompleted.length > 0" class="p-4 border-t border-apex-border">
        <div class="flex items-center justify-between mb-3">
          <h4 class="text-xs text-gray-500 uppercase tracking-wider">Completed</h4>
          <button
            @click="emit('clear-completed')"
            class="text-xs text-gray-600 hover:text-gray-400"
          >
            Clear
          </button>
        </div>

        <div class="space-y-2">
          <div
            v-for="task in recentCompleted"
            :key="task.id"
            class="flex items-center gap-2 text-xs py-1"
          >
            <span
              :class="task.status === 'complete' ? 'text-green-400' : 'text-red-400'"
            >
              {{ task.status === 'complete' ? '✓' : '✗' }}
            </span>
            <span
              class="w-2 h-2 rounded-full flex-shrink-0"
              :style="{ backgroundColor: agentColors[task.agent_id] || '#888' }"
            ></span>
            <span class="text-gray-400 truncate flex-1">{{ task.tool }}</span>
            <span class="text-gray-600">{{ task.duration_ms ? task.duration_ms + 'ms' : getElapsed(task) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Footer stats -->
    <div class="p-3 border-t border-apex-border text-xs text-gray-500 flex justify-between">
      <span>Total: {{ activeTasks.length + completedTasks.length }}</span>
      <span>{{ completedTasks.filter(t => t.status === 'complete').length }} success</span>
    </div>
  </div>
</template>
