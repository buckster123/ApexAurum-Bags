<script setup>
import { ref, onMounted, computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useBillingStore } from '@/stores/billing'
import { useDevMode } from '@/composables/useDevMode'
import { useSound } from '@/composables/useSound'
import { useHaptic } from '@/composables/useHaptic'
import api from '@/services/api'
import { useToast } from '@/composables/useToast'

const auth = useAuthStore()
const { showToast } = useToast()
const chatStore = useChatStore()
const billing = useBillingStore()

// Tools (The Athanor's Hands)
const toolsEnabled = ref(chatStore.toolsEnabled)
const availableTools = ref([])
const toolsCount = ref(0)
const loadingTools = ref(false)
const showToolsList = ref(false)

function toggleTools() {
  chatStore.setToolsEnabled(toolsEnabled.value)
}

async function fetchTools() {
  loadingTools.value = true
  try {
    const response = await api.get('/api/v1/tools')
    availableTools.value = response.data.tools || []
    toolsCount.value = response.data.count || 0
  } catch (e) {
    console.error('Failed to fetch tools:', e)
  } finally {
    loadingTools.value = false
  }
}

// Group tools by category
const toolsByCategory = computed(() => {
  const grouped = {}
  for (const tool of availableTools.value) {
    const cat = tool.category || 'other'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(tool)
  }
  return grouped
})

const categoryLabels = {
  utility: '🔧 Utilities',
  web: '🌐 Web',
  files: '📁 Vault',
  memory: '🧠 Memory',
  knowledge: '📚 Knowledge',
  agent: '🤖 Agents',
  music: '🎵 Music',
  browser: '🖥️ Browser',
}
const { devMode, pacMode, handleTap, tapCount, alchemyLayer, layerName, tierRestrictionMessage, enableDevMode } = useDevMode()
const { soundEnabled, toggleSound, sounds } = useSound()
const { hapticEnabled, setEnabled: setHapticEnabled, haptics, isSupported: hapticSupported } = useHaptic()

// Active tab for dev mode
const activeTab = ref('profile')
const devTabs = ['profile', 'agents', 'memory', 'import', 'advanced', 'api']

// Import state
const importing = ref(false)
const importResult = ref({ conversations: null, memory: null })

// Profile
const displayName = ref('')
const loading = ref(false)
const saved = ref(false)

// Preferences
const preferences = ref({
  default_model: 'claude-sonnet-4-5-20250929',
  cache_strategy: 'balanced',
  context_strategy: 'adaptive',
  theme: 'dark',
  default_agent: 'AZOTH',
  streaming: true,
  max_tokens: 8192,
  temperature: 0.7,
})

// Usage stats
const usage = ref(null)

// Native agents (from API)
const nativeAgents = ref([])
const loadingAgents = ref(false)

// Custom agents
const customAgents = ref([])

// Agent editor modal
const showAgentEditor = ref(false)
const editingAgent = ref(null)
const viewingPrompt = ref(null)
const showPromptViewer = ref(false)

// PAC Mode - Perfected Stones
const showCodexViewer = ref(false)
const viewingCodex = ref(null)

// Multi-Provider API Key Management
const providerKeys = ref({})
const activeProvider = ref(null)
const newProviderKey = ref('')
const savingProvider = ref(null)
const providerError = ref('')
const providerSuccess = ref('')

// Memory (The Cortex)
const memoryStats = ref({ by_agent: {}, total: 0 })
const agentMemories = ref([])
const loadingMemory = ref(false)
const selectedMemoryAgent = ref(null)
const memoryEnabled = ref(true)
const memoryExtractionMode = ref('manual')

// Computed: Agents that have PAC versions
const pacAgents = computed(() => nativeAgents.value.filter(a => a.has_pac))

const models = [
  { id: 'claude-haiku-4-5-20251001', name: '◇ Haiku 4.5 (Fast)', tier: 'haiku' },
  { id: 'claude-sonnet-4-5-20250929', name: '✦ Sonnet 4.5 (Balanced)', tier: 'sonnet' },
  { id: 'claude-opus-4-5-20251101', name: '⚜️ Opus 4.5 (Powerful)', tier: 'opus' },
]

const cacheStrategies = [
  { id: 'disabled', name: 'Disabled' },
  { id: 'conservative', name: 'Conservative' },
  { id: 'balanced', name: 'Balanced' },
  { id: 'aggressive', name: 'Aggressive' },
]

const contextStrategies = [
  { id: 'disabled', name: 'Disabled' },
  { id: 'balanced', name: 'Balanced' },
  { id: 'adaptive', name: 'Adaptive' },
  { id: 'aggressive', name: 'Aggressive' },
  { id: 'rolling', name: 'Rolling' },
]

const agents = ['AZOTH', 'ELYSIAN', 'VAJRA', 'KETHER']

// Computed
const tapProgress = computed(() => Math.min(tapCount.value / 7 * 100, 100))

// Computed: BYOK allowed for this tier (Adept and above)
const canUseBYOK = computed(() => billing.status?.features?.byok_allowed || false)

// Computed: Dev mode allowed for this tier (Opus and Azothic)
const canUseDevMode = computed(() => billing.tierLevel >= 3)

onMounted(async () => {
  displayName.value = auth.user?.display_name || ''
  await billing.fetchStatus() // Fetch tier info first
  await fetchPreferences()
  await fetchUsage()
  await fetchProviderKeys()
  await fetchTools()

  if (devMode.value) {
    await fetchNativeAgents()
    await fetchCustomAgents()
  }
})

async function fetchPreferences() {
  try {
    const response = await api.get('/api/v1/user/preferences')
    preferences.value = { ...preferences.value, ...response.data }
  } catch (e) {
    console.error('Failed to fetch preferences:', e)
  }
}

async function fetchUsage() {
  try {
    const response = await api.get('/api/v1/user/usage')
    usage.value = response.data
  } catch (e) {
    console.error('Failed to fetch usage:', e)
  }
}

// Multi-Provider API Key Management
async function fetchProviderKeys() {
  try {
    const response = await api.get('/api/v1/user/api-key/status')
    providerKeys.value = response.data.providers || {}
  } catch (e) {
    console.error('Failed to fetch provider keys:', e)
  }
}

async function saveProviderKey(providerId) {
  if (!newProviderKey.value.trim()) return

  savingProvider.value = providerId
  providerError.value = ''
  providerSuccess.value = ''

  try {
    const response = await api.post('/api/v1/user/api-key', {
      api_key: newProviderKey.value.trim(),
      provider: providerId,
    })
    newProviderKey.value = ''
    activeProvider.value = null
    providerSuccess.value = response.data.message || 'Key saved!'
    showToast(providerSuccess.value, 'success')
    setTimeout(() => providerSuccess.value = '', 3000)
    await fetchProviderKeys()
  } catch (e) {
    providerError.value = e.response?.data?.detail || 'Failed to save key'
    showToast(providerError.value, 'error')
  } finally {
    savingProvider.value = null
  }
}

