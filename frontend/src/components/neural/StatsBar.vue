<script setup>
/**
 * StatsBar - Top stats bar for Neural Space dashboard
 *
 * Shows memory counts and view toggle.
 */

import { computed } from 'vue'
import { useNeoCortexStore, AGENT_COLORS } from '@/stores/neocortex'

const emit = defineEmits(['toggleView'])

const store = useNeoCortexStore()

const totalMemories = computed(() => store.memoryCount)
const activeFilters = computed(() => {
  let count = 0
  if (store.filters.layer) count++
  if (store.filters.visibility) count++
  if (store.filters.agent_id) count++
  return count
})

function setView(mode) {
  store.setViewMode(mode)
  emit('toggleView', mode)
}
</script>

<template>
  <div class="stats-bar h-12 bg-apex-dark/80 backdrop-blur border-b border-apex-border flex items-center justify-between px-4">
    <!-- Left: Title + Stats -->
    <div class="flex items-center gap-6">
      <div class="flex items-center gap-2">
        <span class="text-lg">🧠</span>
        <span class="font-medium text-white">Neural Space</span>
      </div>

      <div class="hidden sm:flex items-center gap-4 text-xs">
        <div class="flex items-center gap-1">
          <span class="text-gray-500">Memories:</span>
          <span class="text-gold font-mono">{{ totalMemories }}</span>
        </div>

        <div class="flex items-center gap-1">
          <span class="text-gray-500">Showing:</span>
          <span class="text-white font-mono">{{ store.filteredNodes.length }}</span>
        </div>

        <div v-if="activeFilters > 0" class="flex items-center gap-1">
          <span class="px-1.5 py-0.5 bg-gold/20 text-gold rounded text-xs">
            {{ activeFilters }} filter{{ activeFilters > 1 ? 's' : '' }}
          </span>
        </div>
      </div>
    </div>

    <!-- Center: Agent Legend (hidden on mobile) -->
    <div class="hidden md:flex items-center gap-3">
      <div
        v-for="(color, agent) in AGENT_COLORS"
        :key="agent"
        class="flex items-center gap-1"
      >
        <span
          class="w-2 h-2 rounded-full"
          :style="{ backgroundColor: color.hex }"
        ></span>
        <span class="text-xs text-gray-500">{{ agent }}</span>
      </div>
    </div>

    <!-- Right: View Toggle -->
    <div class="flex items-center gap-1 bg-white/5 rounded-lg p-1">
      <button
        @click="setView('3d')"
        :class="[
          'px-3 py-1 text-xs rounded transition-colors',
          store.viewMode === '3d'
            ? 'bg-gold text-black'
            : 'text-gray-400 hover:text-white'
        ]"
      >
        3D
      </button>
      <button
        @click="setView('list')"
        :class="[
          'px-3 py-1 text-xs rounded transition-colors',
          store.viewMode === 'list'
            ? 'bg-gold text-black'
            : 'text-gray-400 hover:text-white'
        ]"
      >
        List
      </button>
    </div>
  </div>
</template>
