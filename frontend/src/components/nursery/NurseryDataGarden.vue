<script setup>
/**
 * NurseryDataGarden - Data Garden tab
 * Generate synthetic data and extract from conversations.
 */

import { ref, onMounted } from 'vue'
import { useNurseryStore } from '@/stores/nursery'
import api from '@/services/api'
import { formatRelativeTime, useConfirmDelete } from './nurseryUtils'

const nursery = useNurseryStore()

// Confirm-before-delete composable
const { requestDelete, isConfirming } = useConfirmDelete()

// Generate form state
const selectedTools = ref([])
const numExamples = ref(50)
const variationLevel = ref('medium')
const datasetName = ref('')
const generateError = ref('')

// Extract form state
const extractTools = ref([])
const minExamples = ref(10)
const extractName = ref('')
const extractError = ref('')

// Available tools
const availableTools = ref([])
const loadingTools = ref(false)

// Preview / expand state
const expandedDataset = ref(null)
const previewData = ref(null)
const loadingPreview = ref(false)

// ---------------------------------------------------------------------------
// Fetch available tools from backend
// ---------------------------------------------------------------------------
async function fetchAvailableTools() {
  loadingTools.value = true
  try {
    const response = await api.get('/api/v1/tools')
    if (response.data) {
      availableTools.value = response.data.tools || response.data || []
    }
  } catch (e) {
    console.error('Failed to fetch tools:', e)
    availableTools.value = []
  } finally {
    loadingTools.value = false
  }
}

// ---------------------------------------------------------------------------
// Tool selection helpers
// ---------------------------------------------------------------------------
function toggleTool(toolName, list) {
  const arr = Array.isArray(list) ? list : list.value
  const idx = arr.indexOf(toolName)
  if (idx === -1) {
    arr.push(toolName)
  } else {
    arr.splice(idx, 1)
  }
}

function isToolSelected(toolName, list) {
  const arr = Array.isArray(list) ? list : list.value
  return arr.includes(toolName)
}

function getToolDisplayName(tool) {
  if (typeof tool === 'string') return tool
  return tool.name || tool.tool_name || tool.id || 'unknown'
}

// ---------------------------------------------------------------------------
// Generate synthetic data
// ---------------------------------------------------------------------------
async function handleGenerate() {
  if (selectedTools.value.length === 0) {
    generateError.value = 'Select at least one tool.'
    return
  }

  generateError.value = ''
  try {
    await nursery.generateData(
      selectedTools.value,
      numExamples.value,
      variationLevel.value,
      datasetName.value || null,
    )
    // Reset form on success
    selectedTools.value = []
    numExamples.value = 50
    variationLevel.value = 'medium'
    datasetName.value = ''
  } catch (e) {
    generateError.value = e.response?.data?.detail || e.message || 'Generation failed. Please try again.'
  }
}

// ---------------------------------------------------------------------------
// Extract from conversations
// ---------------------------------------------------------------------------
async function handleExtract() {
  extractError.value = ''
  try {
    await nursery.extractData(
      extractTools.value.length > 0 ? extractTools.value : null,
      minExamples.value,
      extractName.value || null,
    )
    // Reset form on success
    extractTools.value = []
    minExamples.value = 10
    extractName.value = ''
  } catch (e) {
    extractError.value = e.response?.data?.detail || e.message || 'Extraction failed. Please try again.'
  }
}

