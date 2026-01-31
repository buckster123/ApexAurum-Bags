import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import api from '@/services/api'

export const useNurseryStore = defineStore('nursery', () => {
  // State
  const datasets = ref([])
  const stats = ref({
    datasets: 0,
    total_examples: 0,
    training_jobs: 0,
    jobs_completed: 0,
    models: 0,
    apprentices: 0,
  })
  const loading = ref(false)
  const generating = ref(false)
  const extracting = ref(false)
  const tierRequired = ref(false)

  // Training Forge state
  const trainingJobs = ref([])
  const trainableModels = ref([])
  const costEstimate = ref(null)
  const estimating = ref(false)
  const startingTraining = ref(false)
  const loadingJobs = ref(false)
  const hasTogetherAccess = ref(false)

  // Model Cradle state
  const models = ref([])
  const loadingModels = ref(false)

  // Village Feed state
  const villageActivity = ref([])
  const loadingActivity = ref(false)
  const discoveredModels = ref([])
  const loadingDiscovery = ref(false)
  const discoveryQuery = ref('')

  // Apprentice Protocol state
  const apprentices = ref([])
  const loadingApprentices = ref(false)
  const creatingApprentice = ref(false)

  // Error tracking
  const lastError = ref(null)

  // Computed properties
  const totalDatasets = computed(() => stats.value.datasets || datasets.value.length)
  const totalExamples = computed(() => {
    if (stats.value.total_examples) return stats.value.total_examples
    return datasets.value.reduce((sum, d) => sum + (d.num_examples || 0), 0)
  })
  const runningJobs = computed(() => trainingJobs.value.filter(j => ['running', 'uploading', 'pending'].includes(j.status)).length)
  const completedJobs = computed(() => trainingJobs.value.filter(j => j.status === 'completed').length)
  const trainedApprentices = computed(() => apprentices.value.filter(a => a.status === 'trained').length)
  const trainingApprentices = computed(() => apprentices.value.filter(a => a.status === 'training').length)
  const villageModels = computed(() => models.value.filter(m => m.village_posted).length)

  // Actions
  async function fetchDatasets() {
    loading.value = true
    try {
      const response = await api.get('/api/v1/nursery/datasets')
      datasets.value = response.data.datasets || []
      tierRequired.value = false
      lastError.value = null
    } catch (error) {
      if (error.response?.status === 403) {
        tierRequired.value = true
      }
      console.error('Failed to fetch datasets:', error)
      lastError.value = { action: 'fetchDatasets', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
    } finally {
      loading.value = false
    }
  }

  async function generateData(toolNames, numExamples, variationLevel, datasetName) {
    generating.value = true
    try {
      const payload = {
        tool_names: toolNames,
        num_examples: numExamples,
        variation_level: variationLevel,
      }
      if (datasetName) payload.dataset_name = datasetName

      const response = await api.post('/api/v1/nursery/datasets/generate', payload)

      // Refresh list
      await fetchDatasets()
      await fetchStats()

      lastError.value = null
      return response.data
    } catch (error) {
      console.error('Generate failed:', error)
      lastError.value = { action: 'generateData', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
      throw error
    } finally {
      generating.value = false
    }
  }

  async function extractData(toolsFilter, minExamples, datasetName) {
    extracting.value = true
    try {
      const payload = {
        min_examples: minExamples,
      }
      if (toolsFilter && toolsFilter.length > 0) payload.tools_filter = toolsFilter
      if (datasetName) payload.dataset_name = datasetName

      const response = await api.post('/api/v1/nursery/datasets/extract', payload)

      await fetchDatasets()
      await fetchStats()

      lastError.value = null
      return response.data
    } catch (error) {
      console.error('Extract failed:', error)
      lastError.value = { action: 'extractData', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
      throw error
    } finally {
      extracting.value = false
    }
  }

  async function deleteDataset(datasetId) {
    try {
      await api.delete(`/api/v1/nursery/datasets/${datasetId}`)
      datasets.value = datasets.value.filter(d => d.id !== datasetId)
      await fetchStats()
      lastError.value = null
      return true
    } catch (error) {
      console.error('Delete failed:', error)
      lastError.value = { action: 'deleteDataset', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
      return false
    }
  }

  async function fetchStats() {
    try {
      const response = await api.get('/api/v1/nursery/stats')
      stats.value = response.data
      lastError.value = null
    } catch (error) {
      console.error('Failed to fetch stats:', error)
      lastError.value = { action: 'fetchStats', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
    }
  }

  async function fetchTrainingJobs(statusFilter) {
    loadingJobs.value = true
    try {
      const params = statusFilter ? { status: statusFilter } : {}
      const response = await api.get('/api/v1/nursery/training/jobs', { params })
      trainingJobs.value = response.data.jobs || []
      lastError.value = null
    } catch (error) {
      if (error.response?.status === 403) {
        tierRequired.value = true
      }
      console.error('Failed to fetch training jobs:', error)
      lastError.value = { action: 'fetchTrainingJobs', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
    } finally {
      loadingJobs.value = false
    }
  }

  async function fetchTrainableModels() {
    try {
      const response = await api.get('/api/v1/nursery/training/models')
      trainableModels.value = response.data.models || []
      lastError.value = null
    } catch (error) {
      console.error('Failed to fetch trainable models:', error)
      lastError.value = { action: 'fetchTrainableModels', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
    }
  }

  async function estimateCost(datasetId, baseModel, nEpochs, lora) {
    estimating.value = true
    costEstimate.value = null
    try {
      const response = await api.post('/api/v1/nursery/training/estimate', {
        dataset_id: datasetId,
        base_model: baseModel,
        n_epochs: nEpochs,
        lora: lora,
      })
      costEstimate.value = response.data
      lastError.value = null
      return response.data
    } catch (error) {
      console.error('Estimate failed:', error)
      lastError.value = { action: 'estimateCost', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
      throw error
    } finally {
      estimating.value = false
    }
  }

  async function startTraining(options = {}) {
    const { datasetId, baseModel, nEpochs, learningRate, lora, batchSize, suffix, apprenticeId } = options
    startingTraining.value = true
    try {
      const payload = {
        dataset_id: datasetId,
        base_model: baseModel,
        n_epochs: nEpochs,
        learning_rate: learningRate,
        lora: lora,
      }
      if (batchSize) payload.batch_size = batchSize
      if (suffix) payload.suffix = suffix
      if (apprenticeId) payload.apprentice_id = apprenticeId

      const response = await api.post('/api/v1/nursery/training/start', payload)

      // Refresh jobs and stats
      await fetchTrainingJobs()
      await fetchStats()

      lastError.value = null
      return response.data
    } catch (error) {
      console.error('Start training failed:', error)
      lastError.value = { action: 'startTraining', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
      throw error
    } finally {
      startingTraining.value = false
    }
  }

  async function cancelJob(jobId) {
    try {
      await api.post(`/api/v1/nursery/training/jobs/${jobId}/cancel`)
      await fetchTrainingJobs()
      await fetchStats()
      lastError.value = null
      return true
    } catch (error) {
      console.error('Cancel failed:', error)
      lastError.value = { action: 'cancelJob', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
      return false
    }
  }

  async function checkTogetherAccess() {
    try {
      const response = await api.get('/api/v1/user/api-key/status')
      const providers = response.data.providers || response.data || {}
      const together = providers.together || providers['together'] || {}
      hasTogetherAccess.value = !!(together.configured || together.has_platform_key || together.has_platform_grant)
      lastError.value = null
    } catch (error) {
      console.error('Failed to check API key status:', error)
      lastError.value = { action: 'checkTogetherAccess', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
      hasTogetherAccess.value = false
    }
  }

  // -- Model Cradle --

  async function fetchModels() {
    loadingModels.value = true
    try {
      const response = await api.get('/api/v1/nursery/models')
      models.value = response.data.models || []
      tierRequired.value = false
      lastError.value = null
    } catch (error) {
      if (error.response?.status === 403) tierRequired.value = true
      console.error('Failed to fetch models:', error)
      lastError.value = { action: 'fetchModels', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
    } finally {
      loadingModels.value = false
    }
  }

  async function fetchModelDetail(modelId) {
    try {
      const response = await api.get(`/api/v1/nursery/models/${modelId}`)
      lastError.value = null
      return response.data
    } catch (error) {
      console.error('Failed to fetch model detail:', error)
      lastError.value = { action: 'fetchModelDetail', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
      return null
    }
  }

  async function registerModel(modelId) {
    try {
      const response = await api.post(`/api/v1/nursery/models/${modelId}/register`)
      const idx = models.value.findIndex(m => m.id === modelId)
      if (idx !== -1) models.value[idx].village_posted = true
      await fetchStats()
      lastError.value = null
      return response.data
    } catch (error) {
      console.error('Register model failed:', error)
      lastError.value = { action: 'registerModel', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
      throw error
    }
  }

  async function deleteModel(modelId) {
    try {
      await api.delete(`/api/v1/nursery/models/${modelId}`)
      models.value = models.value.filter(m => m.id !== modelId)
      await fetchStats()
      lastError.value = null
      return true
    } catch (error) {
      console.error('Delete model failed:', error)
      lastError.value = { action: 'deleteModel', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
      return false
    }
  }

  // -- Village Feed --

  async function discoverModels(query) {
    loadingDiscovery.value = true
    try {
      const params = {}
      if (query) params.query = query
      const response = await api.get('/api/v1/nursery/discover', { params })
      discoveredModels.value = response.data.models || []
      lastError.value = null
    } catch (error) {
      console.error('Discover models failed:', error)
      lastError.value = { action: 'discoverModels', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
    } finally {
      loadingDiscovery.value = false
    }
  }

  async function fetchVillageActivity() {
    loadingActivity.value = true
    try {
      const response = await api.get('/api/v1/nursery/village-activity')
      villageActivity.value = response.data.activity || []
      lastError.value = null
    } catch (error) {
      console.error('Failed to fetch village activity:', error)
      lastError.value = { action: 'fetchVillageActivity', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
    } finally {
      loadingActivity.value = false
    }
  }

  // -- Apprentice Protocol --

  async function fetchApprentices() {
    loadingApprentices.value = true
    try {
      const response = await api.get('/api/v1/nursery/apprentices')
      apprentices.value = response.data.apprentices || []
      tierRequired.value = false
      lastError.value = null
    } catch (error) {
      if (error.response?.status === 403) tierRequired.value = true
      console.error('Failed to fetch apprentices:', error)
      lastError.value = { action: 'fetchApprentices', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
    } finally {
      loadingApprentices.value = false
    }
  }

  async function createApprentice(masterAgent, apprenticeName, specialization, autoGenerate, numExamples) {
    creatingApprentice.value = true
    try {
      const payload = {
        master_agent: masterAgent,
        apprentice_name: apprenticeName,
        auto_generate: autoGenerate || false,
        num_examples: numExamples || 50,
      }
      if (specialization) payload.specialization = specialization
      if (autoGenerate) payload.variation_level = 'medium'

      const response = await api.post('/api/v1/nursery/apprentices', payload)
      await fetchApprentices()
      await fetchStats()
      lastError.value = null
      return response.data
    } catch (error) {
      console.error('Create apprentice failed:', error)
      lastError.value = { action: 'createApprentice', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
      throw error
    } finally {
      creatingApprentice.value = false
    }
  }

  async function deleteApprentice(apprenticeId) {
    try {
      await api.delete(`/api/v1/nursery/apprentices/${apprenticeId}`)
      apprentices.value = apprentices.value.filter(a => a.id !== apprenticeId)
      await fetchStats()
      lastError.value = null
      return true
    } catch (error) {
      console.error('Delete apprentice failed:', error)
      lastError.value = { action: 'deleteApprentice', message: error.response?.data?.detail || error.message, timestamp: Date.now() }
      return false
    }
  }

  return {
    // Data Garden
    datasets, stats, loading, generating, extracting, tierRequired,
    fetchDatasets, generateData, extractData, deleteDataset, fetchStats,
    // Training Forge
    trainingJobs, trainableModels, costEstimate, estimating, startingTraining,
    loadingJobs, hasTogetherAccess,
    fetchTrainingJobs, fetchTrainableModels, estimateCost, startTraining, cancelJob, checkTogetherAccess,
    // Model Cradle
    models, loadingModels,
    fetchModels, fetchModelDetail, registerModel, deleteModel,
    // Village Feed
    villageActivity, loadingActivity, discoveredModels, loadingDiscovery, discoveryQuery,
    discoverModels, fetchVillageActivity,
    // Apprentice Protocol
    apprentices, loadingApprentices, creatingApprentice,
    fetchApprentices, createApprentice, deleteApprentice,
    // Computed + error
    lastError, totalDatasets, totalExamples, runningJobs, completedJobs,
    trainedApprentices, trainingApprentices, villageModels,
  }
})
