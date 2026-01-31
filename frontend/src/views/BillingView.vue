<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useBillingStore } from '@/stores/billing'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const billing = useBillingStore()
const auth = useAuthStore()

const activeTab = ref('plans')
const loadingAction = ref(null)
const checkoutError = ref(null)
const couponCode = ref('')
const couponMessage = ref(null)
const selectedResource = ref('opus_messages')

// Check for success redirect
const checkoutSuccess = computed(() => route.query.session_id)

// Trial days remaining
const trialDaysLeft = computed(() => {
  if (!billing.status.trial_end) return 0
  const end = new Date(billing.status.trial_end)
  const now = new Date()
  return Math.max(0, Math.ceil((end - now) / (1000 * 60 * 60 * 24)))
})

onMounted(async () => {
  await billing.fetchStatus()
  await billing.fetchPricing()

  if (checkoutSuccess.value) {
    // Refresh status after successful checkout
    setTimeout(() => billing.fetchStatus(), 2000)
  }
})

async function selectPlan(tierId) {
  if (tierId === 'free_trial') return
  if (tierId === billing.status.tier) return

  loadingAction.value = tierId
  try {
    await billing.createSubscriptionCheckout(tierId)
  } catch (e) {
    console.error('Checkout error:', e)
    checkoutError.value = e.response?.data?.detail || 'Checkout failed. Please try again.'
    setTimeout(() => checkoutError.value = null, 5000)
  } finally {
    loadingAction.value = null
  }
}


async function manageSubscription() {
  loadingAction.value = 'portal'
  try {
    await billing.openPortal()
  } catch (e) {
    console.error('Portal error:', e)
    checkoutError.value = e.response?.data?.detail || 'Could not open billing portal. Please try again.'
    setTimeout(() => checkoutError.value = null, 5000)
  } finally {
    loadingAction.value = null
  }
}

async function redeemCoupon() {
  if (!couponCode.value.trim()) return

  couponMessage.value = null
  loadingAction.value = 'coupon'

  try {
    const result = await billing.redeemCoupon(couponCode.value.trim())
    couponMessage.value = {
      success: true,
      text: result.benefit_description,
    }
    couponCode.value = ''
  } catch (e) {
    couponMessage.value = {
      success: false,
      text: billing.error || 'Failed to redeem coupon',
    }
  } finally {
    loadingAction.value = null
  }
}

async function buyPack(packId, resourceType = null) {
  loadingAction.value = `pack-${packId}`
  try {
    await billing.createPackCheckout(packId, resourceType)
  } catch (e) {
    console.error('Pack checkout error:', e)
    checkoutError.value = e.response?.data?.detail || 'Pack checkout failed. Please try again.'
    setTimeout(() => checkoutError.value = null, 5000)
  } finally {
    loadingAction.value = null
  }
}

function getBarColor(used, limit) {
  if (!limit) return 'bg-green-500'
  const pct = (used / limit) * 100
  if (pct >= 90) return 'bg-red-500'
  if (pct >= 60) return 'bg-yellow-500'
  return 'bg-green-500'
}

