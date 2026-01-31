/**
 * Music Store - apexXuno
 *
 * The Athanor's creative voice - AI music generation via Suno.
 * Handles library management, playback state, and SSE streaming for generation.
 */

import { defineStore } from 'pinia'
import { ref, computed, nextTick } from 'vue'
import api from '@/services/api'

export const useMusicStore = defineStore('music', () => {
  // ═══════════════════════════════════════════════════════════════════════════════
  // STATE
  // ═══════════════════════════════════════════════════════════════════════════════

  // Library
  const library = ref([])
  const total = ref(0)
  const totalDuration = ref(0)
  const loading = ref(false)

  // Filters
  const filters = ref({
    favoritesOnly: false,
    agentId: null,
    status: null,
    search: '',
  })

  // Playback
  const currentTrack = ref(null)
  const isPlaying = ref(false)
  const currentTime = ref(0)
  const duration = ref(0)
  const volume = ref(parseFloat(localStorage.getItem('apexaurum_music_volume')) || 0.8)

  // Generation
  const isGenerating = ref(false)
  const generationProgress = ref('')
  const generationStatus = ref('')
  const generationAbort = ref(null)

  // Audio element (managed externally in MusicPlayer)
  const audioElement = ref(null)

  // ═══════════════════════════════════════════════════════════════════════════════
  // COMPUTED
  // ═══════════════════════════════════════════════════════════════════════════════

  const completedTracks = computed(() =>
    library.value.filter(t => t.status === 'completed')
  )

  const pendingTracks = computed(() =>
    library.value.filter(t => t.status === 'pending' || t.status === 'generating')
  )

  const favoriteTracks = computed(() =>
    library.value.filter(t => t.favorite)
  )

  const progressPercent = computed(() => {
    if (duration.value <= 0) return 0
    return (currentTime.value / duration.value) * 100
  })

  const formattedCurrentTime = computed(() => formatTime(currentTime.value))
  const formattedDuration = computed(() => formatTime(duration.value))

  // ═══════════════════════════════════════════════════════════════════════════════
  // HELPERS
  // ═══════════════════════════════════════════════════════════════════════════════

  function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return '0:00'
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  function getApiUrl() {
    let apiUrl = import.meta.env.VITE_API_URL || ''
    if (apiUrl && !apiUrl.startsWith('http://') && !apiUrl.startsWith('https://')) {
      apiUrl = 'https://' + apiUrl
    }
    return apiUrl
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // LIBRARY ACTIONS
  // ═══════════════════════════════════════════════════════════════════════════════

  async function fetchLibrary() {
    loading.value = true
    try {
      const params = new URLSearchParams({ limit: '100' })
      if (filters.value.favoritesOnly) params.append('favorites_only', 'true')
      if (filters.value.agentId) params.append('agent_id', filters.value.agentId)
      if (filters.value.status) params.append('status', filters.value.status)
      if (filters.value.search) params.append('search', filters.value.search)

      const response = await api.get(`/api/v1/music/library?${params}`)
      library.value = response.data?.tasks || []
      total.value = response.data?.total || 0
      totalDuration.value = response.data?.total_duration || 0
    } catch (e) {
      console.error('Failed to fetch music library:', e)
      library.value = []
    } finally {
      loading.value = false
    }
  }

  async function refreshTask(taskId) {
    try {
      const response = await api.get(`/api/v1/music/tasks/${taskId}`)
      const updatedTask = response.data
      const index = library.value.findIndex(t => t.id === taskId)
      if (index !== -1) {
        library.value[index] = updatedTask
      }
      return updatedTask
    } catch (e) {
      console.error('Failed to refresh task:', e)
      return null
    }
  }

  async function toggleFavorite(taskId) {
    const task = library.value.find(t => t.id === taskId)
    if (!task) return

    const newValue = !task.favorite
    try {
      await api.patch(`/api/v1/music/tasks/${taskId}/favorite`, null, {
        params: { favorite: newValue }
      })
      task.favorite = newValue
    } catch (e) {
      console.error('Failed to toggle favorite:', e)
    }
  }

  async function deleteTrack(taskId) {
    try {
      await api.delete(`/api/v1/music/tasks/${taskId}`)
      library.value = library.value.filter(t => t.id !== taskId)

      // Stop playback if this was the current track
      if (currentTrack.value?.id === taskId) {
        stopPlayback()
      }
    } catch (e) {
      console.error('Failed to delete track:', e)
      throw e
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // PLAYBACK ACTIONS
  // ═══════════════════════════════════════════════════════════════════════════════

  async function playTrack(task) {
    if (!task || task.status !== 'completed' || !task.file_path) {
      console.warn('Track not ready for playback')
      return
    }

    const isSameTrack = currentTrack.value?.id === task.id
    if (isSameTrack) {
      // Replaying same track - force restart via toggle
      isPlaying.value = false
      currentTime.value = 0
      await nextTick()
    }

    // Set playback state FIRST (preserves user gesture chain for autoplay)
    currentTrack.value = task
    isPlaying.value = true

    // Increment play count AFTER (fire-and-forget, non-blocking)
    api.post(`/api/v1/music/tasks/${task.id}/play`).then(() => {
      const libTask = library.value.find(t => t.id === task.id)
      if (libTask) libTask.play_count++
    }).catch(e => {
      console.warn('Failed to increment play count:', e)
    })
  }

  function pausePlayback() {
    isPlaying.value = false
  }

  function resumePlayback() {
    if (currentTrack.value) {
      isPlaying.value = true
    }
  }

  function togglePlayback() {
    if (isPlaying.value) {
      pausePlayback()
    } else {
      resumePlayback()
    }
  }

  function stopPlayback() {
    isPlaying.value = false
    currentTrack.value = null
    currentTime.value = 0
    duration.value = 0
  }

  function seekTo(percent) {
    if (duration.value > 0) {
      currentTime.value = (percent / 100) * duration.value
    }
  }

  function setVolume(vol) {
    volume.value = Math.max(0, Math.min(1, vol))
    localStorage.setItem('apexaurum_music_volume', volume.value.toString())
  }

  function playNext() {
    if (!currentTrack.value) return
    const completed = completedTracks.value
    const currentIndex = completed.findIndex(t => t.id === currentTrack.value.id)
    if (currentIndex < completed.length - 1) {
      playTrack(completed[currentIndex + 1])
    } else {
      // No next track - reset playback state
      isPlaying.value = false
      currentTime.value = 0
    }
  }

  function playPrevious() {
    if (!currentTrack.value) return
    const completed = completedTracks.value
    const currentIndex = completed.findIndex(t => t.id === currentTrack.value.id)
    if (currentIndex > 0) {
      playTrack(completed[currentIndex - 1])
    }
  }

  function getAudioUrl(taskId) {
    const apiUrl = getApiUrl()
    const token = localStorage.getItem('accessToken')
    return `${apiUrl}/api/v1/music/tasks/${taskId}/file?token=${token}`
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // GENERATION ACTIONS (with SSE streaming)
  // ═══════════════════════════════════════════════════════════════════════════════

  async function generateTrack(params) {
    const { prompt, style, title, model = 'V5', instrumental = true } = params

    if (!prompt?.trim()) {
      throw new Error('Prompt is required')
    }

    isGenerating.value = true
    generationProgress.value = 'Starting generation...'
    generationStatus.value = 'pending'

    const abortController = new AbortController()
    generationAbort.value = abortController

    try {
      const apiUrl = getApiUrl()
      const token = localStorage.getItem('accessToken')

      const response = await fetch(`${apiUrl}/api/v1/music/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token && { 'Authorization': `Bearer ${token}` })
        },
        body: JSON.stringify({
          prompt,
          style: style || null,
          title: title || null,
          model,
          instrumental,
          stream: true,
        }),
        signal: abortController.signal,
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || `HTTP ${response.status}`)
      }

      // Read SSE stream
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let completedTask = null

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

            if (data.type === 'status') {
              generationStatus.value = data.status
              generationProgress.value = data.progress || ''
            } else if (data.type === 'completed') {
              completedTask = data.task
              generationStatus.value = 'completed'
              generationProgress.value = 'Complete!'
            } else if (data.type === 'error') {
              throw new Error(data.error)
            }
          } catch (parseError) {
            console.warn('Failed to parse SSE:', line, parseError)
          }
        }
      }

      // Add to library
      if (completedTask) {
        library.value.unshift(completedTask)
        total.value++
      }

      return completedTask
    } catch (e) {
      if (e.name === 'AbortError') {
        generationProgress.value = 'Cancelled'
        generationStatus.value = 'cancelled'
      } else {
        generationProgress.value = `Error: ${e.message}`
        generationStatus.value = 'failed'
        throw e
      }
    } finally {
      isGenerating.value = false
      generationAbort.value = null
    }
  }

  function cancelGeneration() {
    if (generationAbort.value) {
      generationAbort.value.abort()
      generationAbort.value = null
    }
  }

  // Background polling for pending tracks
  async function pollPendingTracks() {
    const pending = pendingTracks.value
    for (const task of pending) {
      const updated = await refreshTask(task.id)
      if (updated?.status === 'completed') {
        // Track completed while we were polling
        console.log(`Track "${updated.title || 'Untitled'}" completed!`)
      }
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // RETURN
  // ═══════════════════════════════════════════════════════════════════════════════

  return {
    // State
    library,
    total,
    totalDuration,
    loading,
    filters,
    currentTrack,
    isPlaying,
    currentTime,
    duration,
    volume,
    isGenerating,
    generationProgress,
    generationStatus,

    // Computed
    completedTracks,
    pendingTracks,
    favoriteTracks,
    progressPercent,
    formattedCurrentTime,
    formattedDuration,

    // Library actions
    fetchLibrary,
    refreshTask,
    toggleFavorite,
    deleteTrack,

    // Playback actions
    playTrack,
    pausePlayback,
    resumePlayback,
    togglePlayback,
    stopPlayback,
    seekTo,
    setVolume,
    playNext,
    playPrevious,
    getAudioUrl,

    // Generation actions
    generateTrack,
    cancelGeneration,
    pollPendingTracks,

    // Helpers
    formatTime,
  }
})
