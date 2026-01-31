<script setup>
/**
 * AgentCard - Individual agent response display
 *
 * Shows an agent's contribution to a deliberation round.
 */

import { computed } from 'vue'

const props = defineProps({
  agentId: {
    type: String,
    required: true,
  },
  content: {
    type: String,
    default: '',
  },
  inputTokens: {
    type: Number,
    default: 0,
  },
  outputTokens: {
    type: Number,
    default: 0,
  },
  color: {
    type: String,
    default: '#888888',
  },
  isStreaming: {
    type: Boolean,
    default: false,
  },
  tools: {
    type: Array,
    default: () => [],
  },
})

const totalTokens = computed(() => props.inputTokens + props.outputTokens)

// Simple markdown-like formatting for paragraphs
const formattedContent = computed(() => {
  if (!props.content) return ''
  return props.content
    .split('\n\n')
    .map(p => `<p class="mb-3 last:mb-0">${p.replace(/\n/g, '<br>')}</p>`)
    .join('')
})
</script>

<template>
  <div
    class="card p-4 flex flex-col"
    :style="{ borderTopColor: color, borderTopWidth: '3px' }"
  >
    <!-- Header -->
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <div
          class="w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm"
          :style="{ backgroundColor: color + '30', color: color }"
        >
          {{ agentId[0] }}
        </div>
        <span class="font-medium" :style="{ color: color }">{{ agentId }}</span>
      </div>
      <div class="flex items-center gap-2 text-xs text-gray-500">
        <span v-if="isStreaming" class="flex items-center gap-1">
          <span class="w-2 h-2 bg-gold rounded-full animate-pulse"></span>
          typing...
        </span>
        <span v-else>{{ totalTokens }} tok</span>
      </div>
    </div>

    <!-- Content -->
    <div
      class="flex-1 text-sm text-gray-300 leading-relaxed prose prose-invert prose-sm max-w-none"
      v-html="formattedContent"
    ></div>

    <!-- Tools Used -->
    <div v-if="tools?.length" class="mt-3 pt-3 border-t border-apex-border/50">
      <div class="flex items-center gap-1 mb-2 text-xs text-gray-500">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clip-rule="evenodd" />
        </svg>
        <span>Tools used: {{ tools.length }}</span>
      </div>
      <div class="space-y-1">
        <div
          v-for="(tool, idx) in tools"
          :key="idx"
          class="text-xs bg-apex-dark/50 rounded px-2 py-1.5"
        >
          <div class="flex items-center gap-1">
            <span class="text-cyan-400 font-mono">{{ tool.name }}</span>
            <span v-if="tool.result" class="text-gray-500">→</span>
            <span v-if="tool.result" class="text-gray-400 truncate flex-1" :title="tool.result">
              {{ tool.result.length > 60 ? tool.result.slice(0, 60) + '...' : tool.result }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <div class="flex items-center justify-between mt-3 pt-3 border-t border-apex-border text-xs text-gray-500">
      <span>In: {{ inputTokens }}</span>
      <span>Out: {{ outputTokens }}</span>
    </div>
  </div>
</template>

<style scoped>
.card {
  @apply bg-apex-card border border-apex-border rounded-xl;
}

.card :deep(p) {
  @apply text-gray-300;
}

.card :deep(strong) {
  @apply text-white font-semibold;
}
</style>
