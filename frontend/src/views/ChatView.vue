<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { useDevMode } from '@/composables/useDevMode'
import { useSound } from '@/composables/useSound'
import { useHaptic } from '@/composables/useHaptic'
import { useSwipe } from '@/composables/useSwipe'
import { usePullToRefresh } from '@/composables/usePullToRefresh'
import { marked } from 'marked'
import api from '@/services/api'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const router = useRouter()
const chat = useChatStore()
const auth = useAuthStore()
const { devMode, pacMode } = useDevMode()
const { sounds } = useSound()
const { haptics } = useHaptic()
const { showToast } = useToast()
const swipe = useSwipe()
const pullRefresh = usePullToRefresh()

const inputMessage = ref('')
const messagesContainer = ref(null)
const inputRef = ref(null)
const showSidebar = ref(true)
const mainArea = ref(null)
const conversationsList = ref(null)
const isMobile = ref(window.innerWidth < 768)
const toolsCount = ref(0)

// File attachments
const attachedFiles = ref([])  // Array of { id, name, file_type, mime_type }
const showFilePicker = ref(false)
const vaultFiles = ref([])
const loadingVaultFiles = ref(false)

// Conversation management state
const searchQuery = ref('')
const editingConvId = ref(null)
const editingTitle = ref('')
const titleInputRef = ref(null)
const contextMenu = ref({ visible: false, x: 0, y: 0, conv: null })

// Native agents - The Four Alchemical Agents
const nativeAgents = [
  { id: 'AZOTH', name: 'Azoth', color: '#FFD700', symbol: '∴', isNative: true, hasPac: true },
  { id: 'ELYSIAN', name: 'Elysian', color: '#E8B4FF', symbol: '∴', isNative: true, hasPac: true },
  { id: 'VAJRA', name: 'Vajra', color: '#4FC3F7', symbol: '∴', isNative: true, hasPac: true },
  { id: 'KETHER', name: 'Kether', color: '#FFFFFF', symbol: '∴', isNative: true, hasPac: true },
]

// PAC agents (Perfected Stones - only visible in PAC mode)
const pacAgents = computed(() => {
  if (!pacMode.value) return []
  return nativeAgents
    .filter(a => a.hasPac)
    .map(a => ({
      ...a,
      id: a.id + '-PAC',
      name: a.name + '-Ω',
      isPac: true,
    }))
})

// Custom agents (loaded from API)
const customAgents = ref([])

// Combined agents list
const allAgents = computed(() => {
  const custom = customAgents.value.map(a => ({
    id: a.id,
    name: a.name,
    color: a.color,
    symbol: a.symbol,
    isNative: false,
    isPac: false,
  }))
  // PAC agents come first in PAC mode
  return [...pacAgents.value, ...nativeAgents.map(a => ({ ...a, isPac: false })), ...custom]
})

const selectedAgent = ref(localStorage.getItem('selectedAgent') || 'AZOTH')

// Model tier icons/colors
const modelTierStyles = {
  opus: { color: '#FFD700', icon: '⚜️', label: 'Opus' },
  sonnet: { color: '#4FC3F7', icon: '✦', label: 'Sonnet' },
  haiku: { color: '#E8B4FF', icon: '◇', label: 'Haiku' },
  // OSS provider tiers
  reasoning: { color: '#FF9800', icon: '✴', label: 'Reasoning' },
  standard: { color: '#4CAF50', icon: '●', label: 'Standard' },
  large: { color: '#2196F3', icon: '⬢', label: 'Large' },
  small: { color: '#9E9E9E', icon: '○', label: 'Small' },
  moe: { color: '#AB47BC', icon: '✦', label: 'MoE' },
  fast: { color: '#00BCD4', icon: '⚡', label: 'Fast' },
}

function getModelTierStyle(tier) {
  return modelTierStyles[tier] || modelTierStyles.haiku
}

// Select an agent (with sound for PAC agents, haptic for all)
function selectAgent(agentId) {
  const isPac = agentId.endsWith('-PAC')
  if (isPac) {
    sounds.stoneSelect()
  }
  haptics.light()
  selectedAgent.value = agentId
  localStorage.setItem('selectedAgent', agentId)
}

// Check if currently using a PAC agent
const isUsingPacAgent = computed(() => {
  return selectedAgent.value?.endsWith('-PAC') ?? false
})

// Get the actual agent ID for API calls (strip -PAC suffix)
const actualAgentId = computed(() => {
  return selectedAgent.value?.replace('-PAC', '') ?? 'AZOTH'
})

// Load custom agents
async function fetchCustomAgents() {
  try {
    const response = await api.get('/api/v1/prompts/custom')
    customAgents.value = response.data?.agents || []
  } catch (e) {
    // Ignore errors (user might not be logged in)
    customAgents.value = []
  }
}

// File attachment functions
async function fetchVaultFiles() {
  loadingVaultFiles.value = true
  try {
    const response = await api.get('/api/v1/files')
    // Flatten: get files from root listing
    vaultFiles.value = (response.data.files || []).filter(f =>
      ['image', 'document', 'code', 'data'].includes(f.file_type)
    )
  } catch (e) {
    console.error('Failed to fetch vault files:', e)
  } finally {
    loadingVaultFiles.value = false
  }
}

function attachFile(file) {
  // Don't attach duplicates
  if (attachedFiles.value.some(f => f.id === file.id)) return
  if (attachedFiles.value.length >= 5) {
    showToast('Maximum 5 attachments', 'warning')
    return
  }
  attachedFiles.value.push({
    id: file.id,
    name: file.name || file.original_filename,
    file_type: file.file_type,
    mime_type: file.mime_type,
  })
  showFilePicker.value = false
}

