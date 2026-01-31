<script setup>
/**
 * NurseryModelCradle - Model Cradle tab
 * View trained models, register in Village, delete.
 */

import { onMounted } from 'vue'
import { useNurseryStore } from '@/stores/nursery'
import { formatRelativeTime, useConfirmDelete } from './nurseryUtils'

const nursery = useNurseryStore()
const emit = defineEmits(['navigate-tab'])

// Confirm-before-delete composable
const { requestDelete, isConfirming } = useConfirmDelete()

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function getModelTypeColor(type) {
  const colors = {
    lora_adapter: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
    cloud_hosted: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
    uploaded: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  }
  return colors[type] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'
}

function getModelTypeLabel(type) {
  const labels = { lora_adapter: 'LoRA', cloud_hosted: 'Cloud', uploaded: 'Uploaded' }
  return labels[type] || type
}

async function handleRegister(modelId) {
  try {
    await nursery.registerModel(modelId)
  } catch (e) {
    console.error('Registration failed:', e)
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
onMounted(() => {
  nursery.fetchModels()
})
</script>

<template>
  <div class="space-y-6">
    <!-- Stats bar -->
    <div class="flex items-center gap-4 text-sm">
      <div class="bg-apex-card border border-apex-border rounded-lg px-4 py-2">
        <span class="text-gray-400">Models:</span>
        <span class="text-white font-bold ml-1">{{ nursery.models.length }}</span>
      </div>
      <div class="bg-apex-card border border-apex-border rounded-lg px-4 py-2">
        <span class="text-gray-400">In Village:</span>
        <span class="text-green-400 font-bold ml-1">{{ nursery.villageModels }}</span>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="nursery.loadingModels" class="text-center py-16">
      <div class="animate-spin h-8 w-8 border-2 border-gold border-t-transparent rounded-full mx-auto mb-3"></div>
      <p class="text-gray-400">Loading models...</p>
    </div>

    <!-- Empty state -->
    <div v-else-if="!nursery.models.length" class="text-center py-16">
      <div class="text-5xl text-gray-600 mb-4">&#10697;</div>
      <h3 class="text-lg font-bold text-gray-300 mb-2">No Trained Models Yet</h3>
      <p class="text-gray-500 max-w-md mx-auto mb-4">
        Models appear here when training jobs complete. Start a training job in the Forge tab.
      </p>
      <button @click="emit('navigate-tab', 'forge')" class="text-gold hover:text-gold-bright text-sm">
        Go to Training Forge &rarr;
      </button>
    </div>

    <!-- Model cards grid -->
    <div v-else class="grid md:grid-cols-2 gap-4">
      <div
        v-for="model in nursery.models"
        :key="model.id"
        class="bg-apex-card border border-apex-border rounded-xl p-5 hover:border-gold/30 transition-colors"
      >
        <!-- Header -->
        <div class="flex items-start justify-between mb-3">
          <div>
            <h3 class="font-bold text-white">{{ model.name }}</h3>
            <p class="text-sm text-gray-400">{{ model.base_model?.split('/').pop() || 'Unknown base' }}</p>
          </div>
          <span
            :class="getModelTypeColor(model.model_type)"
            class="text-xs px-2 py-1 rounded-full border"
          >
            {{ getModelTypeLabel(model.model_type) }}
          </span>
        </div>

        <!-- Capabilities -->
        <div v-if="model.capabilities?.length" class="flex flex-wrap gap-1 mb-3">
          <span
            v-for="cap in model.capabilities.slice(0, 5)"
            :key="cap"
            class="text-xs bg-gold/10 text-gold px-2 py-0.5 rounded"
          >
            {{ cap }}
          </span>
          <span v-if="model.capabilities.length > 5" class="text-xs text-gray-500">
            +{{ model.capabilities.length - 5 }} more
          </span>
        </div>

        <!-- Performance -->
        <div v-if="model.performance" class="text-xs text-gray-500 mb-3">
          <span v-if="model.performance.final_loss">Loss: {{ model.performance.final_loss }}</span>
          <span v-if="model.performance.events_count"> &middot; {{ model.performance.events_count }} events</span>
        </div>

        <!-- Footer -->
        <div class="flex items-center justify-between pt-3 border-t border-apex-border">
          <span class="text-xs text-gray-500">{{ formatRelativeTime(model.created_at) }}</span>
          <div class="flex items-center gap-2">
            <!-- Village status -->
            <button
              v-if="model.village_posted"
              disabled
              class="text-xs bg-green-500/10 text-green-400 px-3 py-1 rounded-lg border border-green-500/30"
            >
              &#10003; In Village
            </button>
            <button
              v-else
              @click="handleRegister(model.id)"
              class="text-xs bg-gold/10 text-gold px-3 py-1 rounded-lg border border-gold/30 hover:bg-gold/20 transition-colors"
            >
              Register in Village
            </button>
            <!-- Delete -->
            <button
              @click="requestDelete(model.id, (id) => nursery.deleteModel(id))"
              :class="isConfirming(model.id) ? 'bg-red-500/20 text-red-400 border-red-500/30' : 'bg-apex-dark text-gray-500 border-apex-border hover:text-red-400 hover:border-red-500/30'"
              class="text-xs px-3 py-1 rounded-lg border transition-colors"
            >
              {{ isConfirming(model.id) ? 'Confirm?' : 'Delete' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