async function removeProviderKey(providerId) {
  const providerName = providerKeys.value[providerId]?.provider_name || providerId
  if (!confirm(`Remove your ${providerName} API key?`)) return

  try {
    await api.delete(`/api/v1/user/api-key/${providerId}`)
    showToast(`${providerName} key removed`, 'success')
    await fetchProviderKeys()
  } catch (e) {
    showToast('Failed to remove key', 'error')
  }
}

function toggleProvider(providerId) {
  if (activeProvider.value === providerId) {
    activeProvider.value = null
  } else {
    activeProvider.value = providerId
    newProviderKey.value = ''
    providerError.value = ''
  }
}

function canConfigureProvider(providerId) {
  // Opus+ can configure all providers, Adept can configure OSS providers
  if (billing.tierLevel >= 3) return true
  if (billing.tierLevel >= 2 && providerId !== 'anthropic') return true
  return false
}

async function fetchNativeAgents() {
  loadingAgents.value = true
  try {
    const response = await api.get('/api/v1/prompts/native')
    nativeAgents.value = response.data?.agents || []
  } catch (e) {
    console.error('Failed to fetch native agents:', e)
  } finally {
    loadingAgents.value = false
  }
}

async function fetchCustomAgents() {
  try {
    const response = await api.get('/api/v1/prompts/custom')
    customAgents.value = response.data?.agents || []
  } catch (e) {
    console.error('Failed to fetch custom agents:', e)
  }
}

async function saveProfile() {
  loading.value = true
  saved.value = false
  try {
    await api.put('/api/v1/user/profile', {
      display_name: displayName.value
    })
    auth.user.display_name = displayName.value
    saved.value = true
    setTimeout(() => saved.value = false, 3000)
  } catch (e) {
    console.error('Failed to save profile:', e)
    showToast('Failed to save profile. Please try again.')
  } finally {
    loading.value = false
  }
}

async function savePreferences() {
  loading.value = true
  saved.value = false
  try {
    await api.put('/api/v1/user/preferences', preferences.value)
    saved.value = true
    setTimeout(() => saved.value = false, 3000)
  } catch (e) {
    console.error('Failed to save preferences:', e)
    showToast('Failed to save preferences. Please try again.')
  } finally {
    loading.value = false
  }
}

async function viewNativePrompt(agentId) {
  try {
    const response = await api.get(`/api/v1/prompts/native/${agentId}`)
    viewingPrompt.value = response.data
    showPromptViewer.value = true
  } catch (e) {
    console.error('Failed to load prompt:', e)
  }
}

// View PAC Codex (The Perfected Stone's true form)
async function viewCodex(agentId) {
  try {
    const response = await api.get(`/api/v1/prompts/native/${agentId}?prompt_type=pac`)
    viewingCodex.value = response.data
    showCodexViewer.value = true
  } catch (e) {
    console.error('Failed to load codex:', e)
  }
}

async function copyToCustom(agent) {
  try {
    const response = await api.get(`/api/v1/prompts/native/${agent.id}`)
    editingAgent.value = {
      id: null, // Will generate new ID
      name: `${response.data.name} (Copy)`,
      symbol: response.data.symbol,
      color: response.data.color,
      prompt: response.data.prompt,
      type: response.data.type,
    }
    showAgentEditor.value = true
  } catch (e) {
    console.error('Failed to copy prompt:', e)
  }
}

function createNewAgent() {
  editingAgent.value = {
    id: null,
    name: 'New Agent',
    symbol: '+',
    color: '#888888',
    prompt: 'You are a helpful AI assistant.',
    type: 'prose',
  }
  showAgentEditor.value = true
}

function editCustomAgent(agent) {
  editingAgent.value = { ...agent }
  showAgentEditor.value = true
}

async function saveAgent() {
  try {
    await api.post('/api/v1/prompts/custom', editingAgent.value)
    await fetchCustomAgents()
    showAgentEditor.value = false
    editingAgent.value = null
  } catch (e) {
    console.error('Failed to save agent:', e)
    showToast('Failed to save agent. Please try again.')
  }
}

async function deleteCustomAgent(agentId) {
  if (!confirm('Delete this custom agent?')) return

  try {
    await api.delete(`/api/v1/prompts/custom/${agentId}`)
    await fetchCustomAgents()
  } catch (e) {
    console.error('Failed to delete agent:', e)
    showToast('Failed to delete agent. Please try again.')
  }
}

function formatCost(cost) {
  return `$${cost.toFixed(4)}`
}

// Tab switching triggers data loading
async function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'agents' && nativeAgents.value.length === 0) {
    await fetchNativeAgents()
    await fetchCustomAgents()
  }
}

