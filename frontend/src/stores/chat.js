import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

export const useChatStore = defineStore('chat', () => {
  // State
  const conversations = ref([])
  const currentConversation = ref(null)
  const messages = ref([])
  const isStreaming = ref(false)
  const streamingContent = ref('')

  // ═══════════════════════════════════════════════════════════════════════════════
  // PROVIDER SELECTION - The Many Flames (Dev Mode Feature)
  // ═══════════════════════════════════════════════════════════════════════════════
  const availableProviders = ref([])
  const selectedProvider = ref(localStorage.getItem('apexaurum_provider') || 'anthropic')

  // ═══════════════════════════════════════════════════════════════════════════════
  // MODEL SELECTION - Unleash the Stones
  // ═══════════════════════════════════════════════════════════════════════════════
  const availableModels = ref([])
  const defaultModel = ref('claude-sonnet-4-5-20250929')
  const selectedModel = ref(localStorage.getItem('apexaurum_selected_model') || 'claude-sonnet-4-5-20250929')
  const maxTokens = ref(parseInt(localStorage.getItem('apexaurum_max_tokens')) || 8192)

  // ═══════════════════════════════════════════════════════════════════════════════
  // TOOLS - The Athanor's Hands
  // ═══════════════════════════════════════════════════════════════════════════════
  const toolsEnabled = ref(localStorage.getItem('apexaurum_tools_enabled') === 'true')
  const currentToolExecution = ref(null)  // Track currently executing tool

  // Getters
  const sortedConversations = computed(() => {
    const convs = conversations.value || []
    if (!Array.isArray(convs)) return []
    return [...convs].sort((a, b) =>
      new Date(b.updated_at) - new Date(a.updated_at)
    )
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // PROVIDER ACTIONS - The Many Flames
  // ═══════════════════════════════════════════════════════════════════════════════

  async function fetchProviders() {
    try {
      const response = await api.get('/api/v1/chat/providers')
      availableProviders.value = response.data.providers || []

      // If selected provider is not available, reset to anthropic
      const providerIds = availableProviders.value.map(p => p.id)
      if (!providerIds.includes(selectedProvider.value)) {
        selectedProvider.value = 'anthropic'
        localStorage.setItem('apexaurum_provider', 'anthropic')
      }
    } catch (e) {
      console.error('Failed to fetch providers:', e)
      // Keep defaults
    }
  }

  async function setProvider(providerId) {
    selectedProvider.value = providerId
    localStorage.setItem('apexaurum_provider', providerId)
    // Refresh models for the new provider
    await fetchModels()
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // MODEL ACTIONS
  // ═══════════════════════════════════════════════════════════════════════════════

  async function fetchModels() {
    try {
      // Fetch models for the selected provider
      const response = await api.get(`/api/v1/chat/models?provider=${selectedProvider.value}`)
      availableModels.value = response.data.models || []
      defaultModel.value = response.data.default || 'claude-sonnet-4-5-20250929'

      // If selected model is not in available models, reset to default
      const modelIds = availableModels.value.map(m => m.id)
      if (!modelIds.includes(selectedModel.value)) {
        selectedModel.value = defaultModel.value
        localStorage.setItem('apexaurum_selected_model', defaultModel.value)
      }
    } catch (e) {
      console.error('Failed to fetch models:', e)
      // Keep defaults
    }
  }

  function setSelectedModel(modelId) {
    selectedModel.value = modelId
    localStorage.setItem('apexaurum_selected_model', modelId)
  }

  function setMaxTokens(tokens) {
    maxTokens.value = tokens
    localStorage.setItem('apexaurum_max_tokens', tokens.toString())
  }

  function setToolsEnabled(enabled) {
    toolsEnabled.value = enabled
    localStorage.setItem('apexaurum_tools_enabled', enabled.toString())
  }

  // Actions
  async function fetchConversations() {
    try {
      const response = await api.get('/api/v1/chat/conversations')
      conversations.value = response.data.conversations || []
    } catch (e) {
      console.error('Failed to fetch conversations:', e)
      conversations.value = []
    }
  }

  async function loadConversation(id) {
    try {
      const response = await api.get(`/api/v1/chat/conversations/${id}`)
      currentConversation.value = response.data
      messages.value = response.data.messages || []
    } catch (e) {
      console.error('Failed to load conversation:', e)
      currentConversation.value = null
      messages.value = []
    }
  }

  async function createConversation() {
    currentConversation.value = null
    messages.value = []
  }

  async function sendMessage(content, agent = 'AZOTH', model = null, usePac = false, fileIds = undefined) {
    // Use selected model if not specified
    const useModel = model || selectedModel.value || defaultModel.value
    // Add user message immediately
    messages.value.push({
      id: Date.now().toString(),
      role: 'user',
      content,
      created_at: new Date().toISOString()
    })

    // Start streaming
    isStreaming.value = true
    streamingContent.value = ''

    // Create placeholder for assistant message
    const assistantMsgId = Date.now().toString() + '-assistant'
    messages.value.push({
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString()
    })

    try {
      // Ensure API URL has https:// prefix
      let apiUrl = import.meta.env.VITE_API_URL || ''
      if (apiUrl && !apiUrl.startsWith('http://') && !apiUrl.startsWith('https://')) {
        apiUrl = 'https://' + apiUrl
      }
      const token = localStorage.getItem('accessToken')

      const response = await fetch(`${apiUrl}/api/v1/chat/message`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token && { 'Authorization': `Bearer ${token}` })
        },
        body: JSON.stringify({
          message: content,
          conversation_id: currentConversation.value?.id,
          provider: selectedProvider.value,
          model: useModel,
          agent,
          stream: true,
          use_pac: usePac,
          max_tokens: maxTokens.value,
          use_tools: toolsEnabled.value,
          ...(fileIds && { file_ids: fileIds }),
        })
      })

      if (!response.ok) {
        // Try to parse error details from response
        let errorMessage = `HTTP ${response.status}`
        try {
          const errorData = await response.json()
          if (errorData.detail) {
            // Handle structured error responses (402/403)
            if (typeof errorData.detail === 'object') {
              const detail = errorData.detail
              if (detail.error === 'trial_expired') {
                errorMessage = `⏳ Your free trial has expired. Subscribe to continue your journey.\n\n[Upgrade your plan](/billing) to keep using ApexAurum.`
              } else if (detail.error === 'opus_limit') {
                errorMessage = `📊 ${detail.message || 'Opus message limit reached for this month.'}`
              } else if (detail.error === 'model_not_allowed') {
                errorMessage = `🔒 ${detail.message || 'This model requires a higher tier.'}\n\nTry switching to Haiku or Sonnet in settings, or upgrade your plan.`
              } else if (detail.error === 'tools_not_allowed') {
                errorMessage = `🔧 ${detail.message || 'Tools require a Pro subscription.'}\n\nUpgrade to unlock AI tools.`
              } else if (detail.error === 'usage_limit') {
                errorMessage = `📊 ${detail.message || 'You\'ve reached your message limit.'}\n\nUpgrade your plan or purchase credits to continue.`
              } else if (detail.error === 'multi_provider_not_allowed') {
                errorMessage = `🌐 ${detail.message || 'Multi-provider LLMs require Adept tier.'}`
              } else {
                errorMessage = detail.message || JSON.stringify(detail)
              }
            } else {
              errorMessage = errorData.detail
            }
          }
        } catch {
          // Couldn't parse JSON, use status text
          errorMessage = `${response.status}: ${response.statusText}`
        }
        throw new Error(errorMessage)
      }

      // Read the SSE stream
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Process complete SSE messages (ending with \n\n)
        const lines = buffer.split('\n\n')
        buffer = lines.pop() || '' // Keep incomplete message in buffer

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue

          try {
            const data = JSON.parse(line.slice(6))

            if (data.type === 'token' && data.content) {
              // Append token to streaming content and message
              streamingContent.value += data.content
              const msg = messages.value.find(m => m.id === assistantMsgId)
              if (msg) msg.content += data.content
            } else if (data.type === 'start' && data.conversation_id) {
              // Update conversation ID if new
              if (!currentConversation.value) {
                currentConversation.value = { id: data.conversation_id }
              }
            } else if (data.type === 'tool_start') {
              // Tool use starting
              currentToolExecution.value = { name: data.tool_name, id: data.tool_id }
              const msg = messages.value.find(m => m.id === assistantMsgId)
              if (msg) {
                msg.content += `\n\n🔧 **Using tool: ${data.tool_name}...**\n`
              }
            } else if (data.type === 'tool_executing') {
              // Tool execution in progress
              currentToolExecution.value = { name: data.name, status: 'executing' }
            } else if (data.type === 'tool_result') {
              // Tool result received
              const msg = messages.value.find(m => m.id === assistantMsgId)
              if (msg) {
                const status = data.is_error ? '❌' : '✅'
                const resultPreview = typeof data.result === 'string'
                  ? data.result.slice(0, 500)
                  : JSON.stringify(data.result, null, 2).slice(0, 500)
                msg.content += `${status} **${data.name}** result:\n\`\`\`\n${resultPreview}\n\`\`\`\n\n`
              }
              currentToolExecution.value = null
            } else if (data.type === 'error') {
              throw new Error(data.message || 'Stream error')
            }
          } catch (parseError) {
            console.warn('Failed to parse SSE:', line, parseError)
          }
        }
      }

      // Fetch conversations if we got a new one
      if (currentConversation.value?.id) {
        await fetchConversations()
      }

    } catch (e) {
      console.error('Chat error:', e)
      // Update assistant message to show friendly error
      const msg = messages.value.find(m => m.id === assistantMsgId)
      if (msg) {
        msg.role = 'system'
        // Check if it's a billing/permission error (has emoji)
        if (e.message.match(/^[🔒🔧📊🌐⏳]/)) {
          msg.content = e.message
        } else {
          msg.content = `⚠️ Something went wrong:\n\n${e.message}\n\nPlease try again or refresh the page.`
        }
      }
    } finally {
      isStreaming.value = false
      streamingContent.value = ''
    }
  }

  async function deleteConversation(id) {
    await api.delete(`/api/v1/chat/conversations/${id}`)
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (currentConversation.value?.id === id) {
      currentConversation.value = null
      messages.value = []
    }
  }

  async function updateConversation(id, updates) {
    await api.patch(`/api/v1/chat/conversations/${id}`, updates)
    const conv = conversations.value.find(c => c.id === id)
    if (conv) {
      Object.assign(conv, updates)
    }
  }

  async function toggleFavorite(id) {
    const conv = conversations.value.find(c => c.id === id)
    if (conv) {
      await updateConversation(id, { favorite: !conv.favorite })
    }
  }

  async function archiveConversation(id) {
    const conv = conversations.value.find(c => c.id === id)
    if (conv) {
      await updateConversation(id, { archived: !conv.archived })
      // Remove from list if archived (we show non-archived by default)
      if (!conv.archived) {
        conversations.value = conversations.value.filter(c => c.id !== id)
      }
    }
  }

  async function exportConversation(id, format = 'json') {
    const apiUrl = import.meta.env.VITE_API_URL || ''
    const token = localStorage.getItem('accessToken')

    const response = await fetch(`${apiUrl}/api/v1/chat/conversations/${id}/export?format=${format}`, {
      headers: token ? { 'Authorization': `Bearer ${token}` } : {}
    })

    if (!response.ok) throw new Error('Export failed')

    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url

    // Get filename from Content-Disposition header or generate one
    const contentDisposition = response.headers.get('Content-Disposition')
    let filename = `conversation.${format === 'markdown' ? 'md' : format}`
    if (contentDisposition) {
      const match = contentDisposition.match(/filename="?(.+?)"?$/)
      if (match) filename = match[1]
    }

    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // BRANCHING (THE MULTIVERSE) - Fork conversations at any message point
  // ═══════════════════════════════════════════════════════════════════════════════

  async function forkConversation(conversationId, messageId, label = null) {
    try {
      const response = await api.post(
        `/api/v1/chat/conversations/${conversationId}/fork`,
        { message_id: messageId, label }
      )
      // Refresh conversations list to show new branch
      await fetchConversations()
      return response.data
    } catch (e) {
      console.error('Failed to fork conversation:', e)
      throw e
    }
  }

  async function getBranches(conversationId) {
    try {
      const response = await api.get(
        `/api/v1/chat/conversations/${conversationId}/branches`
      )
      return response.data
    } catch (e) {
      console.error('Failed to get branches:', e)
      return { parent: null, branches: [], branch_count: 0 }
    }
  }

  return {
    conversations,
    currentConversation,
    messages,
    isStreaming,
    streamingContent,
    sortedConversations,
    // Provider selection (The Many Flames - Dev Mode)
    availableProviders,
    selectedProvider,
    fetchProviders,
    setProvider,
    // Model selection (Unleash the Stones)
    availableModels,
    defaultModel,
    selectedModel,
    maxTokens,
    fetchModels,
    setSelectedModel,
    setMaxTokens,
    // Tools (The Athanor's Hands)
    toolsEnabled,
    currentToolExecution,
    setToolsEnabled,
    // Core actions
    fetchConversations,
    loadConversation,
    createConversation,
    sendMessage,
    deleteConversation,
    updateConversation,
    toggleFavorite,
    archiveConversation,
    exportConversation,
    // Branching (The Multiverse)
    forkConversation,
    getBranches,
  }
})