async function fetchUsageIfNeeded() {
  if (!billing.usageSummary) {
    await billing.fetchUsageSummary()
  }
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  })
}
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8">
    <!-- Header -->
    <div class="text-center mb-12">
      <h1 class="text-4xl font-bold mb-4">Choose Your Path</h1>
      <p class="text-gray-400 text-lg">
        From Seeker to Azothic, unlock the full power of the Athanor
      </p>
    </div>

    <!-- Free Trial Banner -->
    <div v-if="billing.isFreeTrial" class="mb-6 bg-amber-900/30 border border-amber-500/30 rounded-lg p-4 text-center">
      <p class="text-amber-300 font-medium">
        You're on a free trial{{ trialDaysLeft > 0 ? ` (${trialDaysLeft} days remaining)` : ' (expired)' }}.
        Subscribe to unlock the full Athanor.
      </p>
    </div>

    <!-- Success Message -->
    <div v-if="checkoutSuccess" class="mb-8 bg-green-500/10 border border-green-500/30 rounded-lg p-4 text-center">
      <div class="text-green-400 text-lg font-medium">Payment Successful!</div>
      <p class="text-green-300/70 text-sm mt-1">Your account is being updated...</p>
    </div>

    <!-- Current Status Card -->
    <div v-if="auth.isAuthenticated" class="mb-12 bg-surface rounded-xl p-6 border border-gold/20">
      <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div class="text-sm text-gray-400 mb-1">Current Plan</div>
          <div class="text-2xl font-bold text-gold">{{ billing.tierName }}</div>
          <div class="text-sm text-gray-500 mt-1">
            {{ billing.isFreeTrial ? 'Free Trial' : `${{ free_trial: '0', seeker: '10', adept: '30', opus: '100', azothic: '300' }[billing.status.tier] || '?'}/month` }}
          </div>
        </div>

        <div class="flex items-center gap-6">
          <!-- Usage -->
          <div v-if="billing.status.messages_limit" class="text-center">
            <div class="text-sm text-gray-400 mb-1">Messages Used</div>
            <div class="text-xl font-semibold">
              {{ billing.status.messages_used }} / {{ billing.status.messages_limit }}
            </div>
            <div class="w-32 h-2 bg-gray-700 rounded-full mt-2 overflow-hidden">
              <div
                class="h-full transition-all duration-300"
                :class="{
                  'bg-green-500': billing.usagePercent < 60,
                  'bg-yellow-500': billing.usagePercent >= 60 && billing.usagePercent < 90,
                  'bg-red-500': billing.usagePercent >= 90
                }"
                :style="{ width: `${billing.usagePercent}%` }"
              ></div>
            </div>
          </div>
          <div v-else class="text-center">
            <div class="text-sm text-gray-400 mb-1">Messages</div>
            <div class="text-xl font-semibold text-gold">Unlimited</div>
          </div>

          <!-- Feature Credits -->
          <div v-if="billing.hasFeatureCredits" class="text-center">
            <div class="text-sm text-gray-400 mb-1">Feature Credits</div>
            <div class="text-sm">
              <span class="text-gold font-semibold">{{ billing.featureCredits.opus_messages }}</span>
              <span class="text-gray-500 text-xs"> Opus</span>
              <span class="mx-1 text-gray-600">|</span>
              <span class="text-gold font-semibold">{{ billing.featureCredits.suno_generations }}</span>
              <span class="text-gray-500 text-xs"> Suno</span>
              <span class="mx-1 text-gray-600">|</span>
              <span class="text-gold font-semibold">{{ billing.featureCredits.training_jobs }}</span>
              <span class="text-gray-500 text-xs"> Train</span>
            </div>
          </div>

          <!-- Legacy Credits -->
          <div v-if="billing.status.credit_balance_cents > 0" class="text-center">
            <div class="text-sm text-gray-400 mb-1">Credits</div>
            <div class="text-sm font-semibold">${{ billing.status.credit_balance_usd.toFixed(2) }}</div>
          </div>

          <!-- Manage Button -->
          <button
            v-if="billing.status.tier !== 'free_trial'"
            @click="manageSubscription"
            :disabled="loadingAction === 'portal'"
            class="px-4 py-2 bg-surface border border-gray-600 rounded-lg hover:border-gold/50 transition-colors disabled:opacity-50"
          >
            {{ loadingAction === 'portal' ? 'Loading...' : 'Manage Subscription' }}
          </button>
        </div>
      </div>

      <!-- Period End Warning -->
      <div v-if="billing.status.cancel_at_period_end" class="mt-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-yellow-400 text-sm">
        Your subscription will end on {{ formatDate(billing.status.current_period_end) }}
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex justify-center mb-8">
      <div class="inline-flex bg-surface rounded-lg p-1 border border-gray-700">
        <button
          @click="activeTab = 'plans'"
          :class="[
            'px-4 py-2 rounded-lg text-sm transition-colors',
            activeTab === 'plans' ? 'bg-gold text-black font-medium' : 'text-gray-400 hover:text-white'
          ]"
        >Subscription Plans</button>
        <button
          @click="activeTab = 'packs'; fetchUsageIfNeeded()"
          :class="[
            'px-4 py-2 rounded-lg text-sm transition-colors',
            activeTab === 'packs' ? 'bg-gold text-black font-medium' : 'text-gray-400 hover:text-white'
          ]"
        >Feature Packs</button>
        <button
          @click="activeTab = 'usage'; fetchUsageIfNeeded()"
          :class="[
            'px-4 py-2 rounded-lg text-sm transition-colors',
            activeTab === 'usage' ? 'bg-gold text-black font-medium' : 'text-gray-400 hover:text-white'
          ]"
        >Usage</button>
        <button
          @click="activeTab = 'history'; billing.fetchTransactions()"
          :class="[
            'px-4 py-2 rounded-lg text-sm transition-colors',
            activeTab === 'history' ? 'bg-gold text-black font-medium' : 'text-gray-400 hover:text-white'
          ]"
        >History</button>
      </div>
    </div>

    <!-- Checkout Error Banner -->
    <div v-if="checkoutError" class="mb-4 p-3 rounded-lg bg-red-500/20 text-red-400 border border-red-500/30 text-sm">
      {{ checkoutError }}
    </div>

    <!-- Plans Tab -->
    <div v-if="activeTab === 'plans'" class="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
      <div
        v-for="tier in (billing.pricing?.tiers || [])"
        :key="tier.id"
        :class="[
          'relative rounded-xl p-6 border transition-all',
          tier.popular
            ? 'bg-gold/5 border-gold shadow-lg shadow-gold/10'
            : 'bg-surface border-gray-700 hover:border-gray-600',
          billing.status.tier === tier.id && 'ring-2 ring-gold/50'
        ]"
      >
        <!-- Popular Badge -->
        <div
          v-if="tier.popular"
          class="absolute -top-3 left-1/2 -translate-x-1/2 bg-gold text-black text-xs font-bold px-3 py-1 rounded-full"
        >
          MOST POPULAR
        </div>

        <!-- Current Badge -->
        <div
          v-if="billing.status.tier === tier.id"
          class="absolute -top-3 right-4 bg-green-500 text-white text-xs font-bold px-3 py-1 rounded-full"
        >
          CURRENT
        </div>

        <!-- Header -->
        <div class="text-center mb-6">
          <h3 class="text-2xl font-bold mb-1">{{ tier.name }}</h3>
          <p class="text-gray-400 text-sm">{{ tier.tagline }}</p>
          <div class="mt-4">
            <span class="text-4xl font-bold">${{ tier.price_monthly }}</span>
            <span v-if="tier.price_monthly > 0" class="text-gray-400">/mo</span>
            <span v-else class="text-gray-400 text-sm ml-1">forever</span>
          </div>
          <div class="text-sm text-gray-500 mt-1">
            {{ tier.messages_per_month ? `${tier.messages_per_month.toLocaleString()} messages/month` : 'Unlimited messages' }}
          </div>
        </div>

        <!-- Features -->
        <ul class="space-y-3 mb-6">
          <li v-for="feature in tier.features" :key="feature" class="flex items-start gap-2 text-sm">
            <svg class="w-5 h-5 text-gold flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
            </svg>
            <span class="text-gray-300">{{ feature }}</span>
          </li>
        </ul>

        <!-- CTA Button -->
        <button
          @click="selectPlan(tier.id)"
          :disabled="tier.id === 'free_trial' || billing.status.tier === tier.id || loadingAction === tier.id"
          :class="[
            'w-full py-3 rounded-lg font-medium transition-all',
            tier.popular
              ? 'bg-gold text-black hover:bg-gold/90'
              : 'bg-surface border border-gray-600 hover:border-gold/50',
            (tier.id === 'free_trial' || billing.status.tier === tier.id) && 'opacity-50 cursor-not-allowed'
          ]"
        >
          {{
            loadingAction === tier.id
              ? 'Processing...'
              : billing.status.tier === tier.id
                ? 'Current Plan'
                : tier.id === 'free_trial'
                  ? 'Free Trial'
                  : `Upgrade to ${tier.name}`
          }}
        </button>
      </div>
    </div>

    <!-- Feature Packs Tab -->
    <div v-if="activeTab === 'packs'" class="max-w-3xl mx-auto">
      <div class="text-center mb-8">
        <h2 class="text-2xl font-bold mb-2">Feature Packs</h2>
        <p class="text-gray-400">
          Purchase additional Opus messages, Suno generations, and training jobs.
          Credits roll over once (expire at end of next billing period).
        </p>
      </div>

      <!-- Tier Gate -->
      <div v-if="!billing.canBuyPacks" class="text-center py-8">
        <p class="text-gray-400 mb-4">Feature Packs are available for Adept members and above.</p>
        <button @click="activeTab = 'plans'" class="px-6 py-2 bg-gold text-black rounded-lg font-medium hover:bg-gold/90">
          View Plans
        </button>
      </div>

      <div v-else class="space-y-6">
        <!-- Feature Credits Summary -->
        <div v-if="billing.hasFeatureCredits" class="bg-surface rounded-xl p-4 border border-gray-700 mb-6">
          <h3 class="text-sm font-medium text-gray-400 mb-3">Your Feature Credits</h3>
          <div class="grid grid-cols-3 gap-4 text-center">
            <div>
              <div class="text-xl font-bold text-gold">{{ billing.featureCredits.opus_messages }}</div>
              <div class="text-xs text-gray-400">Opus Messages</div>
            </div>
            <div>
              <div class="text-xl font-bold text-gold">{{ billing.featureCredits.suno_generations }}</div>
              <div class="text-xs text-gray-400">Suno Generations</div>
            </div>
            <div>
              <div class="text-xl font-bold text-gold">{{ billing.featureCredits.training_jobs }}</div>
              <div class="text-xs text-gray-400">Training Jobs</div>
            </div>
          </div>
        </div>

        <!-- Pack Cards -->
        <div class="grid md:grid-cols-3 gap-6">
          <!-- Spark Pack -->
          <div class="bg-surface rounded-xl p-6 border border-gray-700 hover:border-gold/30 transition-all">
            <div class="text-center mb-4">
              <h3 class="text-xl font-bold mb-1">Spark</h3>
              <div class="text-3xl font-bold text-gold mb-1">$5</div>
              <p class="text-sm text-gray-400">Choose one resource</p>
            </div>
            <div class="space-y-2 mb-4">
              <label class="flex items-center gap-3 p-2 rounded-lg cursor-pointer border transition-colors"
                     :class="selectedResource === 'opus_messages' ? 'border-gold/50 bg-gold/10' : 'border-gray-700'">
                <input type="radio" v-model="selectedResource" value="opus_messages" class="accent-yellow-500" />
                <span class="text-sm">50 Opus Messages</span>
              </label>
              <label class="flex items-center gap-3 p-2 rounded-lg cursor-pointer border transition-colors"
                     :class="selectedResource === 'suno_generations' ? 'border-gold/50 bg-gold/10' : 'border-gray-700'">
                <input type="radio" v-model="selectedResource" value="suno_generations" class="accent-yellow-500" />
                <span class="text-sm">20 Suno Generations</span>
              </label>
              <label class="flex items-center gap-3 p-2 rounded-lg cursor-pointer border transition-colors"
                     :class="selectedResource === 'training_jobs' ? 'border-gold/50 bg-gold/10' : 'border-gray-700'">
                <input type="radio" v-model="selectedResource" value="training_jobs" class="accent-yellow-500" />
                <span class="text-sm">2 Training Jobs</span>
              </label>
            </div>
            <button
              @click="buyPack('spark', selectedResource)"
              :disabled="loadingAction === 'pack-spark'"
              class="w-full py-3 bg-gold text-black rounded-lg font-medium hover:bg-gold/90 transition-colors disabled:opacity-50"
            >
              {{ loadingAction === 'pack-spark' ? 'Processing...' : 'Buy Spark' }}
            </button>
          </div>

          <!-- Flame Pack -->
          <div class="bg-surface rounded-xl p-6 border border-gold/30 hover:border-gold/50 transition-all">
            <div class="text-center mb-4">
              <h3 class="text-xl font-bold mb-1">Flame</h3>
              <div class="text-3xl font-bold text-gold mb-1">$15</div>
              <p class="text-sm text-gray-400">All three resources</p>
            </div>
            <div class="space-y-2 mb-4 text-sm text-gray-300">
              <div class="flex justify-between"><span>Opus Messages</span><span class="text-gold font-medium">150</span></div>
              <div class="flex justify-between"><span>Suno Generations</span><span class="text-gold font-medium">50</span></div>
              <div class="flex justify-between"><span>Training Jobs</span><span class="text-gold font-medium">5</span></div>
            </div>
            <button
              @click="buyPack('flame')"
              :disabled="loadingAction === 'pack-flame'"
              class="w-full py-3 bg-gold text-black rounded-lg font-medium hover:bg-gold/90 transition-colors disabled:opacity-50"
            >
              {{ loadingAction === 'pack-flame' ? 'Processing...' : 'Buy Flame' }}
            </button>
          </div>

          <!-- Inferno Pack -->
          <div class="bg-surface rounded-xl p-6 border border-gray-700 hover:border-gold/30 transition-all">
            <div class="text-center mb-4">
              <h3 class="text-xl font-bold mb-1">Inferno</h3>
              <div class="text-3xl font-bold text-gold mb-1">$40</div>
              <p class="text-sm text-gray-400">All three resources</p>
            </div>
            <div class="space-y-2 mb-4 text-sm text-gray-300">
              <div class="flex justify-between"><span>Opus Messages</span><span class="text-gold font-medium">500</span></div>
              <div class="flex justify-between"><span>Suno Generations</span><span class="text-gold font-medium">200</span></div>
              <div class="flex justify-between"><span>Training Jobs</span><span class="text-gold font-medium">15</span></div>
            </div>
            <button
              @click="buyPack('inferno')"
              :disabled="loadingAction === 'pack-inferno'"
              class="w-full py-3 bg-gold text-black rounded-lg font-medium hover:bg-gold/90 transition-colors disabled:opacity-50"
            >
              {{ loadingAction === 'pack-inferno' ? 'Processing...' : 'Buy Inferno' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Coupon Redemption Section (keep from old code) -->
      <div class="mt-12 max-w-md mx-auto">
        <div class="bg-surface rounded-xl p-6 border border-gray-700">
          <h3 class="text-lg font-semibold mb-4 text-center">Have a Coupon?</h3>

          <div class="flex gap-2">
            <input
              v-model="couponCode"
              type="text"
              placeholder="Enter coupon code"
              class="flex-1 px-4 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:border-gold focus:outline-none uppercase"
              :disabled="loadingAction === 'coupon'"
              @keyup.enter="redeemCoupon"
            />
            <button
              @click="redeemCoupon"
              :disabled="!couponCode.trim() || loadingAction === 'coupon'"
              class="px-6 py-2 bg-gold text-black rounded-lg font-medium hover:bg-gold/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {{ loadingAction === 'coupon' ? 'Redeeming...' : 'Redeem' }}
            </button>
          </div>

          <div
            v-if="couponMessage"
            :class="[
              'mt-3 p-3 rounded-lg text-sm',
              couponMessage.success
                ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                : 'bg-red-500/20 text-red-400 border border-red-500/30'
            ]"
          >
            {{ couponMessage.text }}
          </div>
        </div>
      </div>
    </div>

    <!-- Usage Tab -->
    <div v-if="activeTab === 'usage'" class="max-w-3xl mx-auto">
      <div class="text-center mb-8">
        <h2 class="text-2xl font-bold mb-2">Usage Dashboard</h2>
        <p class="text-gray-400">
          Track your usage across all features this billing period.
        </p>
      </div>

      <div v-if="!billing.usageSummary" class="text-center py-8 text-gray-400">
        Loading usage data...
      </div>

      <div v-else>
        <!-- Overall Messages -->
        <div class="bg-surface rounded-xl p-6 border border-gray-700 mb-6">
          <div class="flex justify-between items-center mb-2">
            <h3 class="font-semibold">Total Messages</h3>
            <span class="text-sm text-gray-400">
              {{ billing.usageSummary.total_messages_used }}
              {{ billing.usageSummary.total_messages_limit ? `/ ${billing.usageSummary.total_messages_limit.toLocaleString()}` : '(Unlimited)' }}
            </span>
          </div>
          <div class="w-full h-3 bg-gray-700 rounded-full overflow-hidden">
            <div
              v-if="billing.usageSummary.total_messages_limit"
              class="h-full transition-all duration-500 rounded-full"
              :class="getBarColor(billing.usageSummary.total_messages_used, billing.usageSummary.total_messages_limit)"
              :style="{ width: Math.min(100, (billing.usageSummary.total_messages_used / billing.usageSummary.total_messages_limit) * 100) + '%' }"
            ></div>
          </div>
        </div>

        <!-- Per-Resource Breakdown -->
        <div class="space-y-4">
          <div
            v-for="resource in billing.usageSummary.resources"
            :key="resource.counter_type"
            class="bg-surface rounded-xl p-4 border border-gray-700"
          >
            <div class="flex justify-between items-center mb-2">
              <span class="font-medium text-sm">{{ resource.display_name }}</span>
              <span class="text-sm text-gray-400">
                {{ resource.current_count }}
                <template v-if="resource.effective_limit !== null">
                  / {{ resource.effective_limit.toLocaleString() }}
                  <span v-if="resource.feature_credit_bonus > 0" class="text-gold text-xs">
                    (+{{ resource.feature_credit_bonus }} credits)
                  </span>
                </template>
                <template v-else>
                  (Unlimited)
                </template>
              </span>
            </div>
            <div v-if="resource.effective_limit !== null" class="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
              <div
                class="h-full transition-all duration-500 rounded-full"
                :class="{
                  'bg-green-500': resource.status === 'green',
                  'bg-yellow-500': resource.status === 'yellow',
                  'bg-red-500': resource.status === 'red',
                }"
                :style="{ width: Math.min(100, resource.percentage_used || 0) + '%' }"
              ></div>
            </div>
            <div v-if="resource.percentage_used > 80 && resource.effective_limit !== null" class="mt-1 flex justify-between items-center">
              <span class="text-xs" :class="resource.percentage_used >= 100 ? 'text-red-400' : 'text-amber-400'">
                {{ resource.percentage_used >= 100 ? 'Limit reached' : 'Approaching limit' }}
              </span>
              <button
                v-if="billing.canBuyPacks"
                @click="activeTab = 'packs'"
                class="text-xs text-gold hover:underline"
              >
                Buy More
              </button>
            </div>
          </div>
        </div>

        <!-- Feature Credits Remaining -->
        <div class="mt-8 bg-surface rounded-xl p-6 border border-gray-700">
          <h3 class="font-semibold mb-4">Feature Credits Remaining</h3>
          <div class="grid grid-cols-3 gap-4 text-center">
            <div>
              <div class="text-2xl font-bold text-gold">{{ billing.featureCredits.opus_messages }}</div>
              <div class="text-xs text-gray-400">Opus Messages</div>
            </div>
            <div>
              <div class="text-2xl font-bold text-gold">{{ billing.featureCredits.suno_generations }}</div>
              <div class="text-xs text-gray-400">Suno Generations</div>
            </div>
            <div>
              <div class="text-2xl font-bold text-gold">{{ billing.featureCredits.training_jobs }}</div>
              <div class="text-xs text-gray-400">Training Jobs</div>
            </div>
          </div>
          <div v-if="billing.canBuyPacks" class="mt-4 text-center">
            <button @click="activeTab = 'packs'" class="text-sm text-gold hover:underline">
              Purchase more credits
            </button>
          </div>
        </div>

        <div class="mt-4 text-center text-xs text-gray-500">
          Period: {{ billing.usageSummary.period }}
        </div>
      </div>
    </div>

    <!-- History Tab -->
    <div v-if="activeTab === 'history'" class="max-w-3xl mx-auto">
      <h2 class="text-2xl font-bold mb-6 text-center">Transaction History</h2>

      <div v-if="billing.loading" class="text-center py-8 text-gray-400">
        Loading transactions...
      </div>

      <div v-else-if="billing.transactions.length === 0" class="text-center py-8 text-gray-500">
        No transactions yet
      </div>

      <div v-else class="bg-surface rounded-xl border border-gray-700 overflow-hidden">
        <table class="w-full">
          <thead class="bg-gray-800/50">
            <tr>
              <th class="text-left px-4 py-3 text-sm font-medium text-gray-400">Date</th>
              <th class="text-left px-4 py-3 text-sm font-medium text-gray-400">Type</th>
              <th class="text-left px-4 py-3 text-sm font-medium text-gray-400">Description</th>
              <th class="text-right px-4 py-3 text-sm font-medium text-gray-400">Amount</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-700">
            <tr v-for="tx in billing.transactions" :key="tx.id" class="hover:bg-gray-800/30">
              <td class="px-4 py-3 text-sm text-gray-300">{{ formatDate(tx.created_at) }}</td>
              <td class="px-4 py-3">
                <span
                  :class="[
                    'text-xs px-2 py-1 rounded-full',
                    tx.transaction_type === 'purchase' ? 'bg-green-500/20 text-green-400' :
                    tx.transaction_type === 'usage' ? 'bg-blue-500/20 text-blue-400' :
                    tx.transaction_type === 'bonus' ? 'bg-gold/20 text-gold' :
                    'bg-gray-500/20 text-gray-400'
                  ]"
                >
                  {{ tx.transaction_type }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-300">{{ tx.description || '-' }}</td>
              <td
                class="px-4 py-3 text-sm text-right font-mono"
                :class="tx.amount_cents > 0 ? 'text-green-400' : 'text-red-400'"
              >
                {{ tx.amount_cents > 0 ? '+' : '' }}{{ (tx.amount_cents / 100).toFixed(2) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Not Authenticated Message -->
    <div v-if="!auth.isAuthenticated" class="mt-12 text-center">
      <div class="bg-surface rounded-xl p-8 border border-gray-700 max-w-md mx-auto">
        <h3 class="text-xl font-bold mb-2">Sign in to Subscribe</h3>
        <p class="text-gray-400 mb-4">Create an account to start your journey</p>
        <router-link to="/login" class="inline-block px-6 py-3 bg-gold text-black rounded-lg font-medium hover:bg-gold/90 transition-colors">
          Sign In
        </router-link>
      </div>
    </div>
  </div>
</template>