function removeAttachment(fileId) {
  attachedFiles.value = attachedFiles.value.filter(f => f.id !== fileId)
}

function toggleFilePicker() {
  showFilePicker.value = !showFilePicker.value
  if (showFilePicker.value && vaultFiles.value.length === 0) {
    fetchVaultFiles()
  }
}

// Swipe cleanup
let swipeCleanup = null

// Resize listener
function handleResize() {
  isMobile.value = window.innerWidth < 768
}

// Load conversation if ID in route
onMounted(async () => {
  await chat.fetchProviders()  // Fetch available LLM providers (dev mode feature)
  await chat.fetchModels()  // Fetch available models for current provider
  await chat.fetchConversations()
  await fetchCustomAgents()

  // Fetch tools count
  try {
    const response = await api.get('/api/v1/tools')
    toolsCount.value = response.data.count || 0
  } catch (e) {
    toolsCount.value = 46  // Fallback to known count
  }

  if (route.params.id) {
    await chat.loadConversation(route.params.id)
  }

  // Select agent from query param (e.g., from Village GUI click)
  if (route.query.agent) {
    const agentId = route.query.agent
    // Check if it's a valid agent
    const validAgent = allAgents.value.find(a => a.id === agentId || a.id === agentId + '-PAC')
    if (validAgent) {
      selectedAgent.value = validAgent.id
      // Clear the query param to keep URL clean
      router.replace({ path: '/chat', query: {} })
    }
  }

  inputRef.value?.focus()

  // Setup swipe gestures for mobile sidebar
  window.addEventListener('resize', handleResize)

  // Swipe from left edge to open sidebar
  swipe.registerCallbacks({
    onEdgeSwipeRight: () => {
      if (!showSidebar.value) {
        showSidebar.value = true
        haptics.sidebarToggle()
      }
    },
    onSwipeLeft: () => {
      if (showSidebar.value && isMobile.value) {
        showSidebar.value = false
        haptics.sidebarToggle()
      }
    },
  })

  // Attach swipe to main area
  nextTick(() => {
    if (mainArea.value) {
      swipeCleanup = swipe.attachToElement(mainArea.value)
    }

    // Setup pull-to-refresh on conversations list
    if (conversationsList.value) {
      pullRefresh.attach(conversationsList.value, async () => {
        await chat.fetchConversations()
      })
    }
  })
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (swipeCleanup) swipeCleanup()
})

// Watch for route changes
watch(() => route.params.id, async (newId) => {
  if (newId) {
    await chat.loadConversation(newId)
  } else {
    chat.createConversation()
  }
})

// Auto-scroll on new messages
watch(() => chat.messages.length, () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
})

// Branch info - defined here (before loadBranchInfo) to avoid TDZ error
const branchInfo = ref({ parent: null, branches: [], branch_count: 0 })

// Define loadBranchInfo BEFORE the watcher that uses it (TDZ fix)
async function loadBranchInfo() {
  if (chat.currentConversation?.id) {
    branchInfo.value = await chat.getBranches(chat.currentConversation.id)
  } else {
    branchInfo.value = { parent: null, branches: [], branch_count: 0 }
  }
}

// Load branch info when conversation changes
watch(() => chat.currentConversation?.id, () => {
  loadBranchInfo()
}, { immediate: true })

async function handleSubmit() {
  const message = inputMessage.value.trim()
  if (!message || chat.isStreaming) return

  inputMessage.value = ''
  // Collect file_ids before clearing
  const fileIds = attachedFiles.value.length > 0 ? attachedFiles.value.map(f => f.id) : undefined
  attachedFiles.value = []
  showFilePicker.value = false
  // Haptic feedback on send
  haptics.medium()
  // Use actualAgentId and pass isPac flag for PAC prompt loading
  await chat.sendMessage(message, actualAgentId.value, undefined, isUsingPacAgent.value, fileIds)
}

function newConversation() {
  chat.createConversation()
  router.push('/chat')
}

function selectConversation(conv) {
  router.push(`/chat/${conv.id}`)
  // Auto-close sidebar on mobile
  if (window.innerWidth < 768) {
    showSidebar.value = false
  }
}

// Filtered conversations (search)
const filteredConversations = computed(() => {
  if (!searchQuery.value.trim()) return chat.sortedConversations
  const q = searchQuery.value.toLowerCase()
  return chat.sortedConversations.filter(c =>
    c.title?.toLowerCase().includes(q)
  )
})

// Inline title editing
function startEdit(conv) {
  editingConvId.value = conv.id
  editingTitle.value = conv.title || ''
  nextTick(() => titleInputRef.value?.focus())
}

async function saveTitle() {
  if (editingConvId.value && editingTitle.value.trim()) {
    await chat.updateConversation(editingConvId.value, { title: editingTitle.value.trim() })
  }
  editingConvId.value = null
}

function cancelEdit() {
  editingConvId.value = null
}

// Context menu
function showContextMenu(event, conv) {
  event.preventDefault()
  contextMenu.value = {
    visible: true,
    x: event.clientX,
    y: event.clientY,
    conv
  }
}

function hideContextMenu() {
  contextMenu.value.visible = false
}

async function handleContextAction(action) {
  const conv = contextMenu.value.conv
  if (!conv) return

  switch (action) {
    case 'rename':
      startEdit(conv)
      break
    case 'favorite':
      await chat.toggleFavorite(conv.id)
      break
    case 'archive':
      await chat.archiveConversation(conv.id)
      break
    case 'export':
      showExportModal.value = true
      exportConvId.value = conv.id
      break
    case 'delete':
      if (confirm('Delete this conversation?')) {
        await chat.deleteConversation(conv.id)
        if (chat.currentConversation?.id === conv.id) {
          router.push('/chat')
        }
      }
      break
  }
  hideContextMenu()
}

