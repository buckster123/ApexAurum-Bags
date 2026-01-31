/**
 * Neo-Cortex Store
 *
 * State management for the 3D Neural Space memory visualization.
 * "Where memories glow like stars in the vast neural cosmos"
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'
import { isWebGLAvailable } from '@/composables/useThreeScene'

// Agent colors for visualization
export const AGENT_COLORS = {
  AZOTH: { hex: '#FFD700', name: 'Gold (bright)', glow: '#FFA500' },
  CLAUDE: { hex: '#D4AF37', name: 'Gold (dim)', glow: '#B8860B' },
  VAJRA: { hex: '#4FC3F7', name: 'Blue', glow: '#0288D1' },
  ELYSIAN: { hex: '#E8B4FF', name: 'Lilac', glow: '#BA68C8' },
  KETHER: { hex: '#9B59B6', name: 'Purple', glow: '#7B1FA2' },
}

// Layer configuration
export const LAYER_CONFIG = {
  cortex: { radius: [0, 20], brightness: 1.0, color: '#FFFFFF' },
  long_term: { radius: [20, 40], brightness: 0.8, color: '#E0E0E0' },
  working: { radius: [40, 60], brightness: 0.6, color: '#BDBDBD' },
  sensory: { radius: [60, 80], brightness: 0.4, color: '#9E9E9E' },
}

export const useNeoCortexStore = defineStore('neocortex', () => {
  // =============================================================================
  // State
  // =============================================================================

  const memories = ref([])
  const graphData = ref({ nodes: [], edges: [] })
  const stats = ref({
    total: 0,
    by_layer: {},
    by_visibility: {},
    by_agent: {},
    by_message_type: {},
  })

  const selectedMemory = ref(null)
  const hoveredMemory = ref(null)
  const isLoading = ref(false)
  const error = ref(null)

  // Filters
  const filters = ref({
    layer: null,
    visibility: null,
    agent_id: null,
    message_type: null,
    search_query: '',
    date_from: null,
    date_to: null,
  })

  // View settings
  // Check WebGL availability and default to 2D if not supported
  const webglSupported = ref(false)
  const viewMode = ref('list') // '3d' | 'list' - default to list, set to 3d in initialize() if WebGL available
  const showConnections = ref(true)
  const autoRotate = ref(true)
  const nodeScale = ref(1.0)

  // =============================================================================
  // Computed
  // =============================================================================

  const filteredNodes = computed(() => {
    let nodes = graphData.value.nodes

    if (filters.value.layer) {
      nodes = nodes.filter(n => n.layer === filters.value.layer)
    }
    if (filters.value.visibility) {
      nodes = nodes.filter(n => n.visibility === filters.value.visibility)
    }
    if (filters.value.agent_id) {
      nodes = nodes.filter(n => n.agent_id === filters.value.agent_id)
    }
    if (filters.value.message_type) {
      nodes = nodes.filter(n => n.message_type === filters.value.message_type)
    }

    return nodes
  })

  const filteredEdges = computed(() => {
    const nodeIds = new Set(filteredNodes.value.map(n => n.id))
    return graphData.value.edges.filter(
      e => nodeIds.has(e.source) && nodeIds.has(e.target)
    )
  })

  const memoryCount = computed(() => stats.value.total || 0)

  const layerBreakdown = computed(() =>
    Object.entries(stats.value.by_layer || {}).map(([layer, count]) => ({
      layer,
      count,
      percentage: stats.value.total ? ((count / stats.value.total) * 100).toFixed(1) : 0,
      color: LAYER_CONFIG[layer]?.color || '#888',
    }))
  )

  const agentBreakdown = computed(() =>
    Object.entries(stats.value.by_agent || {}).map(([agent, count]) => ({
      agent,
      count,
      color: AGENT_COLORS[agent]?.hex || '#888',
    }))
  )

  // =============================================================================
  // Actions
  // =============================================================================

  async function fetchGraphData(limit = 200) {
    isLoading.value = true
    error.value = null

    try {
      const params = new URLSearchParams()
      if (filters.value.layer) params.append('layer', filters.value.layer)
      if (filters.value.visibility) params.append('visibility', filters.value.visibility)
      params.append('limit', limit.toString())

      const response = await api.get(`/api/v1/cortex/graph?${params}`)
      graphData.value = response.data
    } catch (e) {
      console.error('Failed to fetch graph data:', e)
      error.value = e.message || 'Failed to load memories'
      graphData.value = { nodes: [], edges: [] }
    } finally {
      isLoading.value = false
    }
  }

  async function fetchStats() {
    try {
      const response = await api.get('/api/v1/cortex/stats')
      stats.value = response.data
    } catch (e) {
      console.error('Failed to fetch stats:', e)
    }
  }

  async function fetchMemory(id) {
    try {
      const response = await api.get(`/api/v1/cortex/memories/${id}`)
      selectedMemory.value = response.data
      return response.data
    } catch (e) {
      console.error('Failed to fetch memory:', e)
      throw e
    }
  }

  async function searchMemories(query) {
    isLoading.value = true
    error.value = null

    try {
      const response = await api.post('/api/v1/cortex/search', {
        query,
        layers: filters.value.layer ? [filters.value.layer] : null,
        visibility: filters.value.visibility,
        agent_id: filters.value.agent_id,
        limit: 100,
      })

      // Update graph with search results
      graphData.value = {
        nodes: response.data,
        edges: [], // Search results don't include edges
      }
    } catch (e) {
      console.error('Search failed:', e)
      error.value = e.message || 'Search failed'
    } finally {
      isLoading.value = false
    }
  }

  async function promoteMemory(id, newLayer) {
    try {
      await api.patch(`/api/v1/cortex/memories/${id}/layer`, {
        layer: newLayer,
      })

      // Update local state
      const node = graphData.value.nodes.find(n => n.id === id)
      if (node) node.layer = newLayer

      if (selectedMemory.value?.id === id) {
        selectedMemory.value.layer = newLayer
      }

      // Refresh stats
      await fetchStats()

      return true
    } catch (e) {
      console.error('Failed to promote memory:', e)
      throw e
    }
  }

  async function deleteMemory(id) {
    try {
      await api.delete(`/api/v1/cortex/memories/${id}`)

      // Remove from local state
      graphData.value.nodes = graphData.value.nodes.filter(n => n.id !== id)
      graphData.value.edges = graphData.value.edges.filter(
        e => e.source !== id && e.target !== id
      )

      if (selectedMemory.value?.id === id) {
        selectedMemory.value = null
      }

      // Refresh stats
      await fetchStats()

      return true
    } catch (e) {
      console.error('Failed to delete memory:', e)
      throw e
    }
  }

  function selectMemory(memory) {
    selectedMemory.value = memory
  }

  function clearSelection() {
    selectedMemory.value = null
    hoveredMemory.value = null
  }

  function setFilter(key, value) {
    filters.value[key] = value
  }

  function clearFilters() {
    filters.value = {
      layer: null,
      visibility: null,
      agent_id: null,
      message_type: null,
      search_query: '',
      date_from: null,
      date_to: null,
    }
  }

  function setViewMode(mode) {
    viewMode.value = mode
  }

  // Initialize
  async function initialize() {
    // Check WebGL availability
    webglSupported.value = isWebGLAvailable()
    if (webglSupported.value) {
      viewMode.value = '3d'
      console.log('Neo-Cortex: WebGL available, using 3D mode')
    } else {
      viewMode.value = 'list'
      console.log('Neo-Cortex: WebGL not available, falling back to list mode')
    }

    await Promise.all([fetchGraphData(), fetchStats()])
  }

  return {
    // State
    memories,
    graphData,
    stats,
    selectedMemory,
    hoveredMemory,
    isLoading,
    error,
    filters,
    viewMode,
    webglSupported,
    showConnections,
    autoRotate,
    nodeScale,

    // Computed
    filteredNodes,
    filteredEdges,
    memoryCount,
    layerBreakdown,
    agentBreakdown,

    // Actions
    fetchGraphData,
    fetchStats,
    fetchMemory,
    searchMemories,
    promoteMemory,
    deleteMemory,
    selectMemory,
    clearSelection,
    setFilter,
    clearFilters,
    setViewMode,
    initialize,
  }
})
