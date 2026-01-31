<script setup>
/**
 * NurseryVillageFeed - Village Feed tab
 * Activity feed and model discovery.
 */

import { onMounted } from 'vue'
import { useNurseryStore } from '@/stores/nursery'
import { formatRelativeTime, getStatusColor } from './nurseryUtils'

const nursery = useNurseryStore()

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------
async function handleDiscover() {
  await nursery.discoverModels(nursery.discoveryQuery)
}

function getActivityIcon(type) {
  return type === 'training_job' ? '&#9881;' : '&#9733;'
}

function getActivityColor(item) {
  if (item.type === 'model_created') return item.village_posted ? 'text-green-400' : 'text-cyan-400'
  const colors = { completed: 'text-green-400', running: 'text-amber-400', failed: 'text-red-400', pending: 'text-gray-400' }
  return colors[item.status] || 'text-gray-400'
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
onMounted(() => {
  nursery.fetchVillageActivity()
})
</script>

<template>
  <div class="space-y-8">

    <!-- Activity Feed -->
    <div>
      <h3 class="text-lg font-bold text-white mb-4">Recent Activity</h3>

      <div v-if="nursery.loadingActivity" class="text-center py-8">
        <div class="animate-spin h-6 w-6 border-2 border-gold border-t-transparent rounded-full mx-auto"></div>
      </div>

      <div v-else-if="!nursery.villageActivity.length" class="text-center py-8">
        <p class="text-gray-500">No nursery activity yet. Generate datasets or start training to see events here.</p>
      </div>

      <div v-else class="space-y-2">
        <div
          v-for="item in nursery.villageActivity"
          :key="item.type + '-' + item.id"
          class="bg-apex-card border border-apex-border rounded-lg px-4 py-3 flex items-center gap-3"
        >
          <!-- Icon -->
          <div
            :class="getActivityColor(item)"
            class="text-lg flex-shrink-0"
            v-html="getActivityIcon(item.type)"
          ></div>
          <!-- Message -->
          <div class="flex-1 min-w-0">
            <p class="text-sm text-gray-200 truncate">{{ item.message }}</p>
            <div class="flex items-center gap-2 mt-0.5">
              <span v-if="item.agent_id" class="text-xs text-gold/70">{{ item.agent_id }}</span>
              <span v-if="item.status && item.type === 'training_job'" :class="getStatusColor(item.status)" class="text-xs px-1.5 py-0.5 rounded">
                {{ item.status }}
              </span>
            </div>
          </div>
          <!-- Timestamp -->
          <span class="text-xs text-gray-500 flex-shrink-0">{{ formatRelativeTime(item.timestamp) }}</span>
        </div>
      </div>
    </div>

    <!-- Model Discovery -->
    <div>
      <h3 class="text-lg font-bold text-white mb-4">Discover Models</h3>
      <div class="flex gap-2 mb-4">
        <input
          v-model="nursery.discoveryQuery"
          type="text"
          placeholder="Search Village for models..."
          class="input flex-1"
          @keyup.enter="handleDiscover"
        />
        <button
          @click="handleDiscover"
          :disabled="nursery.loadingDiscovery"
          class="px-4 py-2 bg-gold/10 text-gold border border-gold/30 rounded-lg hover:bg-gold/20 transition-colors text-sm"
        >
          {{ nursery.loadingDiscovery ? 'Searching...' : 'Search' }}
        </button>
      </div>

      <div v-if="nursery.loadingDiscovery" class="text-center py-6">
        <div class="animate-spin h-6 w-6 border-2 border-gold border-t-transparent rounded-full mx-auto"></div>
      </div>

      <div v-else-if="nursery.discoveredModels.length" class="space-y-2">
        <div
          v-for="(item, idx) in nursery.discoveredModels"
          :key="idx"
          class="bg-apex-card border border-apex-border rounded-lg px-4 py-3"
        >
          <p class="text-sm text-gray-200">{{ item.content || item.text || JSON.stringify(item) }}</p>
          <div class="flex items-center gap-2 mt-1">
            <span v-if="item.agent_id" class="text-xs text-gold/70">{{ item.agent_id }}</span>
            <span v-if="item.created_at" class="text-xs text-gray-500">{{ formatRelativeTime(item.created_at) }}</span>
          </div>
        </div>
      </div>

      <div v-else class="text-center py-6">
        <p class="text-gray-500 text-sm">No shared models found. Register models in the Model Cradle to share them.</p>
      </div>
    </div>

  </div>
</template>