// Export modal
const showExportModal = ref(false)
const exportConvId = ref(null)

// Fork modal (The Multiverse)
const showForkModal = ref(false)
const forkMessageId = ref(null)
const forkLabel = ref('')
const forking = ref(false)

async function handleExport(format) {
  if (exportConvId.value) {
    await chat.exportConversation(exportConvId.value, format)
  }
  showExportModal.value = false
  exportConvId.value = null
}

// ═══════════════════════════════════════════════════════════════════════════════
// BRANCHING (THE MULTIVERSE) - Fork conversations at any message point
// ═══════════════════════════════════════════════════════════════════════════════

function openForkModal(messageId) {
  forkMessageId.value = messageId
  forkLabel.value = ''
  showForkModal.value = true
}

async function handleFork() {
  if (!chat.currentConversation?.id || !forkMessageId.value) return

  forking.value = true
  try {
    const result = await chat.forkConversation(
      chat.currentConversation.id,
      forkMessageId.value,
      forkLabel.value || null
    )
    showForkModal.value = false
    // Navigate to the new branch
    router.push(`/chat/${result.id}`)
    haptics.success()
  } catch (e) {
    console.error('Fork failed:', e)
    showToast('Failed to create branch. Please try again.')
  } finally {
    forking.value = false
  }
}

function renderMarkdown(content) {
  return marked(content, { breaks: true })
}
</script>

