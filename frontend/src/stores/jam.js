/**
 * Jam Session Store - The Village Band Frontend
 *
 * Pinia store for collaborative music composition sessions.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

export const useJamStore = defineStore('jam', () => {
  // ═══════════════════════════════════════════════════════════════════════════
  // State
  // ═══════════════════════════════════════════════════════════════════════════

  const sessions = ref([])
  const currentSession = ref(null)
  const isLoading = ref(false)
  const isCreating = ref(false)
  const isContributing = ref(false)
  const isFinalizing = ref(false)
  const isAutoJamming = ref(false)
  const autoJamAbort = ref(null)
  const error = ref(null)

  // For real-time collaboration visualization
  const liveContributions = ref([])  // Recent contributions for animation
  const streamingRound = ref(null)
  const streamingAgents = ref({})  // {agentId: {content, toolCalls}}
  const streamingEvents = ref([])  // All events for timeline display

  // ═══════════════════════════════════════════════════════════════════════════
  // Getters
  // ═══════════════════════════════════════════════════════════════════════════

  const activeSessions = computed(() =>
    sessions.value.filter(s => s.state === 'jamming' || s.state === 'forming')
  )

  const completedSessions = computed(() =>
    sessions.value.filter(s => s.state === 'complete')
  )

  const currentParticipants = computed(() =>
    currentSession.value?.participants || []
  )

  const currentTracks = computed(() =>
    currentSession.value?.tracks || []
  )

  const totalNotes = computed(() =>
    currentTracks.value.reduce((sum, track) => sum + (track.notes?.length || 0), 0)
  )

  const tracksByAgent = computed(() => {
    const grouped = {}
    for (const track of currentTracks.value) {
      if (!grouped[track.agent_id]) {
        grouped[track.agent_id] = []
      }
      grouped[track.agent_id].push(track)
    }
    return grouped
  })

  const tracksByRound = computed(() => {
    const grouped = {}
    for (const track of currentTracks.value) {
      const round = track.round_number || 1
      if (!grouped[round]) {
        grouped[round] = []
      }
      grouped[round].push(track)
    }
    return grouped
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Actions
  // ═══════════════════════════════════════════════════════════════════════════

  async function fetchSessions(limit = 20) {
    isLoading.value = true
    error.value = null

    try {
      const response = await api.get('/api/v1/jam/sessions', { params: { limit } })
      sessions.value = response.data
    } catch (err) {
      console.error('Failed to fetch jam sessions:', err)
      error.value = err.response?.data?.detail || 'Failed to load sessions'
    } finally {
      isLoading.value = false
    }
  }

  async function fetchSession(sessionId) {
    isLoading.value = true
    error.value = null

    try {
      const response = await api.get(`/api/v1/jam/sessions/${sessionId}`)
      currentSession.value = response.data
      return response.data
    } catch (err) {
      console.error('Failed to fetch session:', err)
      error.value = err.response?.data?.detail || 'Failed to load session'
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function createSession({
    title = 'Untitled Jam',
    style = '',
    tempo = 120,
    musicalKey = 'C',
    mode = 'jam',
    agents = ['AZOTH', 'ELYSIAN', 'VAJRA', 'KETHER'],
    maxRounds = 5,
    inspiration = ''
  } = {}) {
    isCreating.value = true
    error.value = null

    try {
      const response = await api.post('/api/v1/jam/sessions', {
        title,
        style,
        tempo,
        musical_key: musicalKey,
        mode,
        agents,
        max_rounds: maxRounds,
        inspiration
      })

      currentSession.value = response.data
      sessions.value.unshift({
        id: response.data.id,
        title: response.data.title,
        style: response.data.style,
        state: response.data.state,
        mode: response.data.mode,
        current_round: response.data.current_round,
        participant_count: response.data.participants.length,
        track_count: 0,
        created_at: response.data.created_at
      })

      return response.data
    } catch (err) {
      console.error('Failed to create session:', err)
      error.value = err.response?.data?.detail || 'Failed to create session'
      return null
    } finally {
      isCreating.value = false
    }
  }

  async function startSession(sessionId) {
    error.value = null

    try {
      const response = await api.post(`/api/v1/jam/sessions/${sessionId}/start`)

      if (currentSession.value?.id === sessionId) {
        currentSession.value.state = 'jamming'
        currentSession.value.current_round = 1
      }

      // Update in list too
      const idx = sessions.value.findIndex(s => s.id === sessionId)
      if (idx !== -1) {
        sessions.value[idx].state = 'jamming'
      }

      return response.data
    } catch (err) {
      console.error('Failed to start session:', err)
      error.value = err.response?.data?.detail || 'Failed to start session'
      return null
    }
  }

  async function contribute(sessionId, { notes, description, role }) {
    isContributing.value = true
    error.value = null

    try {
      // Build note objects with timing
      const noteObjects = notes.map((note, idx) => ({
        note: String(note),
        time: idx * 0.5,
        duration: 0.5,
        velocity: 100
      }))

      const response = await api.post(`/api/v1/jam/sessions/${sessionId}/contribute`, {
        agent_id: 'USER',  // User contributions
        notes: noteObjects,
        description,
        role
      })

      // Add to live contributions for animation
      liveContributions.value.push({
        agent_id: 'USER',
        notes: notes,
        description,
        timestamp: Date.now()
      })

      // Refresh session to get updated tracks
      await fetchSession(sessionId)

      return response.data
    } catch (err) {
      console.error('Failed to contribute:', err)
      error.value = err.response?.data?.detail || 'Failed to contribute'
      return null
    } finally {
      isContributing.value = false
    }
  }

  async function advanceRound(sessionId) {
    error.value = null

    try {
      const response = await api.post(`/api/v1/jam/sessions/${sessionId}/next-round`)

      if (currentSession.value?.id === sessionId) {
        currentSession.value.current_round = response.data.round
      }

      return response.data
    } catch (err) {
      console.error('Failed to advance round:', err)
      error.value = err.response?.data?.detail || 'Failed to advance round'
      return null
    }
  }

  async function finalizeSession(sessionId, { audioInfluence = 0.5, styleOverride, titleOverride } = {}) {
    isFinalizing.value = true
    error.value = null

    try {
      const response = await api.post(`/api/v1/jam/sessions/${sessionId}/finalize`, {
        audio_influence: audioInfluence,
        style_override: styleOverride,
        title_override: titleOverride
      })

      if (currentSession.value?.id === sessionId) {
        currentSession.value.state = 'complete'
        currentSession.value.final_music_task_id = response.data.music_task_id
      }

      // Update in list
      const idx = sessions.value.findIndex(s => s.id === sessionId)
      if (idx !== -1) {
        sessions.value[idx].state = 'complete'
      }

      return response.data
    } catch (err) {
      console.error('Failed to finalize:', err)
      error.value = err.response?.data?.detail || 'Failed to finalize session'
      return null
    } finally {
      isFinalizing.value = false
    }
  }

  async function deleteSession(sessionId) {
    error.value = null

    try {
      await api.delete(`/api/v1/jam/sessions/${sessionId}`)

      sessions.value = sessions.value.filter(s => s.id !== sessionId)

      if (currentSession.value?.id === sessionId) {
        currentSession.value = null
      }

      return true
    } catch (err) {
      console.error('Failed to delete session:', err)
      error.value = err.response?.data?.detail || 'Failed to delete session'
      return false
    }
  }

  async function startAutoJam(sessionId, numRounds = 3) {
    isAutoJamming.value = true
    streamingRound.value = null
    streamingAgents.value = {}
    streamingEvents.value = []
    error.value = null

    const abortController = new AbortController()
    autoJamAbort.value = abortController

    try {
      let apiUrl = import.meta.env.VITE_API_URL || ''
      if (apiUrl && !apiUrl.startsWith('http://') && !apiUrl.startsWith('https://')) {
        apiUrl = 'https://' + apiUrl
      }

      const response = await fetch(
        `${apiUrl}/api/v1/jam/sessions/${sessionId}/auto-jam`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('accessToken')}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ num_rounds: numRounds }),
          signal: abortController.signal,
        }
      )

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}))
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
            streamingEvents.value.push(data)

            if (data.type === 'start') {
              streamingRound.value = 0
            } else if (data.type === 'round_start') {
              streamingRound.value = data.round_number
              streamingAgents.value = {}
            } else if (data.type === 'agent_complete') {
              streamingAgents.value[data.agent_id] = {
                content: data.content,
                role: data.role,
                toolCalls: data.tool_calls || [],
              }
              // Add to live contributions
              liveContributions.value.push({
                agent_id: data.agent_id,
                content: data.content,
                round: streamingRound.value,
                timestamp: Date.now()
              })
            } else if (data.type === 'round_complete') {
              // Round finished
            } else if (data.type === 'finalizing') {
              // Merging tracks
            } else if (data.type === 'midi_created') {
              // MIDI file ready
            } else if (data.type === 'suno_started') {
              // Suno generation started
            } else if (data.type === 'end') {
              isAutoJamming.value = false
              // Refresh session to get final state
              await fetchSession(sessionId)
            }
          } catch (parseErr) {
            console.warn('Failed to parse SSE event:', parseErr)
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error('Auto-jam stream error:', err)
        error.value = err.message || 'Auto-jam failed'
      }
    } finally {
      isAutoJamming.value = false
      autoJamAbort.value = null
    }
  }

  function stopAutoJam() {
    if (autoJamAbort.value) {
      autoJamAbort.value.abort()
      autoJamAbort.value = null
    }
    isAutoJamming.value = false
  }

  function clearLiveContributions() {
    liveContributions.value = []
  }

  function clearStreamingState() {
    streamingRound.value = null
    streamingAgents.value = {}
    streamingEvents.value = []
  }

  function setCurrentSession(session) {
    currentSession.value = session
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Agent Colors (matching Village)
  // ═══════════════════════════════════════════════════════════════════════════

  const agentColors = {
    AZOTH: '#00ffaa',
    ELYSIAN: '#ff69b4',
    VAJRA: '#ffcc00',
    KETHER: '#9370db',
    USER: '#4a9eff',
    VILLAGE_BAND: '#ff6b35'
  }

  function getAgentColor(agentId) {
    return agentColors[agentId] || '#888888'
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Role Icons
  // ═══════════════════════════════════════════════════════════════════════════

  const roleIcons = {
    producer: '🎛️',
    melody: '🎵',
    bass: '🎸',
    harmony: '🎹',
    rhythm: '🥁',
    free: '🎼'
  }

  function getRoleIcon(role) {
    return roleIcons[role] || '🎼'
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // State Badges
  // ═══════════════════════════════════════════════════════════════════════════

  const stateBadges = {
    forming: { label: 'Forming', color: 'bg-blue-500' },
    jamming: { label: 'Jamming', color: 'bg-green-500' },
    finalizing: { label: 'Finalizing', color: 'bg-yellow-500' },
    complete: { label: 'Complete', color: 'bg-purple-500' },
    failed: { label: 'Failed', color: 'bg-red-500' }
  }

  function getStateBadge(state) {
    return stateBadges[state] || { label: state, color: 'bg-gray-500' }
  }

  return {
    // State
    sessions,
    currentSession,
    isLoading,
    isCreating,
    isContributing,
    isFinalizing,
    isAutoJamming,
    autoJamAbort,
    error,
    liveContributions,
    streamingRound,
    streamingAgents,
    streamingEvents,

    // Getters
    activeSessions,
    completedSessions,
    currentParticipants,
    currentTracks,
    totalNotes,
    tracksByAgent,
    tracksByRound,

    // Actions
    fetchSessions,
    fetchSession,
    createSession,
    startSession,
    contribute,
    advanceRound,
    finalizeSession,
    deleteSession,
    startAutoJam,
    stopAutoJam,
    clearLiveContributions,
    clearStreamingState,
    setCurrentSession,

    // Helpers
    getAgentColor,
    getRoleIcon,
    getStateBadge,
    agentColors,
    roleIcons,
    stateBadges
  }
})
