<script setup>
/**
 * MemoryDetailPanel - Right sidebar for selected memory details
 *
 * Shows full content, metadata, and actions for the selected memory.
 */

import { ref, computed } from 'vue'
import { useNeoCortexStore, AGENT_COLORS, LAYER_CONFIG } from '@/stores/neocortex'
import { useSound } from '@/composables/useSound'

const store = useNeoCortexStore()
const { playTone } = useSound()

const isPromoting = ref(false)
const isDeleting = ref(false)
const showDeleteConfirm = ref(false)

const memory = computed(() => store.selectedMemory)

const agentColor = computed(() =>
  AGENT_COLORS[memory.value?.agent_id] || AGENT_COLORS.CLAUDE
)

const layerIndex = computed(() =>
  Object.keys(LAYER_CONFIG).indexOf(memory.value?.layer || 'working')
)

async function promoteLayer() {
  if (!memory.value) return

  const layers = Object.keys(LAYER_CONFIG)
  const currentIndex = layers.indexOf(memory.value.layer)

  if (currentIndex > 0) {
    isPromoting.value = true
    try {
      await store.promoteMemory(memory.value.id, layers[currentIndex - 1])
      playTone(880, 0.1, 'sine', 0.2)
    } catch (e) {
      playTone(220, 0.15, 'sawtooth', 0.15)
    } finally {
      isPromoting.value = false
    }
  }
}

async function demoteLayer() {
  if (!memory.value) return

  const layers = Object.keys(LAYER_CONFIG)
  const currentIndex = layers.indexOf(memory.value.layer)

  if (currentIndex < layers.length - 1) {
    isPromoting.value = true
    try {
      await store.promoteMemory(memory.value.id, layers[currentIndex + 1])
      playTone(440, 0.1, 'sine', 0.15)
    } catch (e) {
      playTone(220, 0.15, 'sawtooth', 0.15)
    } finally {
      isPromoting.value = false
    }
  }
}

async function confirmDelete() {
  if (!memory.value) return

  isDeleting.value = true
  try {
    await store.deleteMemory(memory.value.id)
    showDeleteConfirm.value = false
    playTone(330, 0.1, 'sine', 0.1)
  } catch (e) {
    playTone(220, 0.15, 'sawtooth', 0.15)
  } finally {
    isDeleting.value = false
  }
}

function formatDate(dateStr) {
  if (!dateStr) return 'N/A'
  return new Date(dateStr).toLocaleString()
}

function close() {
  store.clearSelection()
}
</script>

