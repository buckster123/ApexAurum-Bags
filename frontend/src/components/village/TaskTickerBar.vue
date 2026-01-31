<script setup>
/**
 * TaskTickerBar - Horizontal Task Ticker
 *
 * Compact top bar showing active tool executions with progress.
 */

import { computed } from 'vue'

const props = defineProps({
  activeTasks: {
    type: Array,
    default: () => []
  },
  agentColors: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['task-click'])

// Sort by most recent
const sortedTasks = computed(() =>
  [...props.activeTasks].sort((a, b) => b.startTime - a.startTime)
)

function getElapsed(task) {
  if (!task.startTime) return '0s'
  const elapsed = Math.floor((Date.now() - task.startTime) / 1000)
  return elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed / 60)}m`
}

function getProgress(task) {
  // Estimate progress based on elapsed time (fake progress)
  if (task.status === 'complete' || task.status === 'error') return 100
  if (!task.startTime) return 0
  const elapsed = Date.now() - task.startTime
  // Asymptotic progress: approaches 90% over time
  return Math.min(90, Math.floor((1 - Math.exp(-elapsed / 5000)) * 100))
}

function handleClick(task) {
  emit('task-click', task)
}
</script>

<template>
  <div class="task-ticker-bar h-10 bg-apex-dark/80 backdrop-blur border-b border-apex-border flex items-center px-4 overflow-hidden">
    <!-- Label -->
    <div class="flex-shrink-0 text-xs text-gray-500 mr-4 hidden sm:block">
      ACTIVE:
    </div>

    <!-- Empty state -->
    <div v-if="sortedTasks.length === 0" class="text-xs text-gray-600">
      No active tasks
    </div>

    <!-- Scrolling tasks -->
    <div class="flex-1 flex items-center gap-3 overflow-x-auto hide-scrollbar">
      <div
        v-for="task in sortedTasks"
        :key="task.id"
        @click="handleClick(task)"
        class="task-chip flex items-center gap-2 bg-white/5 hover:bg-white/10 rounded px-3 py-1 cursor-pointer transition-colors flex-shrink-0"
        :class="{
          'border border-green-500/30': task.status === 'complete',
          'border border-red-500/30': task.status === 'error',
          'animate-pulse': task.status === 'running'
        }"
      >
        <!-- Agent dot -->
        <span
          class="w-2 h-2 rounded-full flex-shrink-0"
          :style="{ backgroundColor: agentColors[task.agent_id] || '#888' }"
        ></span>

        <!-- Agent name (hidden on mobile) -->
        <span class="text-xs text-gray-400 hidden md:inline">{{ task.agent_id }}</span>

        <!-- Tool name -->
        <span class="text-xs text-white font-medium">{{ task.tool }}</span>

        <!-- Progress bar -->
        <div class="w-16 h-1 bg-white/10 rounded-full overflow-hidden hidden sm:block">
          <div
            class="h-full transition-all duration-300"
            :class="{
              'bg-gold': task.status === 'running',
              'bg-green-400': task.status === 'complete',
              'bg-red-400': task.status === 'error'
            }"
            :style="{ width: getProgress(task) + '%' }"
          ></div>
        </div>

        <!-- Status indicator -->
        <span
          v-if="task.status === 'complete'"
          class="text-green-400 text-xs"
        >✓</span>
        <span
          v-else-if="task.status === 'error'"
          class="text-red-400 text-xs"
        >✗</span>
        <span
          v-else
          class="text-xs text-gray-500"
        >{{ getElapsed(task) }}</span>
      </div>
    </div>

    <!-- Count badge -->
    <div
      v-if="sortedTasks.length > 0"
      class="flex-shrink-0 ml-4 bg-gold/20 text-gold text-xs px-2 py-0.5 rounded"
    >
      {{ sortedTasks.length }}
    </div>
  </div>
</template>

<style scoped>
.hide-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
.hide-scrollbar::-webkit-scrollbar {
  display: none;
}
</style>