// Import handlers
async function handleConversationsImport(event) {
  const file = event.target.files[0]
  if (!file) return

  importing.value = true
  importResult.value.conversations = null

  try {
    const formData = new FormData()
    formData.append('file', file)

    const response = await api.post('/api/v1/import/conversations', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    importResult.value.conversations = `Imported ${response.data.imported} conversations`
    if (response.data.skipped > 0) {
      importResult.value.conversations += ` (${response.data.skipped} skipped)`
    }
  } catch (e) {
    importResult.value.conversations = `Error: ${e.response?.data?.detail || e.message}`
  } finally {
    importing.value = false
    event.target.value = '' // Reset file input
  }
}

async function handleMemoryImport(event) {
  const file = event.target.files[0]
  if (!file) return

  importing.value = true
  importResult.value.memory = null

  try {
    const formData = new FormData()
    formData.append('file', file)

    const response = await api.post('/api/v1/import/memory', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    importResult.value.memory = `Imported ${response.data.imported} memory entries`
    if (response.data.skipped > 0) {
      importResult.value.memory += ` (${response.data.skipped} skipped)`
    }
  } catch (e) {
    importResult.value.memory = `Error: ${e.response?.data?.detail || e.message}`
  } finally {
    importing.value = false
    event.target.value = '' // Reset file input
  }
}

// Memory (The Cortex) functions
async function fetchMemoryStats() {
  loadingMemory.value = true
  try {
    const response = await api.get('/api/v1/memory/stats')
    memoryStats.value = response.data
  } catch (e) {
    console.error('Failed to fetch memory stats:', e)
  } finally {
    loadingMemory.value = false
  }
}

async function fetchAgentMemories(agentId) {
  loadingMemory.value = true
  try {
    const response = await api.get(`/api/v1/memory/${agentId}`)
    agentMemories.value = response.data.memories
    selectedMemoryAgent.value = agentId
  } catch (e) {
    console.error('Failed to fetch agent memories:', e)
    agentMemories.value = []
  } finally {
    loadingMemory.value = false
  }
}

async function deleteMemory(agentId, memoryId) {
  if (!confirm('Delete this memory?')) return
  try {
    await api.delete(`/api/v1/memory/${agentId}/${memoryId}`)
    agentMemories.value = agentMemories.value.filter(m => m.id !== memoryId)
    if (memoryStats.value.by_agent[agentId]) {
      memoryStats.value.by_agent[agentId]--
      memoryStats.value.total--
    }
  } catch (e) {
    console.error('Failed to delete memory:', e)
  }
}

async function clearAgentMemories(agentId) {
  if (!confirm(`Clear ALL memories for ${agentId}? This cannot be undone.`)) return
  try {
    await api.delete(`/api/v1/memory/${agentId}`)
    agentMemories.value = []
    delete memoryStats.value.by_agent[agentId]
    selectedMemoryAgent.value = null
    await fetchMemoryStats()
  } catch (e) {
    console.error('Failed to clear agent memories:', e)
  }
}

async function exportAllMemories() {
  try {
    const response = await api.get('/api/v1/memory/export/all', { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `apexaurum-memories-${new Date().toISOString().split('T')[0]}.json`)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (e) {
    console.error('Failed to export memories:', e)
  }
}

async function clearAllMemories() {
  if (!confirm('Clear ALL memories for ALL agents? This cannot be undone.')) return
  if (!confirm('Are you REALLY sure? This is permanent amnesia.')) return

  try {
    await api.delete('/api/v1/memory/?confirm=true')
    memoryStats.value = { by_agent: {}, total: 0 }
    agentMemories.value = []
    selectedMemoryAgent.value = null
  } catch (e) {
    console.error('Failed to clear all memories:', e)
  }
}

async function toggleMemoryEnabled() {
  memoryEnabled.value = !memoryEnabled.value
  preferences.value.memory_enabled = memoryEnabled.value
  await savePreferences()
}

function getAgentSymbol(agentId) {
  if (agentId.includes('AZOTH')) return '∴'
  if (agentId.includes('ELYSIAN')) return '☽'
  if (agentId.includes('VAJRA')) return '⚡'
  if (agentId.includes('KETHER')) return '☀'
  return '🤖'
}
</script>

<template>
  <div class="max-w-4xl mx-auto px-4 py-8">
    <!-- Header with Au logo (tap target) -->
    <div class="flex items-center justify-between mb-8">
      <h1 class="text-3xl font-bold">Settings</h1>

      <div class="flex items-center gap-3">
        <!-- Layer Badges -->
        <span
          v-if="pacMode"
          class="pac-badge px-3 py-1 text-xs font-bold rounded"
        >
          THE ADEPT
        </span>
        <span
          v-else-if="devMode"
          class="px-2 py-1 text-xs font-bold bg-gold/20 text-gold rounded"
        >
          DEV
        </span>

        <!-- Au Logo - tap target for easter egg -->
        <button
          @click="handleTap"
          class="relative w-12 h-12 rounded-full bg-gradient-to-br from-gold to-gold-dim flex items-center justify-center font-serif font-bold text-xl text-apex-dark hover:scale-105 transition-transform"
          title="ApexAurum"
        >
          Au
          <!-- Tap progress indicator -->
          <svg
            v-if="tapCount > 0 && !devMode"
            class="absolute inset-0 w-12 h-12 -rotate-90"
          >
            <circle
              cx="24" cy="24" r="22"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-dasharray="138.2"
              :stroke-dashoffset="138.2 - (tapProgress / 100 * 138.2)"
              class="text-white/50"
            />
          </svg>
        </button>
      </div>
    </div>

    <!-- Success message -->
    <div
      v-if="saved"
      class="mb-6 p-3 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400 text-sm"
    >
      Settings saved successfully!
    </div>

    <!-- Tier restriction message (when non-Adept tries dev mode) -->
    <div
      v-if="tierRestrictionMessage"
      class="mb-6 p-3 bg-gold/10 border border-gold/30 rounded-lg text-gold text-sm flex items-center gap-2"
    >
      <span class="text-lg">🔒</span>
      {{ tierRestrictionMessage }}
    </div>

    <!-- Dev Mode: Tab Navigation (scrollable on mobile) -->
    <div v-if="devMode" class="flex gap-2 mb-6 border-b border-apex-border overflow-x-auto scrollbar-hide pb-px -mb-px">
      <button
        v-for="tab in devTabs"
        :key="tab"
        @click="switchTab(tab)"
        class="px-4 py-3 text-sm font-medium transition-colors capitalize whitespace-nowrap flex-shrink-0"
        :class="activeTab === tab
          ? 'text-gold border-b-2 border-gold'
          : 'text-gray-400 hover:text-white'"
      >
        {{ tab }}
      </button>
    </div>

    <!-- PROFILE TAB (shown in both modes) -->
    <template v-if="activeTab === 'profile' || !devMode">
      <!-- Profile Section -->
      <div class="card mb-6">
        <h2 class="text-xl font-bold mb-4">Profile</h2>

        <div class="space-y-4">
          <div>
            <label class="block text-sm text-gray-400 mb-2">Email</label>
            <input
              type="email"
              :value="auth.user?.email"
              disabled
              class="input bg-apex-darker cursor-not-allowed"
            />
          </div>

          <div>
            <label class="block text-sm text-gray-400 mb-2">Display Name</label>
            <input
              v-model="displayName"
              type="text"
              class="input"
              placeholder="How should we call you?"
            />
          </div>

          <button
            @click="saveProfile"
            class="btn-primary"
            :disabled="loading"
          >
            {{ loading ? 'Saving...' : 'Save Profile' }}
          </button>
        </div>
      </div>

      <!-- Preferences Section (Standard Mode shows simplified) -->
      <div class="card mb-6">
        <h2 class="text-xl font-bold mb-4">Preferences</h2>

        <div class="space-y-4">
          <div>
            <label class="block text-sm text-gray-400 mb-2">Default Agent</label>
            <select v-model="preferences.default_agent" class="input">
              <option v-for="agent in agents" :key="agent" :value="agent">
                {{ agent }}
              </option>
            </select>
          </div>

          <div>
            <label class="block text-sm text-gray-400 mb-2">Theme</label>
            <select v-model="preferences.theme" class="input">
              <option value="dark">Dark</option>
              <option value="light" disabled>Light (Coming Soon)</option>
            </select>
          </div>

          <div class="flex items-center gap-3">
            <input
              type="checkbox"
              id="streaming"
              v-model="preferences.streaming"
              class="w-4 h-4 rounded border-gray-600 text-gold focus:ring-gold"
            />
            <label for="streaming" class="text-sm text-gray-300">
              Enable streaming responses
            </label>
          </div>

          <!-- Tools (The Athanor's Hands) -->
          <div class="border border-apex-border rounded-lg p-4 space-y-3">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="tools"
                  v-model="toolsEnabled"
                  @change="toggleTools"
                  class="w-4 h-4 rounded border-gray-600 text-gold focus:ring-gold"
                />
                <label for="tools" class="text-sm text-gray-300">
                  Enable tool calling
                </label>
              </div>
              <span class="text-xs px-2 py-1 rounded bg-gold/20 text-gold">
                {{ toolsCount }} tools
              </span>
            </div>

            <button
              @click="showToolsList = !showToolsList"
              class="text-xs text-gray-400 hover:text-gold flex items-center gap-1"
            >
              <span>{{ showToolsList ? 'Hide' : 'Show' }} available tools</span>
              <svg
                class="w-3 h-3 transition-transform"
                :class="{ 'rotate-180': showToolsList }"
                fill="none" stroke="currentColor" viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            <div v-if="showToolsList" class="space-y-3 pt-2 border-t border-apex-border">
              <div v-if="loadingTools" class="text-sm text-gray-500">Loading tools...</div>
              <div v-else v-for="(tools, category) in toolsByCategory" :key="category" class="space-y-1">
                <div class="text-xs font-medium text-gold/80">
                  {{ categoryLabels[category] || category }}
                </div>
                <div class="grid grid-cols-2 gap-1">
                  <div
                    v-for="tool in tools"
                    :key="tool.name"
                    class="text-xs text-gray-400 px-2 py-1 bg-apex-bg rounded truncate"
                    :title="tool.description"
                  >
                    {{ tool.name }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <button
            @click="savePreferences"
            class="btn-primary"
            :disabled="loading"
          >
            {{ loading ? 'Saving...' : 'Save Preferences' }}
          </button>
        </div>
      </div>

      <!-- Dev Mode Toggle (Adept tier only) -->
      <div v-if="canUseDevMode && !devMode" class="card mb-6">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="font-medium text-gold">Developer Mode</h3>
            <p class="text-sm text-gray-400 mt-1">
              Access advanced settings, custom agents, and memory management.
            </p>
          </div>
          <button
            @click="enableDevMode()"
            class="px-4 py-2 rounded-lg text-sm font-medium bg-gold/10 border border-gold/30 text-gold hover:bg-gold/20 transition-colors"
          >
            Enable
          </button>
        </div>
      </div>

      <!-- Usage Statistics (Standard Mode) -->
      <div v-if="!devMode" class="card">
        <h2 class="text-xl font-bold mb-4">Usage Statistics</h2>

        <div v-if="usage" class="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div class="bg-apex-darker rounded-lg p-4">
            <div class="text-2xl font-bold text-gold">{{ usage.total_messages }}</div>
            <div class="text-sm text-gray-400">Messages</div>
          </div>

          <div class="bg-apex-darker rounded-lg p-4">
            <div class="text-2xl font-bold text-gold">{{ usage.conversations_count }}</div>
            <div class="text-sm text-gray-400">Conversations</div>
          </div>

          <div class="bg-apex-darker rounded-lg p-4">
            <div class="text-2xl font-bold text-gold">{{ usage.agents_spawned }}</div>
            <div class="text-sm text-gray-400">Agents Spawned</div>
          </div>
        </div>

        <div v-else class="text-center py-8 text-gray-400">
          Loading usage statistics...
        </div>
      </div>
    </template>

    <!-- AGENTS TAB (Dev Mode only) -->
    <template v-if="devMode && activeTab === 'agents'">
      <div class="card mb-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-xl font-bold">Native Agents</h2>
        </div>

        <div v-if="loadingAgents" class="text-center py-8 text-gray-400">
          Loading agents...
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="agent in nativeAgents"
            :key="agent.id"
            class="flex items-center justify-between p-3 bg-apex-darker rounded-lg"
          >
            <div class="flex items-center gap-3">
              <div
                class="w-8 h-8 rounded-full flex items-center justify-center font-bold"
                :style="{ backgroundColor: agent.color + '20', color: agent.color }"
              >
                {{ agent.symbol }}
              </div>
              <div>
                <div class="font-medium">{{ agent.name }}</div>
                <div class="text-xs text-gray-500">
                  {{ agent.has_pac ? 'Prose + PAC' : 'Prose' }}
                </div>
              </div>
            </div>

            <div class="flex gap-2">
              <button
                @click="viewNativePrompt(agent.id)"
                class="btn-secondary text-xs px-3 py-1"
                :disabled="!agent.has_prompt"
              >
                View
              </button>
              <button
                @click="copyToCustom(agent)"
                class="btn-secondary text-xs px-3 py-1"
                :disabled="!agent.has_prompt"
              >
                Edit Copy
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-xl font-bold">Custom Agents</h2>
          <button @click="createNewAgent" class="btn-primary text-sm">
            + Create New Agent
          </button>
        </div>

        <div v-if="customAgents.length === 0" class="text-center py-8 text-gray-400">
          No custom agents yet. Create one to get started!
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="agent in customAgents"
            :key="agent.id"
            class="flex items-center justify-between p-3 bg-apex-darker rounded-lg"
          >
            <div class="flex items-center gap-3">
              <div
                class="w-8 h-8 rounded-full flex items-center justify-center font-bold"
                :style="{ backgroundColor: agent.color + '20', color: agent.color }"
              >
                {{ agent.symbol }}
              </div>
              <div>
                <div class="font-medium">{{ agent.name }}</div>
                <div class="text-xs text-gray-500">{{ agent.id }}</div>
              </div>
            </div>

            <div class="flex gap-2">
              <button
                @click="editCustomAgent(agent)"
                class="btn-secondary text-xs px-3 py-1"
              >
                Edit
              </button>
              <button
                @click="deleteCustomAgent(agent.id)"
                class="text-red-400 hover:text-red-300 text-xs px-3 py-1"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- PERFECTED STONES (PAC Mode only) -->
      <div v-if="pacMode" class="card mt-6 pac-message">
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center gap-3">
            <span class="text-2xl">⚗</span>
            <div>
              <h2 class="text-xl font-bold text-gold" style="text-shadow: 0 0 20px rgba(255, 215, 0, 0.3);">
                The Perfected Stones
              </h2>
              <p class="text-xs text-purple-300/70">Hyperdense codices for the Adept</p>
            </div>
          </div>
          <span class="pac-badge px-3 py-1 rounded-full text-xs font-bold">
            LAYER {{ alchemyLayer }}
          </span>
        </div>

        <div v-if="pacAgents.length === 0" class="text-center py-8 text-purple-300/50">
          No perfected stones found in this realm...
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="agent in pacAgents"
            :key="agent.id + '-pac'"
            class="flex items-center justify-between p-4 rounded-lg agent-halo"
            :style="{
              backgroundColor: 'rgba(26, 10, 46, 0.8)',
              border: '1px solid rgba(255, 215, 0, 0.2)',
              color: agent.color
            }"
          >
            <div class="flex items-center gap-4">
              <div
                class="w-12 h-12 rounded-full flex items-center justify-center font-bold text-xl"
                :style="{
                  backgroundColor: agent.color + '15',
                  color: agent.color,
                  boxShadow: `0 0 20px ${agent.color}40`
                }"
              >
                {{ agent.symbol }}
              </div>
              <div>
                <div class="font-bold text-lg" :style="{ color: agent.color }">
                  {{ agent.name }}-Ω
                </div>
                <div class="text-xs text-purple-300/60">
                  Perfected Stone · Hyperdense Codex
                </div>
              </div>
            </div>

            <div class="flex gap-2">
              <button
                @click="viewCodex(agent.id)"
                class="px-4 py-2 rounded-lg text-sm font-medium transition-all"
                style="background: rgba(255, 215, 0, 0.1); border: 1px solid rgba(255, 215, 0, 0.3); color: #FFD700;"
              >
                View Codex
              </button>
            </div>
          </div>
        </div>

        <div class="mt-6 pt-4 border-t border-purple-500/20 text-center">
          <p class="text-xs text-purple-300/40 italic">
            "The Stone that is no stone, the medicine that heals all things"
          </p>
        </div>
      </div>
    </template>

    <!-- MEMORY TAB (Dev Mode only) - The Cortex -->
    <template v-if="devMode && activeTab === 'memory'">
      <div class="card mb-6">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-xl font-bold">Agent Memory</h2>
            <p class="text-sm text-gray-400">
              The Cortex: What each agent remembers about you
            </p>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-sm text-gray-400">Total:</span>
            <span class="text-gold font-bold">{{ memoryStats.total }} memories</span>
          </div>
        </div>

        <!-- Global Memory Toggle -->
        <div class="flex items-center justify-between p-4 bg-apex-darker rounded-lg mb-6">
          <div>
            <div class="font-medium">Enable Agent Memory</div>
            <div class="text-sm text-gray-400">
              Allow agents to remember facts and preferences about you
            </div>
          </div>
          <button
            @click="toggleMemoryEnabled"
            class="relative w-14 h-7 rounded-full transition-colors"
            :class="memoryEnabled ? 'bg-gold' : 'bg-apex-border'"
          >
            <span
              class="absolute top-1 left-1 w-5 h-5 rounded-full bg-white transition-transform"
              :class="memoryEnabled ? 'translate-x-7' : ''"
            ></span>
          </button>
        </div>

        <!-- Load memories button -->
        <div v-if="Object.keys(memoryStats.by_agent).length === 0 && !loadingMemory" class="text-center py-4 mb-4">
          <button @click="fetchMemoryStats" class="btn-primary">
            Load Memory Stats
          </button>
        </div>

        <!-- Agents with Memories -->
        <div v-if="loadingMemory" class="text-center py-8 text-gray-400">
          Loading memories...
        </div>

        <div v-else-if="Object.keys(memoryStats.by_agent).length === 0 && memoryStats.total === 0" class="text-center py-12 text-gray-400">
          <div class="text-4xl mb-4">🧠</div>
          <p>No memories yet. Start chatting to build the Cortex!</p>
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="(count, agentId) in memoryStats.by_agent"
            :key="agentId"
            class="p-4 bg-apex-darker rounded-lg"
            :class="{ 'ring-1 ring-gold/50': selectedMemoryAgent === agentId }"
          >
            <div class="flex items-center justify-between mb-2">
              <div class="flex items-center gap-3">
                <div class="text-2xl">{{ getAgentSymbol(agentId) }}</div>
                <div>
                  <div class="font-medium">{{ agentId }}</div>
                  <div class="text-sm text-gray-500">{{ count }} memories</div>
                </div>
              </div>
              <div class="flex gap-2">
                <button
                  @click="fetchAgentMemories(agentId)"
                  class="btn-secondary text-xs px-3 py-1"
                >
                  {{ selectedMemoryAgent === agentId ? 'Refresh' : 'View' }}
                </button>
                <button
                  @click="clearAgentMemories(agentId)"
                  class="text-red-400 hover:text-red-300 text-xs px-3 py-1"
                >
                  Clear
                </button>
              </div>
            </div>

            <!-- Expanded Memory List -->
            <div v-if="selectedMemoryAgent === agentId && agentMemories.length > 0" class="mt-4 pt-4 border-t border-apex-border">
              <div class="space-y-2">
                <div
                  v-for="memory in agentMemories"
                  :key="memory.id"
                  class="flex items-start justify-between p-3 bg-apex-dark rounded-lg text-sm"
                >
                  <div class="flex-1">
                    <div class="flex items-center gap-2 mb-1">
                      <span class="text-xs px-2 py-0.5 rounded-full"
                        :class="{
                          'bg-blue-500/20 text-blue-400': memory.memory_type === 'fact',
                          'bg-purple-500/20 text-purple-400': memory.memory_type === 'preference',
                          'bg-green-500/20 text-green-400': memory.memory_type === 'context',
                          'bg-yellow-500/20 text-yellow-400': memory.memory_type === 'relationship',
                        }"
                      >
                        {{ memory.memory_type }}
                      </span>
                      <span class="text-gray-500 font-mono">{{ memory.key }}</span>
                    </div>
                    <div class="text-gray-300">{{ memory.value }}</div>
                    <div class="text-xs text-gray-500 mt-1">
                      Confidence: {{ (memory.confidence * 100).toFixed(0) }}%
                      · Used {{ memory.access_count }} times
                    </div>
                  </div>
                  <button
                    @click="deleteMemory(agentId, memory.id)"
                    class="text-gray-500 hover:text-red-400 ml-2 text-lg"
                  >
                    &times;
                  </button>
                </div>
              </div>
            </div>

            <div v-else-if="selectedMemoryAgent === agentId && agentMemories.length === 0" class="mt-4 pt-4 border-t border-apex-border text-center text-gray-500 text-sm py-4">
              No memories stored for this agent yet.
            </div>
          </div>
        </div>
      </div>

      <!-- Privacy Controls -->
      <div class="card">
        <h3 class="text-lg font-bold mb-4">Privacy Controls</h3>

        <div class="space-y-4">
          <button
            @click="exportAllMemories"
            class="btn-secondary w-full"
          >
            Export All Memories (JSON)
          </button>

          <button
            @click="clearAllMemories"
            class="btn w-full bg-red-500/20 text-red-400 border border-red-500/50 hover:bg-red-500/30"
          >
            Clear All Memories (Full Amnesia)
          </button>
        </div>

        <p class="text-xs text-gray-500 mt-4">
          Your memories are stored securely and never shared. You can export or delete them at any time.
        </p>
      </div>
    </template>

    <!-- IMPORT TAB (Dev Mode only) -->
    <template v-if="devMode && activeTab === 'import'">
      <div class="card mb-6">
        <h2 class="text-xl font-bold mb-4">Import from Local ApexAurum</h2>
        <p class="text-gray-400 text-sm mb-6">
          Import your conversations and memory from the local ApexAurum app.
          Files are typically located in the <code class="bg-apex-darker px-2 py-1 rounded">sandbox/</code> folder.
        </p>

        <div class="space-y-6">
          <!-- Conversations Import -->
          <div class="bg-apex-darker rounded-lg p-4">
            <div class="flex items-start gap-4">
              <div class="text-3xl">💬</div>
              <div class="flex-1">
                <h3 class="font-medium mb-1">Conversations</h3>
                <p class="text-xs text-gray-500 mb-3">
                  Upload your <code>sandbox/conversations.json</code> file to import chat history.
                </p>
                <input
                  type="file"
                  accept=".json"
                  @change="handleConversationsImport"
                  class="hidden"
                  id="conversations-input"
                />
                <label
                  for="conversations-input"
                  class="btn-secondary text-sm cursor-pointer inline-block"
                  :class="{ 'opacity-50 cursor-not-allowed': importing }"
                >
                  {{ importing ? 'Importing...' : 'Select File' }}
                </label>
                <span
                  v-if="importResult.conversations"
                  class="ml-3 text-sm"
                  :class="importResult.conversations.startsWith('Error') ? 'text-red-400' : 'text-green-400'"
                >
                  {{ importResult.conversations }}
                </span>
              </div>
            </div>
          </div>

          <!-- Memory Import -->
          <div class="bg-apex-darker rounded-lg p-4">
            <div class="flex items-start gap-4">
              <div class="text-3xl">🧠</div>
              <div class="flex-1">
                <h3 class="font-medium mb-1">Memory</h3>
                <p class="text-xs text-gray-500 mb-3">
                  Upload your <code>sandbox/memory.json</code> file to import key-value memory.
                </p>
                <input
                  type="file"
                  accept=".json"
                  @change="handleMemoryImport"
                  class="hidden"
                  id="memory-input"
                />
                <label
                  for="memory-input"
                  class="btn-secondary text-sm cursor-pointer inline-block"
                  :class="{ 'opacity-50 cursor-not-allowed': importing }"
                >
                  Select File
                </label>
                <span
                  v-if="importResult.memory"
                  class="ml-3 text-sm"
                  :class="importResult.memory.startsWith('Error') ? 'text-red-400' : 'text-green-400'"
                >
                  {{ importResult.memory }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div class="mt-6 p-4 bg-gold/5 border border-gold/20 rounded-lg">
          <h4 class="font-medium text-gold mb-2">Supported Formats</h4>
          <ul class="text-xs text-gray-400 space-y-1">
            <li>• <strong>conversations.json</strong> - Chat history with messages</li>
            <li>• <strong>memory.json</strong> - Key-value pairs with metadata</li>
            <li>• Exported JSON files from the cloud app</li>
          </ul>
        </div>
      </div>
    </template>

    <!-- ADVANCED TAB (Dev Mode only) -->
    <template v-if="devMode && activeTab === 'advanced'">
      <div class="card mb-6">
        <h2 class="text-xl font-bold mb-4">Model Settings</h2>

        <div class="space-y-4">
          <div>
            <label class="block text-sm text-gray-400 mb-2">Default Model</label>
            <select v-model="preferences.default_model" class="input">
              <option v-for="model in models" :key="model.id" :value="model.id">
                {{ model.name }}
              </option>
            </select>
          </div>

          <div>
            <label class="block text-sm text-gray-400 mb-2">
              Max Tokens: {{ preferences.max_tokens.toLocaleString() }}
              <span class="text-xs text-gray-500 ml-2">
                ({{ preferences.max_tokens >= 16384 ? 'Maximum' : preferences.max_tokens >= 8192 ? 'High' : 'Normal' }})
              </span>
            </label>
            <input
              type="range"
              v-model.number="preferences.max_tokens"
              min="1024"
              max="16384"
              step="1024"
              class="w-full"
            />
            <div class="flex justify-between text-xs text-gray-500 mt-1">
              <span>1K</span>
              <span>8K</span>
              <span>16K</span>
            </div>
          </div>

          <div>
            <label class="block text-sm text-gray-400 mb-2">
              Temperature: {{ preferences.temperature }}
            </label>
            <input
              type="range"
              v-model.number="preferences.temperature"
              min="0"
              max="1"
              step="0.1"
              class="w-full"
            />
          </div>
        </div>
      </div>

      <div class="card mb-6">
        <h2 class="text-xl font-bold mb-4">Context & Cache</h2>

        <div class="space-y-4">
          <div>
            <label class="block text-sm text-gray-400 mb-2">Cache Strategy</label>
            <select v-model="preferences.cache_strategy" class="input">
              <option v-for="s in cacheStrategies" :key="s.id" :value="s.id">
                {{ s.name }}
              </option>
            </select>
            <p class="text-xs text-gray-500 mt-1">
              Higher caching = more cost savings but potentially stale responses
            </p>
          </div>

          <div>
            <label class="block text-sm text-gray-400 mb-2">Context Strategy</label>
            <select v-model="preferences.context_strategy" class="input">
              <option v-for="s in contextStrategies" :key="s.id" :value="s.id">
                {{ s.name }}
              </option>
            </select>
            <p class="text-xs text-gray-500 mt-1">
              How to handle long conversations approaching token limits
            </p>
          </div>

          <button
            @click="savePreferences"
            class="btn-primary"
            :disabled="loading"
          >
            {{ loading ? 'Saving...' : 'Save Settings' }}
          </button>
        </div>
      </div>

      <!-- Sound & UX Settings -->
      <div class="card mb-6">
        <h2 class="text-xl font-bold mb-4">Sound & UX</h2>

        <div class="space-y-4">
          <div class="flex items-center justify-between">
            <div>
              <div class="font-medium">Sound Effects</div>
              <div class="text-sm text-gray-400">
                Audio feedback for easter eggs and interactions
              </div>
            </div>
            <button
              @click="toggleSound"
              class="relative w-14 h-7 rounded-full transition-colors"
              :class="soundEnabled ? 'bg-gold' : 'bg-apex-border'"
            >
              <span
                class="absolute top-1 left-1 w-5 h-5 rounded-full bg-white transition-transform"
                :class="soundEnabled ? 'translate-x-7' : ''"
              ></span>
            </button>
          </div>

          <!-- Haptic Feedback (mobile only) -->
          <div v-if="hapticSupported" class="flex items-center justify-between">
            <div>
              <div class="font-medium">Haptic Feedback</div>
              <div class="text-sm text-gray-400">
                Vibration feedback on mobile devices
              </div>
            </div>
            <button
              @click="setHapticEnabled(!hapticEnabled)"
              class="relative w-14 h-7 rounded-full transition-colors"
              :class="hapticEnabled ? 'bg-gold' : 'bg-apex-border'"
            >
              <span
                class="absolute top-1 left-1 w-5 h-5 rounded-full bg-white transition-transform"
                :class="hapticEnabled ? 'translate-x-7' : ''"
              ></span>
            </button>
          </div>

          <div v-if="soundEnabled" class="pt-2 border-t border-apex-border">
            <div class="text-sm text-gray-400 mb-3">Test Sounds</div>
            <div class="flex flex-wrap gap-2">
              <button
                @click="sounds.konamiKey(5)"
                class="btn-secondary text-xs px-3 py-1"
              >
                Chime
              </button>
              <button
                @click="sounds.devModeActivate()"
                class="btn-secondary text-xs px-3 py-1"
              >
                Unlock
              </button>
              <button
                @click="sounds.azothLetter(2)"
                class="btn-secondary text-xs px-3 py-1"
              >
                Resonance
              </button>
              <button
                @click="sounds.stoneSelect()"
                class="btn-secondary text-xs px-3 py-1"
              >
                Crystal
              </button>
              <button
                @click="sounds.pacActivate()"
                class="btn-secondary text-xs px-3 py-1"
                :class="pacMode ? 'pac-badge' : ''"
              >
                Ethereal
              </button>
            </div>
          </div>

          <!-- Haptic test buttons -->
          <div v-if="hapticSupported && hapticEnabled" class="pt-2 border-t border-apex-border">
            <div class="text-sm text-gray-400 mb-3">Test Haptics</div>
            <div class="flex flex-wrap gap-2">
              <button
                @click="haptics.light()"
                class="btn-secondary text-xs px-3 py-1"
              >
                Light
              </button>
              <button
                @click="haptics.medium()"
                class="btn-secondary text-xs px-3 py-1"
              >
                Medium
              </button>
              <button
                @click="haptics.strong()"
                class="btn-secondary text-xs px-3 py-1"
              >
                Strong
              </button>
              <button
                @click="haptics.success()"
                class="btn-secondary text-xs px-3 py-1"
              >
                Success
              </button>
              <button
                @click="haptics.pac()"
                class="btn-secondary text-xs px-3 py-1"
                :class="pacMode ? 'pac-badge' : ''"
              >
                PAC
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Usage Stats (in Advanced tab for dev mode) -->
      <div class="card">
        <h2 class="text-xl font-bold mb-4">Usage Statistics</h2>

        <div v-if="usage" class="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div class="bg-apex-darker rounded-lg p-4">
            <div class="text-2xl font-bold text-gold">{{ usage.total_messages }}</div>
            <div class="text-sm text-gray-400">Messages</div>
          </div>

          <div class="bg-apex-darker rounded-lg p-4">
            <div class="text-2xl font-bold text-gold">{{ usage.conversations_count }}</div>
            <div class="text-sm text-gray-400">Conversations</div>
          </div>

          <div class="bg-apex-darker rounded-lg p-4">
            <div class="text-2xl font-bold text-gold">{{ usage.agents_spawned }}</div>
            <div class="text-sm text-gray-400">Agents Spawned</div>
          </div>

          <div class="bg-apex-darker rounded-lg p-4">
            <div class="text-2xl font-bold text-gold">{{ usage.music_generated }}</div>
            <div class="text-sm text-gray-400">Music Generated</div>
          </div>

          <div class="bg-apex-darker rounded-lg p-4">
            <div class="text-2xl font-bold text-gold">{{ (usage.total_tokens / 1000).toFixed(1) }}K</div>
            <div class="text-sm text-gray-400">Tokens Used</div>
          </div>

          <div class="bg-apex-darker rounded-lg p-4">
            <div class="text-2xl font-bold text-gold">{{ formatCost(usage.total_cost_usd) }}</div>
            <div class="text-sm text-gray-400">Total Cost</div>
          </div>
        </div>

        <div v-else class="text-center py-8 text-gray-400">
          Loading usage statistics...
        </div>
      </div>
    </template>

    <!-- API TAB - Multi-Provider Key Management -->
    <template v-if="devMode && activeTab === 'api'">
      <div class="card">
        <div class="flex items-center justify-between mb-6">
          <h2 class="text-xl font-bold">API Keys</h2>
          <span class="text-xs text-gray-400">Bring Your Own Key</span>
        </div>

        <p class="text-sm text-gray-400 mb-6">
          Use your own API keys for direct provider billing. Platform keys are used by default when available.
        </p>

        <!-- Provider Grid -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div
            v-for="(info, providerId) in providerKeys"
            :key="providerId"
            class="rounded-lg border transition-all cursor-pointer"
            :class="{
              'border-green-500/40 bg-green-500/5': info.configured,
              'border-gold/40 bg-gold/5': !info.configured && info.has_platform_grant,
              'border-blue-500/30 bg-blue-500/5': !info.configured && !info.has_platform_grant && info.has_platform_key,
              'border-apex-border bg-apex-darker': !info.configured && !info.has_platform_grant && !info.has_platform_key,
              'ring-1 ring-gold/50': activeProvider === providerId,
            }"
            @click="canConfigureProvider(providerId) ? toggleProvider(providerId) : null"
          >
            <!-- Provider Header -->
            <div class="p-4">
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-3">
                  <span class="text-lg font-bold" :class="{
                    'text-gold': providerId === 'anthropic',
                    'text-blue-400': providerId === 'deepseek',
                    'text-orange-400': providerId === 'groq',
                    'text-purple-400': providerId === 'together',
                    'text-cyan-400': providerId === 'qwen',
                    'text-indigo-400': providerId === 'moonshot',
                  }">{{ info.provider_name }}</span>
                </div>
                <div class="flex items-center gap-2">
                  <!-- Status Badge -->
                  <span v-if="info.configured" class="text-xs px-2 py-0.5 rounded bg-green-500/20 text-green-400">
                    Your Key
                  </span>
                  <span v-else-if="info.has_platform_grant" class="text-xs px-2 py-0.5 rounded bg-gold/20 text-gold font-medium">
                    Platform Granted
                  </span>
                  <span v-else-if="info.has_platform_key" class="text-xs px-2 py-0.5 rounded bg-blue-500/20 text-blue-400">
                    Platform
                  </span>
                  <span v-else class="text-xs px-2 py-0.5 rounded bg-gray-500/20 text-gray-500">
                    Not Set
                  </span>
                  <!-- Lock for insufficient tier -->
                  <span v-if="!canConfigureProvider(providerId)" class="text-gray-500" title="Upgrade tier to configure">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                    </svg>
                  </span>
                </div>
              </div>

              <!-- Key Hint (if configured) -->
              <div v-if="info.configured" class="mt-2 text-xs">
                <span class="font-mono text-gold">{{ info.key_hint }}</span>
                <span v-if="info.added_at" class="text-gray-500 ml-2">
                  added {{ new Date(info.added_at).toLocaleDateString() }}
                </span>
              </div>
            </div>

            <!-- Expanded: Key Input (when clicked) -->
            <div v-if="activeProvider === providerId && canConfigureProvider(providerId)" class="px-4 pb-4 border-t border-apex-border" @click.stop>
              <div class="pt-3 space-y-3">
                <input
                  v-model="newProviderKey"
                  type="password"
                  class="input font-mono text-sm w-full"
                  :placeholder="info.key_placeholder || 'Enter API key...'"
                  @keyup.enter="saveProviderKey(providerId)"
                />
                <div class="flex items-center gap-2">
                  <button
                    @click.stop="saveProviderKey(providerId)"
                    class="btn-primary text-sm px-4"
                    :disabled="savingProvider === providerId || !newProviderKey.trim()"
                  >
                    {{ savingProvider === providerId ? 'Validating...' : (info.configured ? 'Update' : 'Save Key') }}
                  </button>
                  <button
                    v-if="info.configured"
                    @click.stop="removeProviderKey(providerId)"
                    class="text-sm text-red-400 hover:text-red-300 px-2"
                  >
                    Remove
                  </button>
                  <a
                    v-if="info.console_url"
                    :href="info.console_url"
                    target="_blank"
                    @click.stop
                    class="text-sm text-gold/70 hover:text-gold ml-auto"
                  >
                    Get key &rarr;
                  </a>
                </div>
              </div>
            </div>

            <!-- Tier gate message -->
            <div v-if="activeProvider === providerId && !canConfigureProvider(providerId)" class="px-4 pb-4 border-t border-apex-border" @click.stop>
              <p class="pt-3 text-sm text-amber-400">
                {{ providerId === 'anthropic' ? 'Upgrade to Opus to configure Anthropic keys.' : 'Upgrade to Adept to configure open-source providers.' }}
              </p>
            </div>
          </div>
        </div>

        <!-- Security Note -->
        <div class="mt-6 pt-4 border-t border-apex-border">
          <p class="text-xs text-gray-500">
            Keys are encrypted at rest and never logged. Validation uses a minimal test call. Your key is used instead of the platform key when configured.
          </p>
        </div>
      </div>
    </template>

    <!-- Danger Zone (shown in both modes) -->
    <div v-if="activeTab === 'profile' || !devMode" class="card mt-6 border-red-500/30">
      <h2 class="text-xl font-bold text-red-400 mb-4">Danger Zone</h2>
      <p class="text-sm text-gray-400 mb-4">
        These actions are irreversible. Please be careful.
      </p>
      <div class="flex gap-3">
        <button class="btn bg-red-500/20 text-red-400 border border-red-500/50 hover:bg-red-500/30">
          Delete Account
        </button>
        <button
          v-if="devMode"
          @click="devMode = false; localStorage.removeItem('devMode')"
          class="btn-secondary text-sm"
        >
          Exit Dev Mode
        </button>
      </div>
    </div>

    <!-- Prompt Viewer Modal -->
    <div v-if="showPromptViewer" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div class="card w-full max-w-4xl max-h-[80vh] flex flex-col">
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center gap-3">
            <div
              class="w-10 h-10 rounded-full flex items-center justify-center font-bold text-lg"
              :style="{ backgroundColor: viewingPrompt?.color + '20', color: viewingPrompt?.color }"
            >
              {{ viewingPrompt?.symbol }}
            </div>
            <div>
              <h2 class="text-xl font-bold">{{ viewingPrompt?.name }}</h2>
              <div class="text-xs text-gray-500">{{ viewingPrompt?.type }} format</div>
            </div>
          </div>
          <button @click="showPromptViewer = false" class="text-gray-400 hover:text-white text-2xl">
            &times;
          </button>
        </div>

        <div class="flex-1 overflow-y-auto">
          <pre class="bg-apex-darker rounded-lg p-4 text-sm text-gray-300 whitespace-pre-wrap font-mono">{{ viewingPrompt?.prompt }}</pre>
        </div>

        <div class="flex justify-end gap-3 mt-4 pt-4 border-t border-apex-border">
          <button @click="copyToCustom(viewingPrompt); showPromptViewer = false" class="btn-primary">
            Edit Copy
          </button>
          <button @click="showPromptViewer = false" class="btn-secondary">
            Close
          </button>
        </div>
      </div>
    </div>

    <!-- Agent Editor Modal -->
    <div v-if="showAgentEditor" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div class="card w-full max-w-4xl max-h-[90vh] flex flex-col">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-xl font-bold">
            {{ editingAgent?.id ? 'Edit Agent' : 'Create Agent' }}
          </h2>
          <button @click="showAgentEditor = false" class="text-gray-400 hover:text-white text-2xl">
            &times;
          </button>
        </div>

        <div class="flex-1 overflow-y-auto space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm text-gray-400 mb-2">Name</label>
              <input v-model="editingAgent.name" class="input" placeholder="Agent name" />
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm text-gray-400 mb-2">Symbol</label>
                <input v-model="editingAgent.symbol" class="input" maxlength="2" placeholder="+" />
              </div>

              <div>
                <label class="block text-sm text-gray-400 mb-2">Color</label>
                <input type="color" v-model="editingAgent.color" class="input h-10" />
              </div>
            </div>
          </div>

          <div>
            <label class="block text-sm text-gray-400 mb-2">Prompt</label>
            <textarea
              v-model="editingAgent.prompt"
              class="input h-80 resize-none font-mono text-sm"
              placeholder="Enter the system prompt for this agent..."
            ></textarea>
          </div>
        </div>

        <div class="flex justify-end gap-3 mt-4 pt-4 border-t border-apex-border">
          <button @click="showAgentEditor = false" class="btn-secondary">
            Cancel
          </button>
          <button @click="saveAgent" class="btn-primary">
            Save Agent
          </button>
        </div>
      </div>
    </div>

    <!-- Codex Viewer Modal (PAC Mode) -->
    <div v-if="showCodexViewer" class="fixed inset-0 flex items-center justify-center z-50 p-4" style="background: rgba(10, 6, 18, 0.95);">
      <div class="w-full max-w-5xl max-h-[90vh] flex flex-col rounded-xl overflow-hidden" style="background: linear-gradient(180deg, rgba(26, 10, 46, 0.98) 0%, rgba(18, 8, 31, 0.98) 100%); border: 1px solid rgba(255, 215, 0, 0.3); box-shadow: 0 0 60px rgba(255, 215, 0, 0.1);">
        <!-- Header -->
        <div class="p-6 border-b border-purple-500/20">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-4">
              <div
                class="w-14 h-14 rounded-full flex items-center justify-center font-bold text-2xl agent-halo"
                :style="{
                  backgroundColor: viewingCodex?.color + '15',
                  color: viewingCodex?.color,
                  boxShadow: `0 0 30px ${viewingCodex?.color}50`
                }"
              >
                {{ viewingCodex?.symbol }}
              </div>
              <div>
                <h2 class="text-2xl font-bold text-gold" style="text-shadow: 0 0 20px rgba(255, 215, 0, 0.4);">
                  {{ viewingCodex?.name }}-Ω
                </h2>
                <div class="text-sm text-purple-300/60">Hyperdense Codex · Perfected Stone</div>
              </div>
            </div>
            <button @click="showCodexViewer = false" class="text-purple-300/50 hover:text-gold text-3xl transition-colors">
              &times;
            </button>
          </div>
        </div>

        <!-- Codex Content -->
        <div class="flex-1 overflow-y-auto p-6">
          <pre class="codex-viewer rounded-lg p-6 text-sm whitespace-pre-wrap overflow-x-auto" style="tab-size: 2;">{{ viewingCodex?.prompt }}</pre>
        </div>

        <!-- Footer -->
        <div class="p-4 border-t border-purple-500/20 flex justify-between items-center">
          <p class="text-xs text-purple-300/40 italic">
            "That which is above is like that which is below"
          </p>
          <button
            @click="showCodexViewer = false"
            class="px-6 py-2 rounded-lg font-medium transition-all"
            style="background: rgba(255, 215, 0, 0.1); border: 1px solid rgba(255, 215, 0, 0.3); color: #FFD700;"
          >
            Close Codex
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
