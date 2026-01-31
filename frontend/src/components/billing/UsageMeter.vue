<script setup>
import { computed, onMounted } from 'vue'
import { useBillingStore } from '@/stores/billing'
import { useAuthStore } from '@/stores/auth'

const billing = useBillingStore()
const auth = useAuthStore()

const props = defineProps({
  compact: {
    type: Boolean,
    default: false
  }
})

onMounted(() => {
  if (auth.isAuthenticated) {
    billing.fetchStatus()
  }
})

const statusColor = computed(() => {
  if (billing.status.at_limit) return 'text-red-400'
  if (billing.status.near_limit) return 'text-yellow-400'
  return 'text-green-400'
})

const barColor = computed(() => {
  if (billing.usagePercent >= 90) return 'bg-red-500'
  if (billing.usagePercent >= 60) return 'bg-yellow-500'
  return 'bg-green-500'
})
</script>

<template>
  <div v-if="auth.isAuthenticated" class="usage-meter">
    <!-- Compact Mode (for narrow sidebars) -->
    <div v-if="compact" class="text-center">
      <div class="text-xs text-gray-400 mb-1">{{ billing.tierName }}</div>
      <div v-if="billing.status.messages_limit" class="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div
          class="h-full transition-all duration-300"
          :class="barColor"
          :style="{ width: `${billing.usagePercent}%` }"
        ></div>
      </div>
      <div v-else class="text-xs text-gold">Unlimited</div>
      <router-link
        to="/billing"
        class="text-xs text-gray-500 hover:text-gold transition-colors mt-1 block"
      >
        Upgrade
      </router-link>
    </div>

    <!-- Full Mode -->
    <div v-else class="p-3 bg-surface/50 rounded-lg border border-gray-700/50">
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm font-medium text-gold">{{ billing.tierName }}</span>
        <router-link
          to="/billing"
          class="text-xs text-gray-400 hover:text-gold transition-colors"
        >
          {{ billing.isFree ? 'Upgrade' : 'Manage' }}
        </router-link>
      </div>

      <!-- Messages Progress -->
      <div v-if="billing.status.messages_limit" class="mb-2">
        <div class="flex justify-between text-xs text-gray-400 mb-1">
          <span>Messages</span>
          <span :class="statusColor">
            {{ billing.status.messages_used }} / {{ billing.status.messages_limit }}
          </span>
        </div>
        <div class="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
          <div
            class="h-full transition-all duration-300"
            :class="barColor"
            :style="{ width: `${billing.usagePercent}%` }"
          ></div>
        </div>
      </div>

      <div v-else class="text-sm text-center text-gold mb-2">
        Unlimited Messages
      </div>

      <!-- Credits -->
      <div class="flex items-center justify-between text-xs">
        <span class="text-gray-400">Credits</span>
        <span :class="billing.hasCredits ? 'text-green-400' : 'text-gray-500'">
          ${{ billing.status.credit_balance_usd.toFixed(2) }}
        </span>
      </div>

      <!-- Warnings -->
      <div v-if="billing.status.at_limit && !billing.hasCredits" class="mt-2 text-xs text-red-400 text-center">
        Limit reached - upgrade or buy credits
      </div>
      <div v-else-if="billing.status.near_limit" class="mt-2 text-xs text-yellow-400 text-center">
        Running low on messages
      </div>
    </div>
  </div>
</template>
