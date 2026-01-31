<script setup>
/**
 * MemoryFilters - Filter Panel for Neural Space
 *
 * Left sidebar with filters for layer, visibility, agent, etc.
 */

import { ref, computed } from 'vue'
import { useNeoCortexStore, AGENT_COLORS, LAYER_CONFIG } from '@/stores/neocortex'

const store = useNeoCortexStore()
const searchInput = ref('')

const layers = computed(() => Object.keys(LAYER_CONFIG))
const agents = computed(() => Object.keys(AGENT_COLORS))
const visibilities = ['private', 'village', 'bridge']
const messageTypes = ['observation', 'insight', 'decision', 'question', 'response']

async function handleSearch() {
  if (searchInput.value.trim()) {
    await store.searchMemories(searchInput.value)
  } else {
    await store.fetchGraphData()
  }
}

function clearSearch() {
  searchInput.value = ''
  store.fetchGraphData()
}

function toggleLayer(layer) {
  store.setFilter('layer', store.filters.layer === layer ? null : layer)
}

function toggleVisibility(vis) {
  store.setFilter('visibility', store.filters.visibility === vis ? null : vis)
}

function toggleAgent(agent) {
  store.setFilter('agent_id', store.filters.agent_id === agent ? null : agent)
}

function clearAllFilters() {
  store.clearFilters()
  searchInput.value = ''
  store.fetchGraphData()
}
</script>

<template>
  <div class="memory-filters h-full flex flex-col bg-apex-dark border-r border-apex-border">
    <!-- Header -->
    <div class="p-4 border-b border-apex-border">
      <h3 class="text-sm font-semibold text-gold uppercase tracking-wider">Filters</h3>
    </div>

    <!-- Search -->
    <div class="p-4 border-b border-apex-border">
      <label class="text-xs text-gray-500 uppercase tracking-wider mb-2 block">Search</label>
      <div class="relative">
        <input
          v-model="searchInput"
          @keyup.enter="handleSearch"
          type="text"
          placeholder="Semantic search..."
          class="w-full bg-white/5 border border-apex-border rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-gold focus:outline-none pr-8"
        />
        <button
          v-if="searchInput"
          @click="clearSearch"
          class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white"
        >
          &times;
        </button>
      </div>
      <button
        @click="handleSearch"
        class="mt-2 w-full bg-gold/20 hover:bg-gold/30 text-gold text-xs py-1.5 rounded transition-colors"
      >
        Search Memories
      </button>
    </div>

    <!-- Layer Filter -->
    <div class="p-4 border-b border-apex-border">
      <label class="text-xs text-gray-500 uppercase tracking-wider mb-2 block">Layer</label>
      <div class="flex flex-wrap gap-2">
        <button
          v-for="layer in layers"
          :key="layer"
          @click="toggleLayer(layer)"
          :class="[
            'px-2 py-1 text-xs rounded transition-colors',
            store.filters.layer === layer
              ? 'bg-gold text-black'
              : 'bg-white/5 text-gray-400 hover:bg-white/10'
          ]"
        >
          {{ layer }}
        </button>
      </div>
    </div>

    <!-- Visibility Filter -->
    <div class="p-4 border-b border-apex-border">
      <label class="text-xs text-gray-500 uppercase tracking-wider mb-2 block">Visibility</label>
      <div class="flex flex-wrap gap-2">
        <button
          v-for="vis in visibilities"
          :key="vis"
          @click="toggleVisibility(vis)"
          :class="[
            'px-2 py-1 text-xs rounded transition-colors',
            store.filters.visibility === vis
              ? 'bg-gold text-black'
              : 'bg-white/5 text-gray-400 hover:bg-white/10'
          ]"
        >
          {{ vis }}
        </button>
      </div>
    </div>

    <!-- Agent Filter -->
    <div class="p-4 border-b border-apex-border">
      <label class="text-xs text-gray-500 uppercase tracking-wider mb-2 block">Agent</label>
      <div class="flex flex-wrap gap-2">
        <button
          v-for="agent in agents"
          :key="agent"
          @click="toggleAgent(agent)"
          :class="[
            'px-2 py-1 text-xs rounded transition-colors flex items-center gap-1',
            store.filters.agent_id === agent
              ? 'ring-2 ring-offset-2 ring-offset-apex-dark'
              : 'bg-white/5 text-gray-400 hover:bg-white/10'
          ]"
          :style="{
            backgroundColor: store.filters.agent_id === agent ? AGENT_COLORS[agent].hex : '',
            color: store.filters.agent_id === agent ? '#000' : '',
            '--tw-ring-color': AGENT_COLORS[agent].hex
          }"
        >
          <span
            class="w-2 h-2 rounded-full"
            :style="{ backgroundColor: AGENT_COLORS[agent].hex }"
          ></span>
          {{ agent }}
        </button>
      </div>
    </div>

    <!-- Stats Summary -->
    <div class="p-4 flex-1 overflow-auto">
      <label class="text-xs text-gray-500 uppercase tracking-wider mb-2 block">Quick Stats</label>

      <div class="space-y-3">
        <div
          v-for="item in store.layerBreakdown"
          :key="item.layer"
          class="flex items-center justify-between"
        >
          <span class="text-xs text-gray-400">{{ item.layer }}</span>
          <div class="flex items-center gap-2">
            <div class="w-16 h-1.5 bg-white/10 rounded-full overflow-hidden">
              <div
                class="h-full bg-gold rounded-full"
                :style="{ width: `${item.percentage}%` }"
              ></div>
            </div>
            <span class="text-xs text-gray-500 w-8 text-right">{{ item.count }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Clear Filters -->
    <div class="p-4 border-t border-apex-border">
      <button
        @click="clearAllFilters"
        class="w-full bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white text-xs py-2 rounded transition-colors"
      >
        Clear All Filters
      </button>
    </div>
  </div>
</template>