<template>
  <div class="memory-detail-panel h-full flex flex-col bg-apex-dark border-l border-apex-border">
    <!-- Empty state -->
    <div v-if="!memory" class="flex-1 flex items-center justify-center p-8">
      <div class="text-center text-gray-500">
        <div class="text-4xl mb-4 opacity-50">🧠</div>
        <p class="text-sm">Select a memory node to view details</p>
      </div>
    </div>

    <!-- Memory details -->
    <template v-else>
      <!-- Header -->
      <div class="p-4 border-b border-apex-border flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span
            class="w-4 h-4 rounded-full"
            :style="{ backgroundColor: agentColor.hex }"
          ></span>
          <span class="text-sm font-medium text-white">{{ memory.agent_id || 'CLAUDE' }}</span>
        </div>
        <button
          @click="close"
          class="text-gray-500 hover:text-white transition-colors"
        >
          &times;
        </button>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-auto p-4 space-y-4">
        <!-- Layer badge -->
        <div class="flex items-center gap-2">
          <span
            class="px-2 py-1 text-xs rounded uppercase tracking-wider"
            :class="{
              'bg-white/20 text-white': memory.layer === 'cortex',
              'bg-white/15 text-gray-300': memory.layer === 'long_term',
              'bg-white/10 text-gray-400': memory.layer === 'working',
              'bg-white/5 text-gray-500': memory.layer === 'sensory',
            }"
          >
            {{ memory.layer }}
          </span>
          <span class="text-xs text-gray-500">|</span>
          <span class="text-xs text-gray-500">{{ memory.visibility }}</span>
          <span class="text-xs text-gray-500">|</span>
          <span class="text-xs text-gray-500">{{ memory.message_type }}</span>
        </div>

        <!-- Main content -->
        <div class="bg-white/5 rounded-lg p-4">
          <p class="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">
            {{ memory.content }}
          </p>
        </div>

        <!-- Metadata -->
        <div class="space-y-2">
          <h4 class="text-xs text-gray-500 uppercase tracking-wider">Metadata</h4>

          <div class="grid grid-cols-2 gap-2 text-xs">
            <div class="bg-white/5 rounded p-2">
              <div class="text-gray-500 mb-1">Attention</div>
              <div class="text-gold font-mono">{{ memory.attention_weight?.toFixed(2) || '1.00' }}</div>
            </div>
            <div class="bg-white/5 rounded p-2">
              <div class="text-gray-500 mb-1">Access Count</div>
              <div class="text-white font-mono">{{ memory.access_count || 0 }}</div>
            </div>
          </div>

          <div class="bg-white/5 rounded p-2 text-xs">
            <div class="text-gray-500 mb-1">Created</div>
            <div class="text-gray-300">{{ formatDate(memory.created_at) }}</div>
          </div>

          <div v-if="memory.last_accessed_at" class="bg-white/5 rounded p-2 text-xs">
            <div class="text-gray-500 mb-1">Last Accessed</div>
            <div class="text-gray-300">{{ formatDate(memory.last_accessed_at) }}</div>
          </div>

          <!-- Tags -->
          <div v-if="memory.tags?.length" class="bg-white/5 rounded p-2 text-xs">
            <div class="text-gray-500 mb-2">Tags</div>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="tag in memory.tags"
                :key="tag"
                class="px-2 py-0.5 bg-gold/20 text-gold rounded text-xs"
              >
                {{ tag }}
              </span>
            </div>
          </div>

          <!-- Related agents -->
          <div v-if="memory.related_agents?.length" class="bg-white/5 rounded p-2 text-xs">
            <div class="text-gray-500 mb-2">Related Agents</div>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="agent in memory.related_agents"
                :key="agent"
                class="px-2 py-0.5 rounded text-xs flex items-center gap-1"
                :style="{ backgroundColor: AGENT_COLORS[agent]?.hex + '33' }"
              >
                <span
                  class="w-2 h-2 rounded-full"
                  :style="{ backgroundColor: AGENT_COLORS[agent]?.hex }"
                ></span>
                {{ agent }}
              </span>
            </div>
          </div>
        </div>

        <!-- ID (for debugging) -->
        <div class="text-xs text-gray-600 font-mono truncate" :title="memory.id">
          ID: {{ memory.id }}
        </div>
      </div>

      <!-- Actions -->
      <div class="p-4 border-t border-apex-border space-y-2">
        <!-- Layer controls -->
        <div class="flex gap-2">
          <button
            @click="promoteLayer"
            :disabled="isPromoting || layerIndex === 0"
            class="flex-1 bg-green-500/20 hover:bg-green-500/30 disabled:opacity-50 disabled:cursor-not-allowed text-green-400 text-xs py-2 rounded transition-colors"
          >
            Promote Layer
          </button>
          <button
            @click="demoteLayer"
            :disabled="isPromoting || layerIndex === 3"
            class="flex-1 bg-orange-500/20 hover:bg-orange-500/30 disabled:opacity-50 disabled:cursor-not-allowed text-orange-400 text-xs py-2 rounded transition-colors"
          >
            Demote Layer
          </button>
        </div>

        <!-- Delete -->
        <button
          v-if="!showDeleteConfirm"
          @click="showDeleteConfirm = true"
          class="w-full bg-red-500/10 hover:bg-red-500/20 text-red-400 text-xs py-2 rounded transition-colors"
        >
          Delete Memory
        </button>

        <!-- Delete confirmation -->
        <div v-else class="bg-red-500/20 rounded p-3">
          <p class="text-xs text-red-300 mb-2">Are you sure? This cannot be undone.</p>
          <div class="flex gap-2">
            <button
              @click="confirmDelete"
              :disabled="isDeleting"
              class="flex-1 bg-red-500 hover:bg-red-600 text-white text-xs py-1.5 rounded transition-colors"
            >
              {{ isDeleting ? 'Deleting...' : 'Yes, Delete' }}
            </button>
            <button
              @click="showDeleteConfirm = false"
              class="flex-1 bg-white/10 hover:bg-white/20 text-gray-300 text-xs py-1.5 rounded transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