// ---------------------------------------------------------------------------
// Preview / expand dataset
// ---------------------------------------------------------------------------
async function toggleExpand(dataset) {
  if (expandedDataset.value === dataset.id) {
    expandedDataset.value = null
    previewData.value = null
    return
  }

  expandedDataset.value = dataset.id
  loadingPreview.value = true
  try {
    const response = await api.get(`/api/v1/nursery/datasets/${dataset.id}`)
    previewData.value = response.data
  } catch (e) {
    console.error('Failed to load preview:', e)
    previewData.value = null
  } finally {
    loadingPreview.value = false
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function getSourceColor(source) {
  if (source === 'synthetic') return 'bg-green-500/20 text-green-400'
  if (source === 'extracted') return 'bg-blue-500/20 text-blue-400'
  return 'bg-gray-500/20 text-gray-400'
}

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
onMounted(() => {
  fetchAvailableTools()
})
</script>

<template>
  <div>
    <div class="grid lg:grid-cols-2 gap-6">

      <!-- LEFT SECTION: Generate & Extract -->
      <div class="space-y-6">

        <!-- Generate Card -->
        <div class="card">
          <h2 class="text-xl font-bold mb-4">Generate Synthetic Data</h2>

          <!-- Tool multi-select -->
          <div class="mb-4">
            <label class="block text-sm text-gray-400 mb-2">Tools</label>
            <div v-if="loadingTools" class="text-sm text-gray-500 py-2">
              Loading tools...
            </div>
            <div v-else-if="availableTools.length === 0" class="text-sm text-gray-500 py-2">
              No tools available
            </div>
            <div v-else class="max-h-48 overflow-y-auto border border-apex-border rounded-lg p-3 bg-apex-darker space-y-2">
              <label
                v-for="tool in availableTools"
                :key="getToolDisplayName(tool)"
                class="flex items-center gap-2 cursor-pointer hover:bg-white/5 rounded px-2 py-1 transition-colors"
              >
                <input
                  type="checkbox"
                  :checked="isToolSelected(getToolDisplayName(tool), selectedTools)"
                  @change="toggleTool(getToolDisplayName(tool), selectedTools)"
                  class="accent-gold w-4 h-4"
                />
                <span class="text-sm text-gray-300">{{ getToolDisplayName(tool) }}</span>
              </label>
            </div>
            <div v-if="selectedTools.length > 0" class="text-xs text-gray-500 mt-1">
              {{ selectedTools.length }} tool{{ selectedTools.length !== 1 ? 's' : '' }} selected
            </div>
          </div>

          <!-- Examples slider -->
          <div class="mb-4">
            <label class="block text-sm text-gray-400 mb-2">
              Examples: <span class="text-white font-medium">{{ numExamples }}</span>
            </label>
            <input
              type="range"
              v-model.number="numExamples"
              min="10"
              max="500"
              step="10"
              class="w-full accent-gold"
            />
            <div class="flex justify-between text-xs text-gray-500 mt-1">
              <span>10</span>
              <span>500</span>
            </div>
          </div>

          <!-- Variation radio buttons -->
          <div class="mb-4">
            <label class="block text-sm text-gray-400 mb-2">Variation</label>
            <div class="flex gap-3">
              <label
                v-for="level in ['low', 'medium', 'high']"
                :key="level"
                class="flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all"
                :class="variationLevel === level
                  ? 'bg-gold/20 ring-1 ring-gold'
                  : 'bg-apex-darker hover:bg-white/5'"
              >
                <input
                  type="radio"
                  :value="level"
                  v-model="variationLevel"
                  class="accent-gold"
                />
                <span class="text-sm capitalize">{{ level }}</span>
              </label>
            </div>
          </div>

          <!-- Dataset name -->
          <div class="mb-4">
            <label class="block text-sm text-gray-400 mb-2">Dataset Name (optional)</label>
            <input
              v-model="datasetName"
              type="text"
              class="input"
              placeholder="e.g., web-tools-v1"
            />
          </div>

          <!-- Generate error -->
          <div
            v-if="generateError"
            class="mb-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-400 text-sm"
          >
            {{ generateError }}
          </div>

          <!-- Generate button -->
          <button
            @click="handleGenerate"
            :disabled="nursery.generating || selectedTools.length === 0"
            class="btn-primary w-full flex items-center justify-center gap-2"
          >
            <svg
              v-if="nursery.generating"
              class="animate-spin h-4 w-4"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ nursery.generating ? 'Generating...' : 'Generate' }}
          </button>
        </div>

        <!-- Extract Card -->
        <div class="card">
          <h2 class="text-xl font-bold mb-4">Extract from Conversations</h2>

          <!-- Tool filter (optional) -->
          <div class="mb-4">
            <label class="block text-sm text-gray-400 mb-2">Tool Filter (optional)</label>
            <div v-if="loadingTools" class="text-sm text-gray-500 py-2">
              Loading tools...
            </div>
            <div v-else-if="availableTools.length === 0" class="text-sm text-gray-500 py-2">
              No tools available
            </div>
            <div v-else class="max-h-36 overflow-y-auto border border-apex-border rounded-lg p-3 bg-apex-darker space-y-2">
              <label
                v-for="tool in availableTools"
                :key="'ext-' + getToolDisplayName(tool)"
                class="flex items-center gap-2 cursor-pointer hover:bg-white/5 rounded px-2 py-1 transition-colors"
              >
                <input
                  type="checkbox"
                  :checked="isToolSelected(getToolDisplayName(tool), extractTools)"
                  @change="toggleTool(getToolDisplayName(tool), extractTools)"
                  class="accent-gold w-4 h-4"
                />
                <span class="text-sm text-gray-300">{{ getToolDisplayName(tool) }}</span>
              </label>
            </div>
            <div v-if="extractTools.length > 0" class="text-xs text-gray-500 mt-1">
              {{ extractTools.length }} tool{{ extractTools.length !== 1 ? 's' : '' }} selected
            </div>
          </div>

          <!-- Min examples -->
          <div class="mb-4">
            <label class="block text-sm text-gray-400 mb-2">Min Examples</label>
            <input
              v-model.number="minExamples"
              type="number"
              min="1"
              max="1000"
              class="input"
              placeholder="10"
            />
          </div>

          <!-- Dataset name -->
          <div class="mb-4">
            <label class="block text-sm text-gray-400 mb-2">Dataset Name (optional)</label>
            <input
              v-model="extractName"
              type="text"
              class="input"
              placeholder="e.g., conversation-extract-01"
            />
          </div>

          <!-- Extract error -->
          <div
            v-if="extractError"
            class="mb-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-400 text-sm"
          >
            {{ extractError }}
          </div>

          <!-- Extract button -->
          <button
            @click="handleExtract"
            :disabled="nursery.extracting"
            class="btn-primary w-full flex items-center justify-center gap-2"
          >
            <svg
              v-if="nursery.extracting"
              class="animate-spin h-4 w-4"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ nursery.extracting ? 'Extracting...' : 'Extract' }}
          </button>
        </div>
      </div>

      <!-- RIGHT SECTION: Dataset List -->
      <div>
        <!-- Stats Bar -->
        <div class="grid grid-cols-2 gap-4 mb-6">
          <div class="card p-4 text-center">
            <div class="text-2xl font-bold text-gold">{{ nursery.totalDatasets }}</div>
            <div class="text-sm text-gray-400">Datasets</div>
          </div>
          <div class="card p-4 text-center">
            <div class="text-2xl font-bold text-gold">{{ nursery.totalExamples.toLocaleString() }}</div>
            <div class="text-sm text-gray-400">Total Examples</div>
          </div>
        </div>

        <!-- Loading State -->
        <div v-if="nursery.loading" class="text-center py-12 text-gray-400">
          Loading datasets...
        </div>

        <!-- Empty State -->
        <div v-else-if="nursery.datasets.length === 0" class="text-center py-12">
          <div class="text-4xl mb-4 text-gray-600">{ }</div>
          <h2 class="text-xl font-bold mb-2">No datasets yet</h2>
          <p class="text-gray-400">
            Generate or extract training data to get started.
          </p>
        </div>

        <!-- Dataset Cards -->
        <div v-else class="space-y-4">
          <div
            v-for="dataset in nursery.datasets"
            :key="dataset.id"
            class="card hover:border-gold/30 transition-colors cursor-pointer"
            @click="toggleExpand(dataset)"
          >
            <!-- Header row -->
            <div class="flex items-start justify-between mb-2">
              <div class="flex items-center gap-2 min-w-0">
                <h3 class="font-medium truncate">{{ dataset.name || 'Untitled Dataset' }}</h3>
                <span
                  :class="getSourceColor(dataset.source)"
                  class="text-xs px-2 py-0.5 rounded-full whitespace-nowrap"
                >
                  {{ dataset.source || 'unknown' }}
                </span>
              </div>

              <!-- Delete button -->
              <button
                @click.stop="requestDelete(dataset.id, (id) => { nursery.deleteDataset(id); expandedDataset = null; previewData = null })"
                class="ml-2 px-2 py-1 rounded text-sm transition-colors flex-shrink-0"
                :class="isConfirming(dataset.id)
                  ? 'bg-red-500/30 text-red-300'
                  : 'text-gray-500 hover:text-red-400 hover:bg-red-500/20'"
              >
                {{ isConfirming(dataset.id) ? 'Confirm?' : 'Delete' }}
              </button>
            </div>

            <!-- Tool tags -->
            <div v-if="dataset.tool_names?.length" class="flex flex-wrap gap-1 mb-2">
              <span
                v-for="tool in dataset.tool_names"
                :key="tool"
                class="text-xs bg-gold/10 text-gold px-2 py-0.5 rounded"
              >
                {{ tool }}
              </span>
            </div>

            <!-- Stats line -->
            <div class="text-sm text-gray-400">
              {{ dataset.num_examples || 0 }} examples
              <span v-if="dataset.size_bytes"> &middot; {{ formatSize(dataset.size_bytes) }}</span>
            </div>

            <!-- Created date -->
            <div class="text-xs text-gray-500 mt-1">
              {{ formatRelativeTime(dataset.created_at) }}
            </div>

            <!-- Expanded Preview -->
            <div
              v-if="expandedDataset === dataset.id"
              class="mt-4 pt-4 border-t border-apex-border"
              @click.stop
            >
              <div v-if="loadingPreview" class="text-sm text-gray-400 py-2">
                Loading preview...
              </div>
              <div v-else-if="previewData?.examples?.length" class="space-y-2">
                <div class="text-xs text-gray-500 mb-2">
                  Preview (first {{ Math.min(previewData.examples.length, 5) }} examples)
                </div>
                <div
                  v-for="(example, idx) in previewData.examples.slice(0, 5)"
                  :key="idx"
                  class="bg-apex-darker rounded p-3 text-sm"
                >
                  <div v-if="example.input" class="mb-1">
                    <span class="text-gray-500">Input:</span>
                    <span class="text-gray-300 ml-1">{{ example.input }}</span>
                  </div>
                  <div v-if="example.output">
                    <span class="text-gray-500">Output:</span>
                    <span class="text-gray-300 ml-1">{{ example.output }}</span>
                  </div>
                  <div v-if="example.tool_name" class="text-xs text-gold/60 mt-1">
                    Tool: {{ example.tool_name }}
                  </div>
                </div>
              </div>
              <div v-else class="text-sm text-gray-500 py-2">
                No preview data available.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