<template>
  <div class="flex h-[calc(100vh-4rem)] relative">
    <!-- Mobile Sidebar Backdrop -->
    <div
      v-if="showSidebar"
      @click="showSidebar = false"
      class="md:hidden fixed inset-0 bg-black/50 z-20"
    ></div>

    <!-- Sidebar -->
    <aside
      class="fixed md:relative inset-y-0 left-0 z-30 w-72 bg-apex-dark border-r border-apex-border flex flex-col transform transition-transform duration-300 md:translate-x-0"
      :class="showSidebar ? 'translate-x-0' : '-translate-x-full md:translate-x-0'"
      :style="{ top: '4rem', height: 'calc(100vh - 4rem)' }"
    >
      <!-- Mobile Close Button -->
      <button
        @click="showSidebar = false"
        class="md:hidden absolute top-4 right-4 p-1 text-gray-400 hover:text-white z-10"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
        </svg>
      </button>
      <!-- New Chat Button -->
      <div class="p-4 pb-2">
        <button
          @click="newConversation"
          class="btn-primary w-full flex items-center justify-center gap-2"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clip-rule="evenodd" />
          </svg>
          New Chat
        </button>
      </div>

      <!-- Search -->
      <div class="px-4 pb-2">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search conversations..."
          class="input text-sm py-2"
        />
      </div>

      <!-- Conversations List (with pull-to-refresh) -->
      <div ref="conversationsList" class="flex-1 overflow-y-auto px-2 relative">
        <!-- Pull to refresh indicator -->
        <div
          v-if="pullRefresh.isPulling.value || pullRefresh.isRefreshing.value"
          class="absolute top-0 left-0 right-0 flex justify-center py-2 z-10"
          :style="{ transform: `translateY(${Math.min(pullRefresh.pullDistance.value, 40)}px)` }"
        >
          <div
            class="w-6 h-6 rounded-full border-2 border-gold flex items-center justify-center transition-all"
            :class="{ 'animate-spin': pullRefresh.isRefreshing.value, 'opacity-50': !pullRefresh.passedThreshold.value }"
          >
            <span v-if="pullRefresh.isRefreshing.value" class="text-gold text-xs">⟳</span>
            <span v-else class="text-gold text-xs">↓</span>
          </div>
        </div>
        <div
          v-for="conv in filteredConversations"
          :key="conv.id"
          @click="selectConversation(conv)"
          @contextmenu="showContextMenu($event, conv)"
          class="group px-3 py-2 rounded-lg cursor-pointer transition-colors mb-1"
          :class="[
            chat.currentConversation?.id === conv.id
              ? 'bg-gold/20 text-gold'
              : 'hover:bg-white/5 text-gray-300',
            conv.parent_id ? 'ml-4' : ''
          ]"
        >
          <div class="flex items-center justify-between gap-2">
            <!-- Branch indicator -->
            <span v-if="conv.parent_id" class="text-gray-500 text-xs shrink-0" title="Branch">├─</span>

            <!-- Inline Title Edit -->
            <template v-if="editingConvId === conv.id">
              <input
                ref="titleInputRef"
                v-model="editingTitle"
                @keyup.enter="saveTitle"
                @keyup.escape="cancelEdit"
                @blur="saveTitle"
                @click.stop
                class="input text-sm py-1 flex-1"
              />
            </template>
            <template v-else>
              <span
                @dblclick.stop="startEdit(conv)"
                class="truncate text-sm flex-1"
                title="Double-click to rename"
              >
                {{ conv.branch_label || conv.title || 'New Conversation' }}
              </span>
            </template>

            <!-- Branch count badge -->
            <span
              v-if="conv.branch_count > 0"
              class="text-xs bg-purple-500/20 text-purple-300 px-1.5 py-0.5 rounded shrink-0"
              :title="`${conv.branch_count} branch${conv.branch_count > 1 ? 'es' : ''}`"
            >
              {{ conv.branch_count }}
            </span>

            <!-- Favorite Star (clickable) -->
            <button
              @click.stop="chat.toggleFavorite(conv.id)"
              class="text-xs transition-colors shrink-0"
              :class="conv.favorite
                ? 'text-gold'
                : 'text-gray-600 hover:text-gold/50 opacity-0 group-hover:opacity-100'"
              title="Toggle favorite"
            >
              {{ conv.favorite ? '★' : '☆' }}
            </button>
          </div>
          <div class="text-xs text-gray-500 mt-1 flex items-center gap-2">
            <span>{{ new Date(conv.updated_at).toLocaleDateString() }}</span>
            <span v-if="conv.parent_id" class="text-purple-400">branch</span>
          </div>
        </div>

        <div v-if="filteredConversations.length === 0 && searchQuery" class="text-center text-gray-500 text-sm py-8">
          No matches found
        </div>
        <div v-else-if="chat.conversations.length === 0" class="text-center text-gray-500 text-sm py-8">
          No conversations yet
        </div>
      </div>

      <!-- Provider Selector (The Many Flames - Dev Mode Only) -->
      <div v-if="devMode" class="p-4 border-t border-apex-border" :class="{ 'border-purple-500/30': pacMode }">
        <label class="block text-xs mb-2 flex items-center gap-2" :class="pacMode ? 'text-purple-300/60' : 'text-gray-500'">
          <span>Provider</span>
          <span class="text-gold">🔧</span>
        </label>
        <select
          :value="chat.selectedProvider"
          @change="chat.setProvider($event.target.value)"
          class="w-full bg-apex-darker border border-apex-border rounded-lg px-3 py-2 text-sm focus:ring-1 focus:ring-gold focus:border-gold transition-all cursor-pointer"
          :class="pacMode ? 'border-purple-500/30' : ''"
        >
          <option
            v-for="provider in chat.availableProviders"
            :key="provider.id"
            :value="provider.id"
            :disabled="!provider.available"
            class="bg-apex-darker"
          >
            {{ provider.name }}{{ !provider.available ? ' (no key)' : '' }}
          </option>
        </select>
        <p class="text-xs text-gray-600 mt-1">
          {{ chat.selectedProvider === 'anthropic' ? 'Default models' : 'Alternative provider' }}
        </p>
      </div>

      <!-- Model Selector (Unleash the Stones) -->
      <div class="p-4 border-t border-apex-border" :class="{ 'border-purple-500/30': pacMode, 'border-t-0': devMode }">
        <label class="block text-xs mb-2 flex items-center gap-2" :class="pacMode ? 'text-purple-300/60' : 'text-gray-500'">
          <span>Model</span>
          <span v-if="chat.availableModels.length === 0" class="text-xs text-gray-600">(loading...)</span>
        </label>
        <select
          :value="chat.selectedModel"
          @change="chat.setSelectedModel($event.target.value)"
          class="w-full bg-apex-darker border border-apex-border rounded-lg px-3 py-2 text-sm focus:ring-1 focus:ring-gold focus:border-gold transition-all cursor-pointer"
          :class="pacMode ? 'border-purple-500/30' : ''"
          :style="{ color: chat.availableModels.length ? 'inherit' : '#666' }"
        >
          <!-- Show loading state if models not loaded -->
          <option v-if="chat.availableModels.length === 0" value="" disabled>Loading models...</option>
          <!-- Model options -->
          <option
            v-for="model in chat.availableModels"
            :key="model.id"
            :value="model.id"
            class="bg-apex-darker"
          >
            {{ getModelTierStyle(model.tier).icon }} {{ model.name }}
          </option>
        </select>
        <p class="text-xs text-gray-500 mt-1">
          {{ chat.availableModels.find(m => m.id === chat.selectedModel)?.description || 'Loading...' }}
        </p>

        <!-- Max Tokens Slider -->
        <div class="mt-3">
          <label class="block text-xs mb-1" :class="pacMode ? 'text-purple-300/60' : 'text-gray-500'">
            Max Tokens: {{ chat.maxTokens.toLocaleString() }}
          </label>
          <input
            type="range"
            :value="chat.maxTokens"
            @input="chat.setMaxTokens(parseInt($event.target.value))"
            min="1024"
            max="16384"
            step="1024"
            class="w-full h-1 bg-apex-border rounded-lg appearance-none cursor-pointer"
          />
          <div class="flex justify-between text-xs text-gray-600 mt-0.5">
            <span>1K</span>
            <span>16K</span>
          </div>
        </div>

        <!-- Tools Toggle (The Athanor's Hands) -->
        <div class="mt-3 flex items-center justify-between">
          <label class="text-xs" :class="pacMode ? 'text-purple-300/60' : 'text-gray-500'">
            <span class="flex items-center gap-1">
              🔧 Tools
              <span class="text-gray-600">({{ toolsCount }})</span>
            </span>
          </label>
          <button
            @click="chat.setToolsEnabled(!chat.toolsEnabled)"
            class="relative w-10 h-5 rounded-full transition-colors"
            :class="chat.toolsEnabled ? 'bg-gold/60' : 'bg-apex-border'"
          >
            <span
              class="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform"
              :class="chat.toolsEnabled ? 'translate-x-5' : ''"
            ></span>
          </button>
        </div>
      </div>

      <!-- Agent Selector -->
      <div class="p-4 border-t border-apex-border" :class="{ 'border-purple-500/30': pacMode }">
        <label class="block text-xs mb-2" :class="pacMode ? 'text-purple-300/60' : 'text-gray-500'">
          {{ pacMode ? 'Invoke Agent' : 'Active Agent' }}
        </label>

        <!-- PAC Agents (shown first if in PAC mode) -->
        <div v-if="pacAgents.length > 0" class="mb-3">
          <div class="text-xs text-purple-300/40 mb-1">Perfected Stones</div>
          <div class="flex flex-wrap gap-1">
            <button
              v-for="agent in pacAgents"
              :key="agent.id"
              @click="selectAgent(agent.id)"
              class="p-2 rounded text-center transition-all text-xs min-w-[3rem] agent-halo"
              :style="{
                backgroundColor: selectedAgent === agent.id ? agent.color + '33' : 'rgba(26, 10, 46, 0.6)',
                color: selectedAgent === agent.id ? agent.color : agent.color + '80',
                boxShadow: selectedAgent === agent.id
                  ? `inset 0 0 0 1px ${agent.color}, 0 0 15px ${agent.color}40`
                  : `inset 0 0 0 1px ${agent.color}30`,
              }"
              :title="agent.name + ' (Perfected Stone)'"
            >
              {{ agent.symbol }}Ω
            </button>
          </div>
        </div>

        <!-- Regular Agents -->
        <div class="flex flex-wrap gap-1">
          <button
            v-for="agent in allAgents.filter(a => !a.isPac)"
            :key="agent.id"
            @click="selectAgent(agent.id)"
            class="p-2 rounded text-center transition-all text-xs min-w-[2.5rem]"
            :style="{
              backgroundColor: selectedAgent === agent.id ? agent.color + '33' : 'transparent',
              color: selectedAgent === agent.id ? agent.color : '#9ca3af',
              boxShadow: selectedAgent === agent.id ? `inset 0 0 0 1px ${agent.color}` : 'none',
            }"
            :title="agent.name + (agent.isNative ? '' : ' (Custom)')"
          >
            {{ agent.symbol || '+' }}{{ agent.name.charAt(0) }}
          </button>
        </div>
        <div v-if="customAgents.length > 0" class="mt-2 text-xs text-gray-500">
          + {{ customAgents.length }} custom
        </div>
      </div>
    </aside>

    <!-- Main Chat Area -->
    <main
      ref="mainArea"
      class="flex-1 flex flex-col transition-all duration-500"
      :class="isUsingPacAgent ? 'pac-chat-area' : 'bg-apex-darker'"
      :style="isUsingPacAgent ? {
        background: 'radial-gradient(ellipse at center, rgba(26, 10, 46, 0.95) 0%, rgba(10, 6, 18, 0.98) 100%)'
      } : {}"
    >
      <!-- Toggle Sidebar (mobile) -->
      <button
        v-if="!showSidebar"
        @click="showSidebar = true"
        class="md:hidden fixed top-20 left-4 z-40 p-2 bg-apex-card border border-apex-border rounded-lg shadow-lg"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clip-rule="evenodd" />
        </svg>
      </button>

      <!-- Messages -->
      <div
        ref="messagesContainer"
        class="flex-1 overflow-y-auto px-4 py-6"
      >
        <div class="max-w-3xl mx-auto space-y-6">
          <!-- Login Required Prompt -->
          <div v-if="!auth.isAuthenticated" class="text-center py-20">
            <div class="text-6xl font-serif font-bold text-gold mb-4">Au</div>
            <h2 class="text-2xl font-bold mb-2">Welcome to ApexAurum</h2>
            <p class="text-gray-400 mb-6 max-w-md mx-auto">
              Sign in to start chatting with the Agents.
            </p>
            <div class="flex gap-4 justify-center">
              <router-link to="/login" class="btn-primary">
                Sign In
              </router-link>
              <router-link to="/register" class="btn-secondary">
                Create Account
              </router-link>
            </div>
            <p class="text-sm text-gray-500 mt-6">
              Free tier includes 50 messages/month
            </p>
          </div>

          <!-- Welcome message if no messages (authenticated) -->
          <div v-else-if="chat.messages.length === 0" class="text-center py-20">
            <div class="text-6xl font-serif font-bold text-gold mb-4">Au</div>
            <h2 class="text-2xl font-bold mb-2">Welcome to ApexAurum Cloud</h2>
            <p class="text-gray-400 mb-8">68 Tools. Four Alchemists. One Village.</p>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-3 max-w-xl mx-auto text-sm">
              <button
                @click="inputMessage = 'What can you help me with?'"
                class="btn-secondary text-left"
              >
                What can you do?
              </button>
              <button
                @click="inputMessage = 'Tell me about the Village Protocol'"
                class="btn-secondary text-left"
              >
                Village Protocol
              </button>
              <button
                @click="inputMessage = 'Generate some music for me'"
                class="btn-secondary text-left"
              >
                Generate Music
              </button>
              <button
                @click="inputMessage = 'Spawn a research agent'"
                class="btn-secondary text-left"
              >
                Spawn Agent
              </button>
            </div>
          </div>

          <!-- Branch Info Bar -->
          <div
            v-if="branchInfo.parent || branchInfo.branch_count > 0"
            class="bg-purple-500/10 border border-purple-500/30 rounded-lg px-4 py-2 mb-4"
          >
            <div class="flex items-center gap-4 text-sm">
              <!-- Parent link -->
              <button
                v-if="branchInfo.parent"
                @click="router.push(`/chat/${branchInfo.parent.id}`)"
                class="flex items-center gap-1 text-purple-300 hover:text-purple-200"
              >
                <span>←</span>
                <span>Parent: {{ branchInfo.parent.title || 'Untitled' }}</span>
              </button>

              <!-- Branch count -->
              <span v-if="branchInfo.branch_count > 0" class="text-gray-400">
                {{ branchInfo.branch_count }} branch{{ branchInfo.branch_count > 1 ? 'es' : '' }}
              </span>
            </div>
          </div>

          <!-- Message list -->
          <div
            v-for="message in chat.messages"
            :key="message.id"
            class="flex gap-4 group relative"
            :class="message.role === 'user' ? 'justify-end' : ''"
          >
            <!-- Fork button (appears on hover, left side) -->
            <button
              v-if="message.role !== 'system' && chat.currentConversation?.id"
              @click.stop="openForkModal(message.id)"
              class="absolute -left-8 top-2 opacity-0 group-hover:opacity-100 transition-opacity p-1 text-gray-500 hover:text-purple-400"
              title="Fork from here"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M7.707 3.293a1 1 0 010 1.414L5.414 7H11a7 7 0 017 7v2a1 1 0 11-2 0v-2a5 5 0 00-5-5H5.414l2.293 2.293a1 1 0 11-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clip-rule="evenodd" />
              </svg>
            </button>

            <!-- Avatar -->
            <div
              v-if="message.role !== 'user'"
              class="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 transition-all"
              :class="message.role === 'system'
                ? 'bg-red-500/20'
                : isUsingPacAgent
                  ? 'agent-halo'
                  : 'bg-gold/20'"
              :style="isUsingPacAgent && message.role === 'assistant' ? {
                backgroundColor: 'rgba(255, 215, 0, 0.15)',
                boxShadow: '0 0 20px rgba(255, 215, 0, 0.3)'
              } : {}"
            >
              <span v-if="message.role === 'assistant'" class="text-gold font-serif font-bold text-sm">
                {{ isUsingPacAgent ? '∴' : 'Au' }}
              </span>
              <span v-else class="text-red-400 text-sm">!</span>
            </div>

            <!-- Message content -->
            <div
              class="max-w-[80%] rounded-2xl px-4 py-3 transition-all"
              :class="{
                'bg-gold text-apex-dark': message.role === 'user',
                'bg-apex-card': message.role === 'assistant' && !isUsingPacAgent,
                'pac-message': message.role === 'assistant' && isUsingPacAgent,
                'bg-red-500/10 border border-red-500/30': message.role === 'system'
              }"
            >
              <div
                v-if="message.role === 'assistant'"
                class="prose prose-sm max-w-none"
                :class="isUsingPacAgent ? 'prose-invert pac-prose' : 'prose-invert'"
                :style="isUsingPacAgent ? { color: '#E8B4FF' } : {}"
                v-html="renderMarkdown(message.content)"
              />
              <div v-else>{{ message.content }}</div>
            </div>

            <!-- User avatar -->
            <div
              v-if="message.role === 'user'"
              class="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
              :class="isUsingPacAgent
                ? 'bg-gradient-to-br from-purple-400 to-purple-600'
                : 'bg-gradient-to-br from-gold to-gold-dim'"
            >
              <span class="text-apex-dark font-bold text-sm">Y</span>
            </div>
          </div>

          <!-- Streaming indicator -->
          <div v-if="chat.isStreaming" class="flex gap-4">
            <div
              class="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
              :class="isUsingPacAgent ? 'agent-halo' : 'bg-gold/20'"
              :style="isUsingPacAgent ? {
                backgroundColor: 'rgba(255, 215, 0, 0.15)',
                boxShadow: '0 0 20px rgba(255, 215, 0, 0.3)'
              } : {}"
            >
              <span class="text-gold font-serif font-bold text-sm">{{ isUsingPacAgent ? '∴' : 'Au' }}</span>
            </div>
            <div :class="isUsingPacAgent ? 'pac-message' : 'bg-apex-card'" class="rounded-2xl px-4 py-3">
              <div class="flex items-center gap-2" :class="isUsingPacAgent ? 'text-purple-300' : 'text-gray-400'">
                <!-- Tool execution indicator -->
                <template v-if="chat.currentToolExecution">
                  <span class="text-gold">🔧</span>
                  <span class="text-sm">Using {{ chat.currentToolExecution.name }}...</span>
                </template>
                <!-- Regular thinking indicator -->
                <template v-else>
                  <div class="flex gap-1">
                    <span class="w-2 h-2 rounded-full animate-bounce" :class="isUsingPacAgent ? 'bg-purple-400' : 'bg-gold'" style="animation-delay: 0ms"></span>
                    <span class="w-2 h-2 rounded-full animate-bounce" :class="isUsingPacAgent ? 'bg-purple-400' : 'bg-gold'" style="animation-delay: 150ms"></span>
                    <span class="w-2 h-2 rounded-full animate-bounce" :class="isUsingPacAgent ? 'bg-purple-400' : 'bg-gold'" style="animation-delay: 300ms"></span>
                  </div>
                  <span class="text-sm">Thinking...</span>
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Input Area -->
      <div
        class="border-t p-4 transition-all"
        :class="isUsingPacAgent ? 'border-purple-500/30' : 'border-apex-border'"
        @click="showFilePicker = false"
      >
        <form @submit.prevent="handleSubmit" class="max-w-3xl mx-auto">
          <!-- Attached Files Preview -->
          <div v-if="attachedFiles.length > 0" class="flex flex-wrap gap-2 mb-2">
            <div
              v-for="file in attachedFiles"
              :key="file.id"
              class="flex items-center gap-1.5 bg-apex-darker border border-apex-border rounded-lg px-2.5 py-1 text-sm"
            >
              <span v-if="file.file_type === 'image'" class="text-xs">&#x1F5BC;</span>
              <span v-else class="text-xs">&#x1F4C4;</span>
              <span class="text-gray-300 max-w-[120px] truncate">{{ file.name }}</span>
              <button
                @click="removeAttachment(file.id)"
                class="text-gray-500 hover:text-red-400 ml-1"
                type="button"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          <div class="flex gap-3">
            <!-- Attach File Button -->
            <div class="relative" @click.stop>
              <button
                type="button"
                @click="toggleFilePicker"
                class="p-2.5 rounded-lg transition-colors"
                :class="attachedFiles.length > 0 ? 'text-gold' : 'text-gray-500 hover:text-gray-300'"
                title="Attach file from Vault"
                :disabled="!auth.isAuthenticated"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                </svg>
              </button>

              <!-- Vault File Picker Dropdown -->
              <div
                v-if="showFilePicker"
                class="absolute bottom-full left-0 mb-2 w-72 bg-apex-dark border border-apex-border rounded-lg shadow-xl z-50 max-h-64 overflow-y-auto"
              >
                <div class="p-2 border-b border-apex-border">
                  <span class="text-xs text-gray-400 font-medium">Attach from Vault</span>
                </div>
                <div v-if="loadingVaultFiles" class="p-4 text-center text-gray-400 text-sm">
                  Loading files...
                </div>
                <div v-else-if="vaultFiles.length === 0" class="p-4 text-center text-gray-500 text-sm">
                  No files in vault
                </div>
                <div v-else>
                  <button
                    v-for="file in vaultFiles"
                    :key="file.id"
                    @click="attachFile(file)"
                    type="button"
                    class="w-full text-left px-3 py-2 hover:bg-apex-darker flex items-center gap-2 text-sm transition-colors"
                    :class="{ 'opacity-50': attachedFiles.some(f => f.id === file.id) }"
                  >
                    <span v-if="file.file_type === 'image'" class="text-xs">&#x1F5BC;</span>
                    <span v-else-if="file.file_type === 'code'" class="text-xs">&#x2697;&#xFE0F;</span>
                    <span v-else class="text-xs">&#x1F4C4;</span>
                    <span class="truncate text-gray-300">{{ file.name || file.original_filename }}</span>
                    <span class="text-xs text-gray-500 ml-auto shrink-0">{{ file.file_type }}</span>
                  </button>
                </div>
              </div>
            </div>

            <input
              ref="inputRef"
              v-model="inputMessage"
              type="text"
              :placeholder="!auth.isAuthenticated ? 'Sign in to start chatting...' : (isUsingPacAgent ? 'Speak to the Stone...' : 'Message ApexAurum...')"
              class="input flex-1"
              :class="isUsingPacAgent ? 'pac-input' : ''"
              :style="isUsingPacAgent ? {
                background: 'rgba(26, 10, 46, 0.8)',
                borderColor: 'rgba(255, 215, 0, 0.2)',
              } : {}"
              :disabled="chat.isStreaming || !auth.isAuthenticated"
            />
            <button
              type="submit"
              class="px-6 rounded-lg font-medium transition-all"
              :class="isUsingPacAgent ? '' : 'btn-primary'"
              :style="isUsingPacAgent ? {
                background: 'rgba(255, 215, 0, 0.15)',
                border: '1px solid rgba(255, 215, 0, 0.4)',
                color: '#FFD700',
                boxShadow: '0 0 20px rgba(255, 215, 0, 0.2)'
              } : {}"
              :disabled="!inputMessage.trim() || chat.isStreaming || !auth.isAuthenticated"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
              </svg>
            </button>
          </div>
          <p class="text-xs mt-2 text-center" :class="isUsingPacAgent ? 'text-purple-300/60' : 'text-gray-500'">
            <template v-if="isUsingPacAgent">
              <span class="text-gold">∴ {{ actualAgentId }}-Ω ∴</span> ·
              <span class="text-purple-300/80">{{ chat.availableModels.find(m => m.id === chat.selectedModel)?.name || 'Sonnet 4' }}</span>
              <span v-if="chat.toolsEnabled" class="text-gold"> · 🔧</span>
            </template>
            <template v-else>
              <span class="text-gold">{{ selectedAgent }}</span> ·
              <span class="text-gray-400">{{ chat.availableModels.find(m => m.id === chat.selectedModel)?.name || 'Sonnet 4' }}</span>
              <span v-if="chat.toolsEnabled" class="text-gold"> · 🔧 Tools</span>
            </template>
          </p>
        </form>
      </div>
    </main>

    <!-- Context Menu (Desktop: fixed position, Mobile: bottom sheet) -->
    <Teleport to="body">
      <!-- Backdrop -->
      <Transition name="fade">
        <div
          v-if="contextMenu.visible"
          @click="hideContextMenu"
          class="fixed inset-0 z-40"
          :class="isMobile ? 'bg-black/50' : ''"
        ></div>
      </Transition>

      <!-- Desktop Context Menu -->
      <Transition name="fade">
        <div
          v-if="contextMenu.visible && !isMobile"
          class="fixed bg-apex-card border border-apex-border rounded-lg shadow-xl py-1 z-50 min-w-[160px]"
          :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        >
          <button
            @click="handleContextAction('rename')"
            class="w-full px-4 py-2 text-left text-sm hover:bg-white/5 flex items-center gap-2"
          >
            <span class="text-gray-400">✏️</span> Rename
          </button>
          <button
            @click="handleContextAction('favorite')"
            class="w-full px-4 py-2 text-left text-sm hover:bg-white/5 flex items-center gap-2"
          >
            <span class="text-gray-400">{{ contextMenu.conv?.favorite ? '☆' : '★' }}</span>
            {{ contextMenu.conv?.favorite ? 'Unfavorite' : 'Favorite' }}
          </button>
          <button
            @click="handleContextAction('export')"
            class="w-full px-4 py-2 text-left text-sm hover:bg-white/5 flex items-center gap-2"
          >
            <span class="text-gray-400">📤</span> Export
          </button>
          <button
            @click="handleContextAction('archive')"
            class="w-full px-4 py-2 text-left text-sm hover:bg-white/5 flex items-center gap-2"
          >
            <span class="text-gray-400">📦</span> Archive
          </button>
          <hr class="border-apex-border my-1" />
          <button
            @click="handleContextAction('delete')"
            class="w-full px-4 py-2 text-left text-sm hover:bg-red-500/10 text-red-400 flex items-center gap-2"
          >
            <span>🗑️</span> Delete
          </button>
        </div>
      </Transition>

      <!-- Mobile Bottom Sheet -->
      <Transition name="slide-up">
        <div
          v-if="contextMenu.visible && isMobile"
          class="fixed bottom-0 left-0 right-0 bg-apex-card border-t border-apex-border rounded-t-2xl shadow-2xl z-50 pb-safe"
        >
          <!-- Handle bar -->
          <div class="flex justify-center py-3">
            <div class="w-10 h-1 bg-gray-600 rounded-full"></div>
          </div>

          <!-- Title -->
          <div class="px-4 pb-3 border-b border-apex-border">
            <h3 class="font-medium text-sm text-gray-300 truncate">
              {{ contextMenu.conv?.title || 'Conversation' }}
            </h3>
          </div>

          <!-- Actions -->
          <div class="py-2">
            <button
              @click="handleContextAction('rename')"
              class="w-full px-6 py-4 text-left flex items-center gap-4 active:bg-white/5"
            >
              <span class="text-xl">✏️</span>
              <span>Rename</span>
            </button>
            <button
              @click="handleContextAction('favorite')"
              class="w-full px-6 py-4 text-left flex items-center gap-4 active:bg-white/5"
            >
              <span class="text-xl">{{ contextMenu.conv?.favorite ? '☆' : '★' }}</span>
              <span>{{ contextMenu.conv?.favorite ? 'Unfavorite' : 'Favorite' }}</span>
            </button>
            <button
              @click="handleContextAction('export')"
              class="w-full px-6 py-4 text-left flex items-center gap-4 active:bg-white/5"
            >
              <span class="text-xl">📤</span>
              <span>Export</span>
            </button>
            <button
              @click="handleContextAction('archive')"
              class="w-full px-6 py-4 text-left flex items-center gap-4 active:bg-white/5"
            >
              <span class="text-xl">📦</span>
              <span>Archive</span>
            </button>
            <hr class="border-apex-border my-2" />
            <button
              @click="handleContextAction('delete')"
              class="w-full px-6 py-4 text-left flex items-center gap-4 active:bg-red-500/10 text-red-400"
            >
              <span class="text-xl">🗑️</span>
              <span>Delete</span>
            </button>
          </div>

          <!-- Cancel button -->
          <div class="px-4 pb-4">
            <button
              @click="hideContextMenu"
              class="btn-ghost w-full py-3"
            >
              Cancel
            </button>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Export Modal -->
    <Teleport to="body">
      <div
        v-if="showExportModal"
        class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
        @click.self="showExportModal = false"
      >
        <div class="card w-80">
          <h3 class="text-lg font-bold mb-4">Export Conversation</h3>
          <div class="space-y-2">
            <button
              @click="handleExport('json')"
              class="btn-secondary w-full text-left flex items-center gap-3"
            >
              <span class="text-lg">📄</span>
              <div>
                <div class="font-medium">JSON</div>
                <div class="text-xs text-gray-500">Full data, re-importable</div>
              </div>
            </button>
            <button
              @click="handleExport('markdown')"
              class="btn-secondary w-full text-left flex items-center gap-3"
            >
              <span class="text-lg">📝</span>
              <div>
                <div class="font-medium">Markdown</div>
                <div class="text-xs text-gray-500">Readable, shareable</div>
              </div>
            </button>
            <button
              @click="handleExport('txt')"
              class="btn-secondary w-full text-left flex items-center gap-3"
            >
              <span class="text-lg">📃</span>
              <div>
                <div class="font-medium">Plain Text</div>
                <div class="text-xs text-gray-500">Simple format</div>
              </div>
            </button>
          </div>
          <button
            @click="showExportModal = false"
            class="btn-ghost w-full mt-4"
          >
            Cancel
          </button>
        </div>
      </div>
    </Teleport>

    <!-- Fork Modal (The Multiverse) -->
    <Teleport to="body">
      <div
        v-if="showForkModal"
        class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
        @click.self="showForkModal = false"
      >
        <div class="card w-96 max-w-[90vw]">
          <h3 class="text-lg font-bold mb-2 flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-purple-400" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M7.707 3.293a1 1 0 010 1.414L5.414 7H11a7 7 0 017 7v2a1 1 0 11-2 0v-2a5 5 0 00-5-5H5.414l2.293 2.293a1 1 0 11-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clip-rule="evenodd" />
            </svg>
            Create Branch
          </h3>
          <p class="text-gray-400 text-sm mb-4">
            Fork this conversation from the selected message. The new branch will contain all messages up to this point.
          </p>

          <div class="mb-4">
            <label class="block text-sm text-gray-400 mb-1">Branch Label (optional)</label>
            <input
              v-model="forkLabel"
              type="text"
              placeholder="e.g., What if we tried..."
              class="input w-full"
              maxlength="100"
              @keyup.enter="handleFork"
            />
          </div>

          <div class="flex gap-3">
            <button
              @click="showForkModal = false"
              class="btn-ghost flex-1"
              :disabled="forking"
            >
              Cancel
            </button>
            <button
              @click="handleFork"
              class="btn-primary flex-1 bg-purple-600 hover:bg-purple-500"
              :disabled="forking"
            >
              <span v-if="forking">Creating...</span>
              <span v-else>Create Branch</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* Bounce animation for typing indicator */
@keyframes bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}

/* Fade transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Slide up transition for bottom sheet */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: transform 0.3s ease;
}
.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
}

/* Safe area padding for bottom sheet */
.pb-safe {
  padding-bottom: max(1rem, env(safe-area-inset-bottom));
}
</style>
