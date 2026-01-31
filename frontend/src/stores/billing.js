import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

export const useBillingStore = defineStore('billing', () => {
  // State
  const status = ref({
    tier: 'free_trial',
    subscription_status: 'active',
    messages_used: 0,
    messages_limit: 50,
    messages_remaining: 50,
    current_period_end: null,
    cancel_at_period_end: false,
    credit_balance_cents: 0,
    credit_balance_usd: 0,
    features: {
      models: ['claude-haiku-4-5-20251001'],
      tools_enabled: false,
      multi_provider: false,
      byok_allowed: false,
      api_access: false,
    },
    at_limit: false,
    near_limit: false,
  })

  const usageSummary = ref(null)
  const featureCredits = ref({ opus_messages: 0, suno_generations: 0, training_jobs: 0 })

  const pricing = ref(null)
  const transactions = ref([])
  const loading = ref(false)
  const error = ref(null)

  // Getters
  // Tier identity checks
  const isFreeTrial = computed(() => status.value.tier === 'free_trial')
  const isSeeker = computed(() => status.value.tier === 'seeker')
  const isAdept = computed(() => status.value.tier === 'adept')
  const isOpus = computed(() => status.value.tier === 'opus')
  const isAzothic = computed(() => status.value.tier === 'azothic')

  // Backward compat aliases
  const isFree = computed(() => status.value.tier === 'free_trial')
  const isPro = computed(() => status.value.tier === 'seeker')

  // Tier level for >= comparisons (0=trial, 1=seeker, 2=adept, 3=opus, 4=azothic)
  const tierLevel = computed(() => {
    const levels = { free_trial: 0, seeker: 1, adept: 2, opus: 3, azothic: 4 }
    return levels[status.value.tier] || 0
  })

  // Convenience
  const isPaid = computed(() => status.value.tier !== 'free_trial')

  const tierName = computed(() => {
    const names = {
      free_trial: 'Free Trial',
      seeker: 'Seeker',
      adept: 'Adept',
      opus: 'Opus',
      azothic: 'Azothic',
    }
    return names[status.value.tier] || 'Unknown'
  })

  const usagePercent = computed(() => {
    if (!status.value.messages_limit) return 0
    return Math.min(100, Math.round((status.value.messages_used / status.value.messages_limit) * 100))
  })

  const hasCredits = computed(() => status.value.credit_balance_cents > 0)

  const canUseTools = computed(() => status.value.features?.tools_enabled || false)
  const canUseMultiProvider = computed(() => status.value.features?.multi_provider || false)
  const allowedModels = computed(() => status.value.features?.models || [])

  const canBuyPacks = computed(() => tierLevel.value >= 2)  // Adept+

  const hasFeatureCredits = computed(() => {
    const fc = featureCredits.value
    return fc.opus_messages > 0 || fc.suno_generations > 0 || fc.training_jobs > 0
  })

  // Actions
  async function fetchStatus() {
    try {
      loading.value = true
      error.value = null
      const response = await api.get('/api/v1/billing/status')
      status.value = response.data
      // Extract feature credits if present
      if (response.data.feature_credits) {
        featureCredits.value = response.data.feature_credits
      }
    } catch (e) {
      // If billing not configured (404) or not authenticated, use defaults
      if (e.response?.status === 404 || e.response?.status === 401) {
        // Keep defaults
      } else {
        error.value = e.response?.data?.detail || 'Failed to load billing status'
        console.error('Failed to fetch billing status:', e)
      }
    } finally {
      loading.value = false
    }
  }

  async function fetchPricing() {
    try {
      const response = await api.get('/api/v1/billing/pricing')
      pricing.value = response.data
    } catch (e) {
      console.error('Failed to fetch pricing:', e)
    }
  }

  async function fetchTransactions(limit = 50, offset = 0) {
    try {
      loading.value = true
      const response = await api.get('/api/v1/billing/transactions', {
        params: { limit, offset }
      })
      transactions.value = response.data.transactions
      return response.data
    } catch (e) {
      console.error('Failed to fetch transactions:', e)
      return { transactions: [], total: 0 }
    } finally {
      loading.value = false
    }
  }

  async function createSubscriptionCheckout(tier) {
    try {
      loading.value = true
      error.value = null
      const response = await api.post('/api/v1/billing/checkout/subscription', { tier })
      // Redirect to Stripe Checkout
      window.location.href = response.data.checkout_url
      return response.data
    } catch (e) {
      error.value = e.response?.data?.detail || 'Failed to create checkout session'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function createCreditsCheckout(pack) {
    try {
      loading.value = true
      error.value = null
      const response = await api.post('/api/v1/billing/checkout/credits', { pack })
      // Redirect to Stripe Checkout
      window.location.href = response.data.checkout_url
      return response.data
    } catch (e) {
      error.value = e.response?.data?.detail || 'Failed to create checkout session'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function openPortal() {
    try {
      loading.value = true
      error.value = null
      const response = await api.post('/api/v1/billing/portal', {})
      // Redirect to Stripe Portal
      window.location.href = response.data.portal_url
      return response.data
    } catch (e) {
      error.value = e.response?.data?.detail || 'Failed to open billing portal'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchUsageSummary() {
    try {
      const response = await api.get('/api/v1/billing/usage')
      usageSummary.value = response.data
      if (response.data.feature_credits) {
        featureCredits.value = response.data.feature_credits
      }
      return response.data
    } catch (error) {
      console.error('Failed to fetch usage summary:', error)
      return null
    }
  }

  async function createPackCheckout(packId, resourceType = null) {
    loading.value = true
    error.value = null
    try {
      const payload = { pack: packId }
      if (resourceType) payload.resource_type = resourceType
      const response = await api.post('/api/v1/billing/checkout/pack', payload)
      if (response.data.checkout_url) {
        window.location.href = response.data.checkout_url
      }
      return response.data
    } catch (err) {
      error.value = err.response?.data?.detail || 'Failed to create pack checkout.'
      throw err
    } finally {
      loading.value = false
    }
  }

  function isModelAllowed(modelId) {
    return allowedModels.value.includes(modelId)
  }

  // Coupon functionality
  const couponResult = ref(null)
  const couponLoading = ref(false)

  async function checkCoupon(code) {
    try {
      couponLoading.value = true
      couponResult.value = null
      const response = await api.get(`/api/v1/billing/coupon/${encodeURIComponent(code)}`)
      couponResult.value = response.data
      return response.data
    } catch (e) {
      couponResult.value = { valid: false, error: e.response?.data?.detail || 'Failed to check coupon' }
      return couponResult.value
    } finally {
      couponLoading.value = false
    }
  }

  async function redeemCoupon(code) {
    try {
      couponLoading.value = true
      error.value = null
      const response = await api.post('/api/v1/billing/coupon/redeem', { code })
      // Refresh status after redemption
      await fetchStatus()
      return response.data
    } catch (e) {
      error.value = e.response?.data?.detail || 'Failed to redeem coupon'
      throw e
    } finally {
      couponLoading.value = false
    }
  }

  function clearCouponResult() {
    couponResult.value = null
  }

  function reset() {
    status.value = {
      tier: 'free_trial',
      subscription_status: 'active',
      messages_used: 0,
      messages_limit: 50,
      messages_remaining: 50,
      current_period_end: null,
      cancel_at_period_end: false,
      credit_balance_cents: 0,
      credit_balance_usd: 0,
      features: {
        models: ['claude-haiku-4-5-20251001'],
        tools_enabled: false,
        multi_provider: false,
        byok_allowed: false,
        api_access: false,
      },
      at_limit: false,
      near_limit: false,
    }
    pricing.value = null
    transactions.value = []
  }

  return {
    // State
    status,
    pricing,
    transactions,
    loading,
    error,

    // Getters
    isFreeTrial,
    isSeeker,
    isAdept,
    isOpus,
    isAzothic,
    isFree,
    isPro,
    tierLevel,
    isPaid,
    tierName,
    usagePercent,
    hasCredits,
    canUseTools,
    canUseMultiProvider,
    allowedModels,

    // New: feature credits + usage
    usageSummary,
    featureCredits,
    fetchUsageSummary,
    createPackCheckout,
    canBuyPacks,
    hasFeatureCredits,

    // Actions
    fetchStatus,
    fetchPricing,
    fetchTransactions,
    createSubscriptionCheckout,
    createCreditsCheckout,
    openPortal,
    isModelAllowed,
    reset,
    // Coupons
    couponResult,
    couponLoading,
    checkCoupon,
    redeemCoupon,
    clearCouponResult,
  }
})
