<script setup>
/**
 * MemoryList - List view fallback for Neural Space
 *
 * A table-based list view of memories (2D/List mode).
 */

import { computed } from 'vue'
import { useNeoCortexStore, AGENT_COLORS } from '@/stores/neocortex'

const store = useNeoCortexStore()

const memories = computed(() => store.filteredNodes)

function selectMemory(memory) {
  store.selectMemory(memory)
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function truncate(text, length = 100) {
  if (!text) return ''
  return text.length > length ? text.slice(0, length) + '...' : text
}
</script>

<template>
  <div class="memory-list h-full overflow-auto bg-apex-dark">
    <!-- Empty state -->
    <div
      v-if="memories.length === 0"
      class="h-full flex items-center justify-center"
    >
      <div class="text-center text-gray-500">
        <div class="text-4xl mb-4 opacity-50">🧠</div>
        <p>No memories match your filters</p>
      </div>
    </div>

    <!-- Table -->
    <table v-else class="w-full text-sm">
      <thead class="sticky top-0 bg-apex-dark border-b border-apex-border">
        <tr class="text-left text-xs text-gray-500 uppercase tracking-wider">
          <th class="p-3 w-24">Agent</th>
          <th class="p-3 w-24">Layer</th>
          <th class="p-3">Content</th>
          <th class="p-3 w-20 text-right">Attention</th>
          <th class="p-3 w-36">Created</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="memory in memories"
          :key="memory.id"
          @click="selectMemory(memory)"
          :class="[
            'border-b border-apex-border/50 cursor-pointer transition-colors',
            store.selectedMemory?.id === memory.id
              ? 'bg-gold/10'
              : 'hover:bg-white/5'
          ]"
        >
          <td class="p-3">
            <div class="flex items-center gap-2">
              <span
                class="w-2 h-2 rounded-full"
                :style="{ backgroundColor: AGENT_COLORS[memory.agent_id]?.hex || '#888' }"
              ></span>
              <span class="text-xs text-gray-400">{{ memory.agent_id || 'CLAUDE' }}</span>
            </div>
          </td>
          <td class="p-3">
            <span
              class="px-2 py-0.5 text-xs rounded"
              :class="{
                'bg-white/20 text-white': memory.layer === 'cortex',
                'bg-white/15 text-gray-300': memory.layer === 'long_term',
                'bg-white/10 text-gray-400': memory.layer === 'working',
                'bg-white/5 text-gray-500': memory.layer === 'sensory',
              }"
            >
              {{ memory.layer }}
            </span>
          </td>
          <td class="p-3">
            <p class="text-gray-300 line-clamp-2">{{ truncate(memory.content, 150) }}</p>
          </td>
          <td class="p-3 text-right">
            <span class="text-gold font-mono text-xs">
              {{ memory.attention_weight?.toFixed(2) || '1.00' }}
            </span>
          </td>
          <td class="p-3 text-xs text-gray-500">
            {{ formatDate(memory.created_at) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
