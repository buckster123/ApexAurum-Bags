<script setup>
/**
 * NurseryApprentices - Apprentice Protocol tab
 * Create, train, and manage apprentice agents.
 */

import { ref, onMounted } from 'vue'
import { useNurseryStore } from '@/stores/nursery'
import { formatRelativeTime, useConfirmDelete } from './nurseryUtils'

const nursery = useNurseryStore()

// Confirm-before-delete composable
const { requestDelete, isConfirming } = useConfirmDelete()

// Form state
const masterAgent = ref('AZOTH')
const apprenticeName = ref('')
const specialization = ref('')
const autoGenerate = ref(false)
const apprenticeNumExamples = ref(50)
const apprenticeError = ref('')
const apprenticeSuccess = ref('')

// Constants
const masterAgents = [
  { id: 'AZOTH', label: 'Azoth', color: 'text-[#D4AF37]', bg: 'bg-[#D4AF37]/10 border-[#D4AF37]/30' },
  { id: 'ELYSIAN', label: 'Elysian', color: 'text-[#9B59B6]', bg: 'bg-[#9B59B6]/10 border-[#9B59B6]/30' },
  { id: 'VAJRA', label: 'Vajra', color: 'text-[#E74C3C]', bg: 'bg-[#E74C3C]/10 border-[#E74C3C]/30' },
  { id: 'KETHER', label: 'Kether', color: 'text-[#3498DB]', bg: 'bg-[#3498DB]/10 border-[#3498DB]/30' },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function getApprenticeStatusColor(status) {
  const colors = {
    dataset_ready: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
    training: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    trained: 'bg-green-500/20 text-green-400 border-green-500/30',
    failed: 'bg-red-500/20 text-red-400 border-red-500/30',
  }
  return colors[status] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'
}

function getApprenticeStatusLabel(status) {
  const labels = { dataset_ready: 'Ready', training: 'Training', trained: 'Trained', failed: 'Failed' }
  return labels[status] || status
}

function getMasterColor(agent) {
  const found = masterAgents.find(m => m.id === agent)
  return found ? found.color : 'text-gray-400'
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------
async function handleCreateApprentice() {
  if (!apprenticeName.value.trim()) {
    apprenticeError.value = 'Apprentice name is required.'
    return
  }
  apprenticeError.value = ''
  apprenticeSuccess.value = ''
  try {
    const result = await nursery.createApprentice(
      masterAgent.value,
      apprenticeName.value.trim(),
      specialization.value.trim() || null,
      autoGenerate.value,
      apprenticeNumExamples.value,
    )
    apprenticeSuccess.value = result.message || 'Apprentice created!'
    apprenticeName.value = ''
    specialization.value = ''
    autoGenerate.value = false
    apprenticeNumExamples.value = 50
  } catch (e) {
    apprenticeError.value = e.response?.data?.detail || e.message || 'Failed to create apprentice.'
  }
}

async function handleAutoTrain(apprentice) {
  if (!nursery.hasTogetherAccess) return
  try {
    await nursery.startTraining({
      datasetId: apprentice.dataset_id,
      baseModel: 'meta-llama/Llama-3.2-3B-Instruct',
      nEpochs: 3,
      learningRate: 1e-5,
      lora: true,
      apprenticeId: apprentice.id,
    })
    await nursery.fetchApprentices()
  } catch (e) {
    console.error('Auto-train failed:', e)
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
onMounted(() => {
  nursery.fetchApprentices()
})
</script>

<template>
  <div class="space-y-6">
    <div class="grid lg:grid-cols-2 gap-6">

      <!-- Left: Create Apprentice Form -->
      <div class="bg-apex-card border border-apex-border rounded-xl p-6">
        <h3 class="text-lg font-bold text-white mb-4">Create Apprentice</h3>

        <!-- Master Agent Selector -->
        <div class="mb-4">
          <label class="block text-sm text-gray-400 mb-2">Master Agent</label>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="agent in masterAgents"
              :key="agent.id"
              @click="masterAgent = agent.id"
              :class="masterAgent === agent.id ? agent.bg + ' border' : 'bg-apex-dark border border-apex-border hover:border-gray-500'"
              class="px-3 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              <span :class="agent.color">{{ agent.label }}</span>
            </button>
          </div>
        </div>

        <!-- Apprentice Name -->
        <div class="mb-4">
          <label class="block text-sm text-gray-400 mb-2">Apprentice Name</label>
          <input
            v-model="apprenticeName"
            type="text"
            placeholder="e.g., Search Scholar"
            class="input w-full"
            :disabled="nursery.creatingApprentice"
          />
        </div>

        <!-- Specialization -->
        <div class="mb-4">
          <label class="block text-sm text-gray-400 mb-2">Specialization</label>
          <input
            v-model="specialization"
            type="text"
            placeholder="e.g., web_search, cortex_recall"
            class="input w-full"
            :disabled="nursery.creatingApprentice"
          />
          <p class="text-xs text-gray-500 mt-1">Comma-separated tool names for training data</p>
        </div>

        <!-- Auto-Generate Toggle -->
        <div class="mb-4">
          <label class="flex items-center gap-2 cursor-pointer">
            <input
              v-model="autoGenerate"
              type="checkbox"
              class="w-4 h-4 rounded bg-apex-dark border-apex-border accent-gold"
              :disabled="nursery.creatingApprentice"
            />
            <span class="text-sm text-gray-300">Auto-generate training dataset</span>
          </label>
        </div>

        <!-- Num Examples (shown when auto-generate is on) -->
        <div v-if="autoGenerate" class="mb-4">
          <label class="block text-sm text-gray-400 mb-2">
            Training Examples: <span class="text-white font-bold">{{ apprenticeNumExamples }}</span>
          </label>
          <input
            v-model.number="apprenticeNumExamples"
            type="range"
            min="10"
            max="500"
            step="10"
            class="w-full accent-gold"
          />
          <div class="flex justify-between text-xs text-gray-500 mt-1">
            <span>10</span>
            <span>250</span>
            <span>500</span>
          </div>
        </div>

        <!-- Messages -->
        <div v-if="apprenticeError" class="bg-red-500/10 border border-red-500/50 rounded-lg p-3 text-red-400 text-sm mb-4">
          {{ apprenticeError }}
        </div>
        <div v-if="apprenticeSuccess" class="bg-green-500/10 border border-green-500/50 rounded-lg p-3 text-green-400 text-sm mb-4">
          {{ apprenticeSuccess }}
        </div>

        <!-- Create Button -->
        <button
          @click="handleCreateApprentice"
          :disabled="nursery.creatingApprentice || !apprenticeName.trim()"
          class="w-full py-2.5 bg-gold text-black font-bold rounded-lg hover:bg-gold/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ nursery.creatingApprentice ? 'Creating...' : 'Create Apprentice' }}
        </button>
      </div>

      <!-- Right: Apprentice List -->
      <div>
        <!-- Stats bar (MOBILE FIX: flex flex-wrap) -->
        <div class="flex flex-wrap items-center gap-3 mb-4 text-sm">
          <div class="bg-apex-card border border-apex-border rounded-lg px-3 py-1.5">
            <span class="text-gray-400">Total:</span>
            <span class="text-white font-bold ml-1">{{ nursery.apprentices.length }}</span>
          </div>
          <div class="bg-apex-card border border-apex-border rounded-lg px-3 py-1.5">
            <span class="text-gray-400">Training:</span>
            <span class="text-amber-400 font-bold ml-1">{{ nursery.trainingApprentices }}</span>
          </div>
          <div class="bg-apex-card border border-apex-border rounded-lg px-3 py-1.5">
            <span class="text-gray-400">Trained:</span>
            <span class="text-green-400 font-bold ml-1">{{ nursery.trainedApprentices }}</span>
          </div>
        </div>

        <!-- Loading -->
        <div v-if="nursery.loadingApprentices" class="text-center py-12">
          <div class="animate-spin h-8 w-8 border-2 border-gold border-t-transparent rounded-full mx-auto mb-3"></div>
          <p class="text-gray-400">Loading apprentices...</p>
        </div>

        <!-- Empty state -->
        <div v-else-if="!nursery.apprentices.length" class="text-center py-12 bg-apex-card border border-apex-border rounded-xl">
          <div class="text-5xl text-gray-600 mb-4">&#9734;</div>
          <h3 class="text-lg font-bold text-gray-300 mb-2">No Apprentices Yet</h3>
          <p class="text-gray-500 max-w-sm mx-auto">
            Create an apprentice to begin raising a new mind under one of the four masters.
          </p>
        </div>

        <!-- Apprentice cards -->
        <div v-else class="space-y-3">
          <div
            v-for="a in nursery.apprentices"
            :key="a.id"
            class="bg-apex-card border border-apex-border rounded-xl p-4 hover:border-gold/20 transition-colors"
          >
            <!-- Header -->
            <div class="flex items-start justify-between mb-2">
              <div>
                <h4 class="font-bold text-white">{{ a.apprentice_name }}</h4>
                <p class="text-sm">
                  <span class="text-gray-500">Master:</span>
                  <span :class="getMasterColor(a.master_agent)" class="font-medium ml-1">{{ a.master_agent }}</span>
                </p>
              </div>
              <span
                :class="getApprenticeStatusColor(a.status)"
                class="text-xs px-2 py-1 rounded-full border"
              >
                {{ getApprenticeStatusLabel(a.status) }}
              </span>
            </div>

            <!-- Specialization -->
            <p v-if="a.specialization" class="text-xs text-gray-400 mb-2">
              Specialization: <span class="text-gray-300">{{ a.specialization }}</span>
            </p>

            <!-- Dataset / Model info -->
            <div class="text-xs text-gray-500 space-y-1 mb-3">
              <div v-if="a.dataset_name">
                Dataset: <span class="text-gray-300">{{ a.dataset_name }}</span>
                <span class="text-gray-600">({{ a.num_examples }} examples)</span>
              </div>
              <div v-if="a.model_name">
                Model: <span class="text-green-400">{{ a.model_name }}</span>
              </div>
            </div>

            <!-- Footer -->
            <div class="flex items-center justify-between pt-2 border-t border-apex-border">
              <span class="text-xs text-gray-500">{{ formatRelativeTime(a.created_at) }}</span>
              <div class="flex items-center gap-2">
                <!-- Start Training button (only for dataset_ready with Together key) -->
                <button
                  v-if="a.status === 'dataset_ready' && a.dataset_id && nursery.hasTogetherAccess"
                  @click="handleAutoTrain(a)"
                  class="text-xs bg-gold/10 text-gold px-3 py-1 rounded-lg border border-gold/30 hover:bg-gold/20 transition-colors"
                >
                  Start Training
                </button>
                <span
                  v-if="a.status === 'dataset_ready' && !nursery.hasTogetherAccess"
                  class="text-xs text-gray-500 italic"
                >
                  Needs Together.ai access
                </span>
                <!-- Delete -->
                <button
                  @click="requestDelete(a.id, (id) => nursery.deleteApprentice(id))"
                  :class="isConfirming(a.id) ? 'bg-red-500/20 text-red-400 border-red-500/30' : 'bg-apex-dark text-gray-500 border-apex-border hover:text-red-400 hover:border-red-500/30'"
                  class="text-xs px-3 py-1 rounded-lg border transition-colors"
                >
                  {{ isConfirming(a.id) ? 'Confirm?' : 'Delete' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>
