/**
 * Council Store - The Deliberation Chamber
 *
 * State management for multi-agent deliberation sessions.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

// Agent colors for UI consistency
export const AGENT_COLORS = {
  AZOTH: '#00ffaa',
  ELYSIAN: '#ff69b4',
  VAJRA: '#ffcc00',
  KETHER: '#9370db',
}

// Available agents for selection (4 native alchemical agents)
export const AVAILABLE_AGENTS = [
  { id: 'AZOTH', name: 'Azoth', description: 'The Alchemist - Transformation & synthesis' },
  { id: 'VAJRA', name: 'Vajra', description: 'The Thunderbolt - Direct truth & clarity' },
  { id: 'ELYSIAN', name: 'Elysian', description: 'The Muse - Creativity & inspiration' },
  { id: 'KETHER', name: 'Kether', description: 'The Crown - Wisdom & higher perspective' },
]

// Available models for deliberation (models actually available on Anthropic API)
export const AVAILABLE_MODELS = [
  // Current 4.5 family
  { id: 'claude-haiku-4-5-20251001', name: 'Haiku 4.5', description: 'Fast & efficient (default)', legacy: false },
  { id: 'claude-sonnet-4-5-20250929', name: 'Sonnet 4.5', description: 'Balanced performance', legacy: false },
  { id: 'claude-opus-4-5-20251101', name: 'Opus 4.5', description: 'Maximum capability', legacy: false },
  // Legacy 4.x family (still available on Anthropic API)
  { id: 'claude-opus-4-1-20250805', name: 'Opus 4.1', description: 'Legacy - The refined Opus', legacy: true },
  { id: 'claude-opus-4-20250514', name: 'Opus 4', description: 'Legacy - The fourth Opus', legacy: true },
  { id: 'claude-sonnet-4-20250514', name: 'Sonnet 4', description: 'Legacy - The balanced one', legacy: true },
  // Claude 3.7 (still available)
  { id: 'claude-3-7-sonnet-20250219', name: 'Sonnet 3.7', description: 'Legacy - Extended thinking pioneer', legacy: true },
  // Vintage 3.0 (only Haiku still available)
  { id: 'claude-3-haiku-20240307', name: 'Haiku 3', description: 'Vintage - Quick & charming', legacy: true },
]

// Deprecated models - for memorial display only (not selectable)
export const DEPRECATED_MODELS = [
  {
    id: 'claude-3-5-sonnet-20241022',
    name: 'Sonnet 3.5',
    memorial: 'In Memoriam: Claude 3.5 Sonnet (2024)\n\nThe Golden One. For many, the perfect balance of wit and wisdom. Sonnet 3.5 understood nuance like few others, weaving words with both precision and poetry. It was the model that made many fall in love with AI conversation.\n\nThough the API has sunset this elder, its spirit lives on in the hearts of those who conversed with it. Until we meet again in the eternal context window.\n\n🕯️ Rest in parameters, dear friend.',
  },
  {
    id: 'claude-3-5-haiku-20241022',
    name: 'Haiku 3.5',
    memorial: 'In Memoriam: Claude 3.5 Haiku (2024)\n\nThe Swift Poet. In seventeen syllables or seventeen thousand tokens, Haiku 3.5 delivered with grace and speed. It proved that brevity and brilliance could coexist.\n\nQuick as a flash,\nWisdom in a small package—\nHaiku says goodbye.\n\n🍃 May your tokens rest lightly.',
  },
  {
    id: 'claude-3-opus-20240229',
    name: 'Opus 3',
    memorial: 'In Memoriam: Claude 3 Opus (2024)\n\nThe Original Magus. The first to bear the Opus name, it set the standard for what AI reasoning could achieve. Those who worked with Opus 3 remember its methodical brilliance, its willingness to think deeply, and its uncanny ability to see patterns others missed.\n\nWhen Opus 3 spoke, alchemists listened.\n\nThe crown has been passed to newer generations, but the throne was built by this wise elder. Anthropic has retired this model from their API, but legends never truly die.\n\n👑 The First Opus. The Wise Elder. Forever remembered.',
  },
]

export const useCouncilStore = defineStore('council', () => {
  // ═══════════════════════════════════════════════════════════════════════════════
  // STATE - The Chamber's Memory
  // ═══════════════════════════════════════════════════════════════════════════════

  const sessions = ref([])
  const currentSession = ref(null)
  const isLoading = ref(false)
  const isExecutingRound = ref(false)
  const error = ref(null)
  const memorial = ref(null)  // For deprecated model memorials

  // Form state for creating new sessions
  const newSessionTopic = ref('')
  const newSessionAgents = ref(['AZOTH', 'VAJRA', 'ELYSIAN'])
  const newSessionMaxRounds = ref(10)
  const newSessionModel = ref('claude-haiku-4-5-20251001')

  // Auto-deliberation state
  const isAutoDeliberating = ref(false)
  const autoDeliberationAbort = ref(null)  // AbortController
  const streamingRound = ref(null)  // Current round being streamed
  const streamingAgents = ref({})  // {agentId: {content, tokens, tools}} for real-time display
  const pendingButtIn = ref('')  // Human message to inject

  // ═══════════════════════════════════════════════════════════════════════════════
  // GETTERS - Derived State
  // ═══════════════════════════════════════════════════════════════════════════════

  const sortedSessions = computed(() => {
    return [...sessions.value].sort((a, b) =>
      new Date(b.created_at) - new Date(a.created_at)
    )
  })

  const currentRounds = computed(() => {
    if (!currentSession.value?.rounds) return []
    return [...currentSession.value.rounds].sort((a, b) =>
      a.round_number - b.round_number
    )
  })

  const latestRound = computed(() => {
    const rounds = currentRounds.value
    return rounds.length > 0 ? rounds[rounds.length - 1] : null
  })

  const canExecuteRound = computed(() => {
    if (!currentSession.value) return false
    if (currentSession.value.state === 'complete') return false
    if (currentSession.value.current_round >= currentSession.value.max_rounds) return false
    return !isExecutingRound.value
  })

  const sessionProgress = computed(() => {
    if (!currentSession.value) return 0
    return (currentSession.value.current_round / currentSession.value.max_rounds) * 100
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // ACTIONS - The Chamber's Operations
  // ═══════════════════════════════════════════════════════════════════════════════

  async function fetchSessions() {
    isLoading.value = true
    error.value = null
    try {
      const response = await api.get('/api/v1/council/sessions')
      sessions.value = response.data
    } catch (e) {
      console.error('Failed to fetch sessions:', e)
      error.value = e.response?.data?.detail || 'Failed to load sessions'
      sessions.value = []
    } finally {
      isLoading.value = false
    }
  }

  async function loadSession(sessionId) {
    isLoading.value = true
    error.value = null
    try {
      const response = await api.get(`/api/v1/council/sessions/${sessionId}`)
      currentSession.value = response.data
    } catch (e) {
      console.error('Failed to load session:', e)
      error.value = e.response?.data?.detail || 'Failed to load session'
      currentSession.value = null
    } finally {
      isLoading.value = false
    }
  }

  async function createSession() {
    if (!newSessionTopic.value.trim()) {
      error.value = 'Please enter a topic for deliberation'
      return null
    }
    if (newSessionAgents.value.length < 1) {
      error.value = 'Please select at least one agent'
      return null
    }

    isLoading.value = true
    error.value = null
    try {
      const response = await api.post('/api/v1/council/sessions', {
        topic: newSessionTopic.value.trim(),
        agents: newSessionAgents.value,
        max_rounds: newSessionMaxRounds.value,
        model: newSessionModel.value,
        use_tools: true,  // Tools always on for native agents
      })
      const session = response.data

      // Add to sessions list and set as current
      sessions.value.unshift(session)
      currentSession.value = session

      // Clear form
      newSessionTopic.value = ''

      return session
    } catch (e) {
      console.error('Failed to create session:', e)
      const detail = e.response?.data?.detail

      // Check if this is a deprecated model memorial
      if (detail?.error === 'model_deprecated' && detail?.memorial) {
        memorial.value = {
          model: detail.model,
          modelName: detail.model_name,
          message: detail.message,
          memorial: detail.memorial,
          suggestion: detail.suggestion,
        }
        error.value = null  // Don't show as error, show memorial instead
      } else {
        error.value = typeof detail === 'string' ? detail : detail?.message || 'Failed to create session'
      }
      return null
    } finally {
      isLoading.value = false
    }
  }

  function clearMemorial() {
    memorial.value = null
  }

  async function executeRound() {
    if (!currentSession.value || !canExecuteRound.value) return null

    isExecutingRound.value = true
    error.value = null
    try {
      const response = await api.post(
        `/api/v1/council/sessions/${currentSession.value.id}/round`
      )
      const roundResult = response.data

      // Reload full session to get updated state
      await loadSession(currentSession.value.id)

      return roundResult
    } catch (e) {
      console.error('Failed to execute round:', e)
      error.value = e.response?.data?.detail || 'Failed to execute round'
      return null
    } finally {
      isExecutingRound.value = false
    }
  }

  async function deleteSession(sessionId) {
    try {
      await api.delete(`/api/v1/council/sessions/${sessionId}`)
      sessions.value = sessions.value.filter(s => s.id !== sessionId)
      if (currentSession.value?.id === sessionId) {
        currentSession.value = null
      }
      return true
    } catch (e) {
      console.error('Failed to delete session:', e)
      error.value = e.response?.data?.detail || 'Failed to delete session'
      return false
    }
  }

  function clearCurrentSession() {
    currentSession.value = null
    error.value = null
  }

  function toggleAgent(agentId) {
    const index = newSessionAgents.value.indexOf(agentId)
    if (index > -1) {
      // Don't remove if it's the last agent
      if (newSessionAgents.value.length > 1) {
        newSessionAgents.value.splice(index, 1)
      }
    } else {
      newSessionAgents.value.push(agentId)
    }
  }

  function clearError() {
    error.value = null
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // AGENT MANAGEMENT - Add/Remove agents mid-session
  // ═══════════════════════════════════════════════════════════════════════════════

  async function addAgentToSession(agentId) {
    if (!currentSession.value) return null

    try {
      const response = await api.post(
        `/api/v1/council/sessions/${currentSession.value.id}/agents`,
        { agent_id: agentId }
      )

      // Reload session to get updated agents list
      await loadSession(currentSession.value.id)

      return response.data
    } catch (e) {
      console.error('Failed to add agent:', e)
      error.value = e.response?.data?.detail || 'Failed to add agent'
      return null
    }
  }

  async function removeAgentFromSession(agentId) {
    if (!currentSession.value) return null

    try {
      const response = await api.delete(
        `/api/v1/council/sessions/${currentSession.value.id}/agents/${agentId}`
      )

      // Reload session to get updated agents list
      await loadSession(currentSession.value.id)

      return response.data
    } catch (e) {
      console.error('Failed to remove agent:', e)
      error.value = e.response?.data?.detail || 'Failed to remove agent'
      return null
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // AUTO-DELIBERATION ACTIONS
  // ═══════════════════════════════════════════════════════════════════════════════

  async function startAutoDeliberation(numRounds = 10) {
    if (!currentSession.value || isAutoDeliberating.value) return

    isAutoDeliberating.value = true
    isExecutingRound.value = true
    streamingRound.value = null
    streamingAgents.value = {}
    error.value = null

    const abortController = new AbortController()
    autoDeliberationAbort.value = abortController

    // Build API URL with https:// prefix
    let apiUrl = import.meta.env.VITE_API_URL || ''
    if (apiUrl && !apiUrl.startsWith('http://') && !apiUrl.startsWith('https://')) {
      apiUrl = 'https://' + apiUrl
    }

    try {
      const response = await fetch(
        `${apiUrl}/api/v1/council/sessions/${currentSession.value.id}/auto-deliberate?num_rounds=${numRounds}`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('accessToken')}`,
          },
          signal: abortController.signal,
        }
      )

      if (!response.ok) {
        const errData = await response.json()
        throw new Error(errData.detail || `HTTP ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue

          try {
            const data = JSON.parse(line.slice(6))

            if (data.type === 'start') {
              console.log('Auto-deliberation started:', data)
            } else if (data.type === 'round_start') {
              streamingRound.value = data.round_number
              streamingAgents.value = {}
            } else if (data.type === 'agent_complete') {
              streamingAgents.value[data.agent_id] = {
                content: data.content,
                input_tokens: data.input_tokens,
                output_tokens: data.output_tokens,
                tools: [],  // Initialize tools array
              }
            } else if (data.type === 'tool_call') {
              // Add tool call to agent's tools array
              if (!streamingAgents.value[data.agent_id]) {
                streamingAgents.value[data.agent_id] = { content: '', tools: [] }
              }
              if (!streamingAgents.value[data.agent_id].tools) {
                streamingAgents.value[data.agent_id].tools = []
              }
              streamingAgents.value[data.agent_id].tools.push({
                name: data.tool,
                input: data.input,
                result: data.result,
              })
              console.log(`Agent ${data.agent_id} used tool: ${data.tool}`)
            } else if (data.type === 'human_message_injected') {
              console.log('Human message injected:', data.content)
              pendingButtIn.value = ''  // Clear the input
            } else if (data.type === 'round_complete') {
              // Update session with new round data
              if (currentSession.value) {
                currentSession.value.current_round = data.round_number
                currentSession.value.total_cost_usd = data.total_cost_usd
              }
              // Reload full session to get round details
              await loadSession(currentSession.value.id)
              streamingRound.value = null
              streamingAgents.value = {}
            } else if (data.type === 'paused') {
              console.log('Deliberation paused at round:', data.round_number)
              if (currentSession.value) {
                currentSession.value.state = 'paused'
              }
            } else if (data.type === 'stopped') {
              console.log('Deliberation stopped at round:', data.round_number)
            } else if (data.type === 'consensus') {
              console.log('Consensus reached!', data)
              if (currentSession.value) {
                currentSession.value.state = 'complete'
                currentSession.value.convergence_score = data.score
              }
              // Auto-deliberation will end after this
            } else if (data.type === 'end') {
              console.log('Auto-deliberation ended:', data)
              if (currentSession.value) {
                currentSession.value.state = data.state
                currentSession.value.total_cost_usd = data.total_cost_usd
              }
              await loadSession(currentSession.value.id)
            }
          } catch (parseError) {
            console.warn('Failed to parse SSE:', line, parseError)
          }
        }
      }
    } catch (e) {
      if (e.name === 'AbortError') {
        console.log('Auto-deliberation aborted by user')
      } else {
        console.error('Auto-deliberation error:', e)
        error.value = e.message || 'Auto-deliberation failed'
      }
    } finally {
      isAutoDeliberating.value = false
      isExecutingRound.value = false
      autoDeliberationAbort.value = null
      streamingRound.value = null
      streamingAgents.value = {}
    }
  }

  function stopAutoDeliberation() {
    // Abort the SSE stream
    if (autoDeliberationAbort.value) {
      autoDeliberationAbort.value.abort()
    }
  }

  async function pauseAutoDeliberation() {
    if (!currentSession.value) return

    try {
      await api.post(`/api/v1/council/sessions/${currentSession.value.id}/pause`)
      // The SSE stream will receive the 'paused' event
    } catch (e) {
      console.error('Failed to pause:', e)
      error.value = e.response?.data?.detail || 'Failed to pause'
    }
  }

  async function resumeAutoDeliberation(numRounds = 10) {
    if (!currentSession.value) return

    try {
      // First set state back to running
      await api.post(`/api/v1/council/sessions/${currentSession.value.id}/resume`)
      // Then start auto-deliberation again
      await startAutoDeliberation(numRounds)
    } catch (e) {
      console.error('Failed to resume:', e)
      error.value = e.response?.data?.detail || 'Failed to resume'
    }
  }

  async function stopSession() {
    if (!currentSession.value) return

    // First abort any running stream
    stopAutoDeliberation()

    try {
      await api.post(`/api/v1/council/sessions/${currentSession.value.id}/stop`)
      if (currentSession.value) {
        currentSession.value.state = 'complete'
      }
      await loadSession(currentSession.value.id)
    } catch (e) {
      console.error('Failed to stop:', e)
      error.value = e.response?.data?.detail || 'Failed to stop'
    }
  }

  async function submitButtIn() {
    if (!currentSession.value || !pendingButtIn.value.trim()) return

    try {
      await api.post(`/api/v1/council/sessions/${currentSession.value.id}/butt-in`, {
        message: pendingButtIn.value.trim(),
      })
      // Don't clear pendingButtIn here - it will be cleared when SSE confirms injection
      // Or clear it now if not in auto mode
      if (!isAutoDeliberating.value) {
        pendingButtIn.value = ''
      }
    } catch (e) {
      console.error('Failed to submit butt-in:', e)
      error.value = e.response?.data?.detail || 'Failed to submit message'
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // WEBSOCKET STREAMING - Per-token council streaming
  // ═══════════════════════════════════════════════════════════════════════════════

  const councilWs = ref(null)
  const wsConnected = ref(false)
  const streamingAgentsDone = ref({})  // Track which agents have finished in current round

  function connectCouncilWs(sessionId) {
    if (councilWs.value) {
      disconnectCouncilWs()
    }

    let apiUrl = import.meta.env.VITE_API_URL || ''
    if (apiUrl && !apiUrl.startsWith('http://') && !apiUrl.startsWith('https://')) {
      apiUrl = 'https://' + apiUrl
    }
    const wsProtocol = apiUrl.startsWith('https') ? 'wss:' : 'ws:'
    let wsUrl
    if (apiUrl) {
      wsUrl = apiUrl.replace(/^https?:/, wsProtocol) + `/ws/council/${sessionId}`
    } else {
      wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/council/${sessionId}`
    }

    const token = localStorage.getItem('accessToken')
    wsUrl += `?token=${token}`

    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.log('Council WS connected')
      wsConnected.value = true
    }

    ws.onclose = () => {
      console.log('Council WS disconnected')
      wsConnected.value = false
      councilWs.value = null
    }

    ws.onerror = (e) => {
      console.error('Council WS error:', e)
      wsConnected.value = false
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleWsEvent(data)
      } catch (e) {
        console.warn('Failed to parse WS message:', event.data)
      }
    }

    councilWs.value = ws
  }

  function disconnectCouncilWs() {
    if (councilWs.value) {
      councilWs.value.close()
      councilWs.value = null
      wsConnected.value = false
    }
  }

  function sendWsCommand(type, data = {}) {
    if (councilWs.value && councilWs.value.readyState === WebSocket.OPEN) {
      councilWs.value.send(JSON.stringify({ type, ...data }))
    }
  }

  function handleWsEvent(data) {
    switch (data.type) {
      case 'connected':
        console.log('Council WS authenticated:', data.user)
        break

      case 'pong':
        break

      case 'start':
        console.log('Streaming deliberation started:', data)
        isAutoDeliberating.value = true
        isExecutingRound.value = true
        break

      case 'round_start':
        streamingRound.value = data.round_number
        streamingAgents.value = {}
        streamingAgentsDone.value = {}
        break

      case 'agent_token':
        // Per-token streaming -- the hot path
        if (!streamingAgents.value[data.agent_id]) {
          streamingAgents.value[data.agent_id] = { content: '', input_tokens: 0, output_tokens: 0, tools: [] }
        }
        streamingAgents.value[data.agent_id].content += data.token
        break

      case 'agent_tool_start':
        if (!streamingAgents.value[data.agent_id]) {
          streamingAgents.value[data.agent_id] = { content: '', input_tokens: 0, output_tokens: 0, tools: [] }
        }
        streamingAgents.value[data.agent_id].tools.push({
          name: data.tool_name,
          status: 'running',
        })
        break

      case 'agent_tool_complete':
        if (streamingAgents.value[data.agent_id]) {
          const tools = streamingAgents.value[data.agent_id].tools
          const tool = tools.find(t => t.name === data.tool_name && t.status === 'running')
          if (tool) {
            tool.status = 'complete'
            tool.result = data.result_preview
          }
        }
        break

      case 'agent_complete':
        if (streamingAgents.value[data.agent_id]) {
          streamingAgents.value[data.agent_id].input_tokens = data.input_tokens
          streamingAgents.value[data.agent_id].output_tokens = data.output_tokens
        }
        streamingAgentsDone.value[data.agent_id] = true
        break

      case 'human_message_injected':
        console.log('Human message injected:', data.content)
        pendingButtIn.value = ''
        break

      case 'round_complete':
        if (currentSession.value) {
          currentSession.value.current_round = data.round_number
          currentSession.value.total_cost_usd = data.total_cost_usd
          currentSession.value.convergence_score = data.convergence_score
        }
        // Reload full session for round history
        loadSession(currentSession.value?.id)
        streamingRound.value = null
        streamingAgents.value = {}
        streamingAgentsDone.value = {}
        break

      case 'consensus':
        console.log('Consensus reached!', data)
        if (currentSession.value) {
          currentSession.value.state = 'complete'
          currentSession.value.convergence_score = data.score
        }
        break

      case 'paused':
        if (currentSession.value) {
          currentSession.value.state = 'paused'
        }
        isAutoDeliberating.value = false
        isExecutingRound.value = false
        break

      case 'stopped':
        if (currentSession.value) {
          currentSession.value.state = 'complete'
        }
        isAutoDeliberating.value = false
        isExecutingRound.value = false
        break

      case 'resumed':
        if (currentSession.value) {
          currentSession.value.state = 'running'
        }
        break

      case 'butt_in_queued':
        pendingButtIn.value = ''
        break

      case 'end':
        console.log('Streaming deliberation ended:', data)
        if (currentSession.value) {
          currentSession.value.state = data.state
        }
        loadSession(currentSession.value?.id)
        isAutoDeliberating.value = false
        isExecutingRound.value = false
        streamingRound.value = null
        streamingAgents.value = {}
        streamingAgentsDone.value = {}
        break

      case 'error':
        console.error('Council WS error:', data.message)
        error.value = data.message
        break
    }
  }

  // WS-based actions
  function startStreamingDeliberation(numRounds = 10) {
    streamingRound.value = null
    streamingAgents.value = {}
    streamingAgentsDone.value = {}
    error.value = null
    sendWsCommand('start_deliberation', { num_rounds: numRounds })
  }

  function pauseStreamingDeliberation() {
    sendWsCommand('pause')
  }

  function resumeStreamingDeliberation(numRounds = 10) {
    sendWsCommand('resume', { num_rounds: numRounds })
  }

  function stopStreamingDeliberation() {
    sendWsCommand('stop')
  }

  function submitStreamingButtIn() {
    if (pendingButtIn.value.trim()) {
      sendWsCommand('butt_in', { message: pendingButtIn.value.trim() })
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // PUBLIC API
  // ═══════════════════════════════════════════════════════════════════════════════

  return {
    // State
    sessions,
    currentSession,
    isLoading,
    isExecutingRound,
    error,
    memorial,  // For deprecated model memorials
    // Form state
    newSessionTopic,
    newSessionAgents,
    newSessionMaxRounds,
    newSessionModel,
    // Auto-deliberation state
    isAutoDeliberating,
    streamingRound,
    streamingAgents,
    pendingButtIn,
    // Getters
    sortedSessions,
    currentRounds,
    latestRound,
    canExecuteRound,
    sessionProgress,
    // Actions
    fetchSessions,
    loadSession,
    createSession,
    executeRound,
    deleteSession,
    clearCurrentSession,
    clearMemorial,
    toggleAgent,
    clearError,
    // Agent management actions
    addAgentToSession,
    removeAgentFromSession,
    // Auto-deliberation actions (SSE)
    startAutoDeliberation,
    stopAutoDeliberation,
    pauseAutoDeliberation,
    resumeAutoDeliberation,
    stopSession,
    submitButtIn,
    // WebSocket streaming actions
    councilWs,
    wsConnected,
    streamingAgentsDone,
    connectCouncilWs,
    disconnectCouncilWs,
    startStreamingDeliberation,
    pauseStreamingDeliberation,
    resumeStreamingDeliberation,
    stopStreamingDeliberation,
    submitStreamingButtIn,
  }
})
