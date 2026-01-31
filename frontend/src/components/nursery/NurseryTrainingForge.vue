<script setup>
/**
 * NurseryTrainingForge - Training Forge tab
 * Start training jobs, monitor progress, manage costs.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useNurseryStore } from '@/stores/nursery'
import { formatRelativeTime, getStatusColor } from './nurseryUtils'

const nursery = useNurseryStore()

// Form state
const forgeDataset = ref('')
const forgeModel = ref('meta-llama/Llama-3.2-3B-Instruct')
const forgeEpochs = ref(3)
const forgeLearningRate = ref('1e-5')
const forgeLora = ref(true)
const forgeBatchSize = ref('')
const forgeSuffix = ref('')
const forgeError = ref('')
const forgeSuccess = ref('')

let jobPollInterval = null

// Constants
const forgeModels = [
  { id: 'meta-llama/Llama-3.2-1B-Instruct', label: 'Llama 3.2 1B', size: '1B' },
  { id: 'meta-llama/Llama-3.2-3B-Instruct', label: 'Llama 3.2 3B', size: '3B' },
  { id: 'meta-llama/Meta-Llama-3.1-8B-Instruct-Reference', label: 'Llama 3.1 8B', size: '8B' },
  { id: 'Qwen/Qwen2.5-7B-Instruct', label: 'Qwen 2.5 7B', size: '7B' },
]

const learningRates = [
  { value: '1e-4', label: '1e-4 (aggressive)' },
  { value: '5e-5', label: '5e-5 (moderate)' },
  { value: '1e-5', label: '1e-5 (default)' },
  { value: '5e-6', label: '5e-6 (gentle)' },
]

// Local computed
const failedJobs = computed(() => nursery.trainingJobs.filter(j => j.status === 'failed').length)

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------
async function handleEstimate() {
  if (!forgeDataset.value) return
  try {
    await nursery.estimateCost(
      forgeDataset.value,
      forgeModel.value,
      forgeEpochs.value,
      forgeLora.value,
    )
  } catch (e) {
    console.error('Estimate failed:', e)
  }
}

async function handleStartTraining() {
  if (!forgeDataset.value) {
    forgeError.value = 'Select a dataset first.'
    return
  }
  if (!nursery.hasTogetherAccess) {
    forgeError.value = 'Together.ai access required. Configure in Settings > API Keys or contact admin for platform access.'
    return
  }

  forgeError.value = ''
  forgeSuccess.value = ''
  try {
    const result = await nursery.startTraining({
      datasetId: forgeDataset.value,
      baseModel: forgeModel.value,
      nEpochs: forgeEpochs.value,
      learningRate: parseFloat(forgeLearningRate.value),
      lora: forgeLora.value,
      batchSize: forgeBatchSize.value ? parseInt(forgeBatchSize.value) : null,
      suffix: forgeSuffix.value || null,
    })
    forgeSuccess.value = result.message || 'Training started!'
    // Reset some fields
    forgeSuffix.value = ''
    forgeBatchSize.value = ''
  } catch (e) {
    forgeError.value = e.response?.data?.detail || e.message || 'Failed to start training.'
  }
}

async function handleCancelJob(jobId) {
  await nursery.cancelJob(jobId)
}

function startJobPolling() {
  stopJobPolling()
  jobPollInterval = setInterval(async () => {
    await nursery.fetchTrainingJobs()
  }, 15000)
}

function stopJobPolling() {
  if (jobPollInterval) {
    clearInterval(jobPollInterval)
    jobPollInterval = null
  }
}

function getModelLabel(modelId) {
  const found = forgeModels.find(m => m.id === modelId)
  return found ? found.label : modelId?.split('/').pop() || modelId
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
onMounted(() => {
  nursery.fetchTrainingJobs()
  if (!nursery.trainableModels.length) nursery.fetchTrainableModels()
  startJobPolling()
})

onUnmounted(() => {
  stopJobPolling()
})
</script>

<template>
  <div>
    <div class="grid lg:grid-cols-2 gap-6">

      <!-- LEFT: New Training Job -->
      <div class="space-y-6">
        <div class="card">
          <h2 class="text-xl font-bold mb-4">New Training Job</h2>

          <!-- No Together access warning -->
          <div v-if="!nursery.hasTogetherAccess" class="mb-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
            <p class="text-amber-400 text-sm font-medium mb-1">Together.ai Access Required</p>
            <p class="text-gray-400 text-xs mb-2">Configure your own key in Settings, or contact admin for platform access.</p>
            <router-link to="/settings" class="text-gold text-xs hover:underline">
              Configure in Settings &rarr;
            </router-link>
          </div>

          <!-- Dataset selector -->
          <div class="mb-4">
            <label class="block text-sm text-gray-400 mb-2">Dataset</label>
            <select
              v-model="forgeDataset"
              class="input w-full"
              @change="handleEstimate"
            >
              <option value="">Select a dataset...</option>
              <option
                v-for="ds in nursery.datasets"
                :key="ds.id"
                :value="ds.id"
              >
                {{ ds.name }} ({{ ds.num_examples }} examples)
              </option>
            </select>
            <div v-if="nursery.datasets.length === 0" class="text-xs text-gray-500 mt-1">
              No datasets yet. Generate one in the Data Garden tab.
            </div>
          </div>

          <!-- Base model selector (MOBILE FIX: grid-cols-1 sm:grid-cols-2) -->
          <div class="mb-4">
            <label class="block text-sm text-gray-400 mb-2">Base Model</label>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <label
                v-for="model in forgeModels"
                :key="model.id"
                class="flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all"
                :class="forgeModel === model.id
                  ? 'bg-gold/20 ring-1 ring-gold'
                  : 'bg-apex-darker hover:bg-white/5'"
              >
                <input
                  type="radio"
                  :value="model.id"
                  v-model="forgeModel"
                  @change="handleEstimate"
                  class="accent-gold"
                />
                <div>
                  <div class="text-sm">{{ model.label }}</div>
                  <div class="text-xs text-gray-500">{{ model.size }} params</div>
                </div>
              </label>
            </div>
          </div>

          <!-- Config section -->
          <div class="mb-4 grid grid-cols-2 gap-4">
            <!-- Epochs -->
            <div>
              <label class="block text-sm text-gray-400 mb-2">
                Epochs: <span class="text-white">{{ forgeEpochs }}</span>
              </label>
              <input
                type="range"
                v-model.number="forgeEpochs"
                min="1"
                max="10"
                @change="handleEstimate"
                class="w-full accent-gold"
              />
              <div class="flex justify-between text-xs text-gray-500">
                <span>1</span>
                <span>10</span>
              </div>
            </div>

            <!-- Learning rate -->
            <div>
              <label class="block text-sm text-gray-400 mb-2">Learning Rate</label>
              <select v-model="forgeLearningRate" class="input w-full">
                <option v-for="lr in learningRates" :key="lr.value" :value="lr.value">
                  {{ lr.label }}
                </option>
              </select>
            </div>
          </div>

          <!-- LoRA toggle -->
          <div class="mb-4 flex items-center gap-3">
            <label class="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                v-model="forgeLora"
                @change="handleEstimate"
                class="accent-gold w-4 h-4"
              />
              <span class="text-sm">LoRA (recommended)</span>
            </label>
            <span class="text-xs text-gray-500">
              {{ forgeLora ? 'Faster, cheaper, memory-efficient' : 'Full fine-tune -- slower, higher quality' }}
            </span>
          </div>

          <!-- Optional: suffix + batch -->
          <div class="mb-4 grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm text-gray-400 mb-2">Suffix (optional)</label>
              <input v-model="forgeSuffix" class="input" placeholder="e.g., v1" />
            </div>
            <div>
              <label class="block text-sm text-gray-400 mb-2">Batch Size</label>
              <select v-model="forgeBatchSize" class="input w-full">
                <option value="">Auto</option>
                <option value="4">4</option>
                <option value="8">8</option>
                <option value="16">16</option>
                <option value="32">32</option>
              </select>
            </div>
          </div>

          <!-- Cost estimate -->
          <div v-if="nursery.costEstimate" class="mb-4 p-3 bg-gold/5 border border-gold/20 rounded-lg">
            <div class="flex justify-between items-center">
              <span class="text-sm text-gray-400">Estimated Cost</span>
              <span class="text-lg font-bold text-gold">
                ${{ nursery.costEstimate.estimated_cost_usd?.toFixed(2) }}
              </span>
            </div>
            <div class="text-xs text-gray-500 mt-1">
              {{ nursery.costEstimate.total_tokens?.toLocaleString() }} tokens
              &middot; ~{{ nursery.costEstimate.estimated_minutes }} min
              &middot; {{ nursery.costEstimate.training_method }}
            </div>
          </div>
          <div v-else-if="nursery.estimating" class="mb-4 text-sm text-gray-400">
            Calculating estimate...
          </div>

          <!-- Error/Success -->
          <div v-if="forgeError" class="mb-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-400 text-sm">
            {{ forgeError }}
          </div>
          <div v-if="forgeSuccess" class="mb-4 p-3 bg-green-500/20 border border-green-500/30 rounded-lg text-green-400 text-sm">
            {{ forgeSuccess }}
          </div>

          <!-- Start Training button -->
          <button
            @click="handleStartTraining"
            :disabled="nursery.startingTraining || !forgeDataset || !nursery.hasTogetherAccess"
            class="btn-primary w-full flex items-center justify-center gap-2"
            :class="{ 'opacity-50 cursor-not-allowed': !forgeDataset || !nursery.hasTogetherAccess }"
          >
            <svg
              v-if="nursery.startingTraining"
              class="animate-spin h-4 w-4"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ nursery.startingTraining ? 'Starting...' : 'Start Training' }}
          </button>
        </div>
      </div>

      <!-- RIGHT: Active Jobs -->
      <div>
        <!-- Job stats (MOBILE FIX: grid-cols-2 sm:grid-cols-3) -->
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-6">
          <div class="card p-4 text-center">
            <div class="text-2xl font-bold text-gold">{{ nursery.trainingJobs.length }}</div>
            <div class="text-sm text-gray-400">Total Jobs</div>
          </div>
          <div class="card p-4 text-center">
            <div class="text-2xl font-bold text-amber-400">{{ nursery.runningJobs }}</div>
            <div class="text-sm text-gray-400">Active</div>
          </div>
          <div class="card p-4 text-center">
            <div class="text-2xl font-bold text-green-400">{{ nursery.completedJobs }}</div>
            <div class="text-sm text-gray-400">Completed</div>
          </div>
        </div>

        <!-- Loading -->
        <div v-if="nursery.loadingJobs" class="text-center py-12 text-gray-400">
          Loading jobs...
        </div>

        <!-- Empty -->
        <div v-else-if="nursery.trainingJobs.length === 0" class="text-center py-12">
          <div class="text-4xl mb-4 text-gray-600">{ }</div>
          <h2 class="text-xl font-bold mb-2">No training jobs yet</h2>
          <p class="text-gray-400">
            Select a dataset and start a training job.
          </p>
        </div>

        <!-- Job cards -->
        <div v-else class="space-y-4">
          <div
            v-for="job in nursery.trainingJobs"
            :key="job.id"
            class="card"
          >
            <!-- Header -->
            <div class="flex items-start justify-between mb-2">
              <div>
                <h3 class="font-medium">{{ job.dataset_name || 'Training Job' }}</h3>
                <div class="text-sm text-gray-400">{{ getModelLabel(job.base_model) }}</div>
              </div>
              <span
                :class="getStatusColor(job.status)"
                class="text-xs px-2 py-0.5 rounded-full capitalize"
              >
                {{ job.status }}
              </span>
            </div>

            <!-- Progress bar (for running jobs) -->
            <div v-if="job.status === 'running' || job.status === 'uploading'" class="mb-3">
              <div class="h-2 bg-apex-darker rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all duration-500"
                  :class="job.status === 'uploading' ? 'bg-blue-500' : 'bg-amber-500'"
                  :style="{ width: `${job.progress || 5}%` }"
                />
              </div>
              <div class="text-xs text-gray-500 mt-1">
                {{ job.progress ? `${Math.round(job.progress)}%` : 'Starting...' }}
              </div>
            </div>

            <!-- Cost -->
            <div v-if="job.cost_estimate" class="text-sm text-gray-400 mb-1">
              Est. ${{ job.cost_estimate?.toFixed(2) }}
              <span v-if="job.cost_actual"> &rarr; Actual: ${{ job.cost_actual?.toFixed(2) }}</span>
            </div>

            <!-- Timestamps -->
            <div class="text-xs text-gray-500">
              Created {{ formatRelativeTime(job.created_at) }}
              <span v-if="job.started_at"> &middot; Started {{ formatRelativeTime(job.started_at) }}</span>
              <span v-if="job.completed_at"> &middot; Done {{ formatRelativeTime(job.completed_at) }}</span>
            </div>

            <!-- Output model name -->
            <div v-if="job.output_name && job.status === 'completed'" class="text-xs text-green-400 mt-1">
              Model: {{ job.output_name }}
            </div>

            <!-- Error message -->
            <div v-if="job.error_message" class="text-xs text-red-400 mt-1">
              {{ job.error_message }}
            </div>

            <!-- Cancel button -->
            <div v-if="job.status === 'pending' || job.status === 'running' || job.status === 'uploading'" class="mt-3">
              <button
                @click="handleCancelJob(job.id)"
                class="text-xs text-red-400 hover:text-red-300 transition-colors"
              >
                Cancel Job
              </button>
            </div>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>
