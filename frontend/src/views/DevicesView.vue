<script setup>
/**
 * Devices View - ApexPocket Device Management
 *
 * Register, monitor, and manage ApexPocket companion devices.
 * Handles device tokens, soul state display, and lifecycle operations.
 */

import { ref, onMounted } from 'vue'
import { useDevicesStore } from '@/stores/devices'

const store = useDevicesStore()

const showAddModal = ref(false)
const newDeviceName = ref('')
const creating = ref(false)
const copied = ref(false)

onMounted(() => {
  store.fetchDevices()
})

// ═══════════════════════════════════════════════════════════════════════════════
// DEVICE ACTIONS
// ═══════════════════════════════════════════════════════════════════════════════

async function handleCreate() {
  if (!newDeviceName.value.trim()) return
  creating.value = true
  try {
    await store.createDevice(newDeviceName.value.trim())
    showAddModal.value = false
    newDeviceName.value = ''
  } catch (e) {
    // error shown via store.error
  } finally {
    creating.value = false
  }
}

async function handleRotate(device) {
  if (!confirm(`Rotate token for "${device.device_name}"? The old token will stop working immediately.`)) return
  try {
    await store.rotateToken(device.id)
  } catch (e) {
    // error shown via store.error
  }
}

function confirmRevoke(device) {
  if (!confirm(`Revoke "${device.device_name}"? The device will lose access immediately.`)) return
  store.revokeDevice(device.id)
}

function confirmDelete(device) {
  if (!confirm(`Permanently delete "${device.device_name}"? This cannot be undone.`)) return
  store.deleteDevice(device.id)
}

// ═══════════════════════════════════════════════════════════════════════════════
// TOKEN ACTIONS
// ═══════════════════════════════════════════════════════════════════════════════

async function copyToken() {
  try {
    await navigator.clipboard.writeText(store.newDeviceToken)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // Fallback - select the text
  }
}

function downloadConfig() {
  const blob = new Blob([store.newConfigJson], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'config.json'
  a.click()
  URL.revokeObjectURL(url)
}

// ═══════════════════════════════════════════════════════════════════════════════
// STATUS HELPERS
// ═══════════════════════════════════════════════════════════════════════════════

function statusDotClass(device) {
  if (device.status === 'revoked') return 'bg-red-400'
  if (!device.last_seen_at) return 'bg-gray-500'
  const ago = Date.now() - new Date(device.last_seen_at).getTime()
  if (ago < 5 * 60 * 1000) return 'bg-green-400'
  if (ago < 60 * 60 * 1000) return 'bg-yellow-400'
  return 'bg-gray-500'
}

function statusBadgeClass(device) {
  if (device.status === 'revoked') return 'bg-red-500/20 text-red-400'
  if (!device.last_seen_at) return 'bg-gray-500/20 text-gray-400'
  const ago = Date.now() - new Date(device.last_seen_at).getTime()
  if (ago < 5 * 60 * 1000) return 'bg-green-500/20 text-green-400'
  if (ago < 60 * 60 * 1000) return 'bg-yellow-500/20 text-yellow-400'
  return 'bg-gray-500/20 text-gray-400'
}

function deviceStatusText(device) {
  if (device.status === 'revoked') return 'Revoked'
  if (!device.last_seen_at) return 'Never seen'
  const ago = Date.now() - new Date(device.last_seen_at).getTime()
  if (ago < 5 * 60 * 1000) return 'Online'
  if (ago < 60 * 60 * 1000) return 'Idle'
  return 'Offline'
}

function formatLastSeen(dateStr) {
  if (!dateStr) return 'Never'
  const ago = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(ago / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function soulStateColor(soul) {
  const E = soul.E || 0
  if (E < 0.5) return '#ef4444'      // red - PROTECTING
  if (E < 1.0) return '#f97316'      // orange - GUARDED
  if (E < 2.0) return '#eab308'      // yellow - TENDER
  if (E < 5.0) return '#22c55e'      // green - WARM
  if (E < 12.0) return '#06b6d4'     // cyan - FLOURISHING
  if (E < 30.0) return '#3b82f6'     // blue - RADIANT
  return '#a855f7'                     // purple - TRANSCENDENT
}
</script>

<template>
  <div class="min-h-screen bg-apex-dark pt-20 pb-12 px-4">
    <div class="max-w-4xl mx-auto">

      <!-- Header -->
      <div class="flex items-center justify-between mb-8">
        <div>
          <h1 class="text-2xl font-bold text-white">Devices</h1>
          <p class="text-gray-400 text-sm mt-1">Manage your ApexPocket companions</p>
        </div>
        <button
          @click="showAddModal = true"
          class="px-4 py-2 bg-gold text-black rounded font-medium hover:bg-gold/90 transition-colors"
        >
          Add Device
        </button>
      </div>

      <!-- Error display -->
      <div
        v-if="store.error"
        class="mb-6 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm"
      >
        {{ store.error }}
      </div>

      <!-- Loading state -->
      <div v-if="store.loading" class="text-center py-20 text-gray-400">
        Loading devices...
      </div>

      <!-- Empty state -->
      <div
        v-else-if="!store.devices || store.devices.length === 0"
        class="text-center py-20"
      >
        <div class="bg-white/5 border border-apex-border rounded-lg p-8 max-w-md mx-auto">
          <p class="text-gray-400 mb-6">
            No devices registered yet. Add your first ApexPocket to get started.
          </p>
          <button
            @click="showAddModal = true"
            class="px-4 py-2 bg-gold text-black rounded font-medium hover:bg-gold/90 transition-colors"
          >
            Add Device
          </button>
        </div>
      </div>

      <!-- Device grid -->
      <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div
          v-for="device in store.devices"
          :key="device.id"
          class="bg-white/5 border border-apex-border rounded-lg p-4"
        >
          <!-- Header row -->
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-3">
              <!-- Status dot -->
              <span class="w-2.5 h-2.5 rounded-full" :class="statusDotClass(device)"></span>
              <div>
                <h3 class="font-medium text-white">{{ device.device_name }}</h3>
                <span class="text-xs text-gray-500">{{ device.device_type === 'apex_pocket' ? 'ApexPocket' : device.device_type }}</span>
              </div>
            </div>
            <!-- Status badge -->
            <span class="text-xs px-2 py-0.5 rounded" :class="statusBadgeClass(device)">
              {{ deviceStatusText(device) }}
            </span>
          </div>

          <!-- Info rows -->
          <div class="space-y-2 text-sm">
            <!-- Token prefix -->
            <div class="flex justify-between">
              <span class="text-gray-500">Token</span>
              <code class="text-gray-400 text-xs">{{ device.token_prefix }}...</code>
            </div>

            <!-- Last seen -->
            <div class="flex justify-between">
              <span class="text-gray-500">Last seen</span>
              <span class="text-gray-400">{{ formatLastSeen(device.last_seen_at) }}</span>
            </div>

            <!-- Firmware -->
            <div v-if="device.firmware_version" class="flex justify-between">
              <span class="text-gray-500">Firmware</span>
              <span class="text-gray-400">{{ device.firmware_version }}</span>
            </div>

            <!-- Soul State -->
            <div v-if="device.soul_state && device.soul_state.E !== undefined" class="mt-3 pt-3 border-t border-white/5">
              <div class="flex items-center justify-between mb-1">
                <span class="text-gray-500">Soul Energy</span>
                <span class="text-sm font-medium" :style="{ color: soulStateColor(device.soul_state) }">
                  E={{ device.soul_state.E?.toFixed(1) }} {{ device.soul_state.state || '' }}
                </span>
              </div>
              <!-- E bar -->
              <div class="h-1.5 bg-white/5 rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :style="{ width: Math.min(device.soul_state.E / 30 * 100, 100) + '%', backgroundColor: soulStateColor(device.soul_state) }"
                ></div>
              </div>
              <div v-if="device.soul_state.interactions" class="text-xs text-gray-600 mt-1">
                {{ device.soul_state.interactions }} interactions
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="mt-4 pt-3 border-t border-white/5 flex gap-2">
            <button
              v-if="device.status === 'active'"
              @click="confirmRevoke(device)"
              class="text-xs px-3 py-1.5 bg-white/5 hover:bg-red-500/20 text-gray-400 hover:text-red-400 rounded transition-colors"
            >
              Revoke
            </button>
            <button
              v-if="device.status === 'active'"
              @click="handleRotate(device)"
              class="text-xs px-3 py-1.5 bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white rounded transition-colors"
            >
              Rotate Token
            </button>
            <button
              @click="confirmDelete(device)"
              class="text-xs px-3 py-1.5 bg-white/5 hover:bg-red-500/20 text-gray-400 hover:text-red-400 rounded transition-colors ml-auto"
            >
              Delete
            </button>
          </div>
        </div>
      </div>

      <!-- Add Device Modal -->
      <div
        v-if="showAddModal"
        class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
        @click.self="showAddModal = false"
      >
        <div class="bg-apex-dark border border-apex-border rounded-lg shadow-2xl w-full max-w-md mx-4 p-6">
          <h2 class="text-lg font-medium text-white mb-4">Add Device</h2>

          <div class="space-y-4">
            <div>
              <label class="block text-sm text-gray-400 mb-1">Device Name</label>
              <input
                v-model="newDeviceName"
                type="text"
                placeholder="My Pocket"
                class="w-full bg-white/5 border border-apex-border rounded px-3 py-2 text-white placeholder-gray-600 focus:outline-none focus:border-gold"
                maxlength="100"
                @keyup.enter="handleCreate"
              />
            </div>
          </div>

          <div class="flex gap-3 mt-6">
            <button
              @click="showAddModal = false"
              class="flex-1 px-4 py-2 bg-white/5 text-gray-400 rounded hover:bg-white/10 transition-colors"
            >
              Cancel
            </button>
            <button
              @click="handleCreate"
              :disabled="!newDeviceName.trim() || creating"
              class="flex-1 px-4 py-2 bg-gold text-black rounded font-medium hover:bg-gold/90 transition-colors disabled:opacity-50"
            >
              {{ creating ? 'Creating...' : 'Create Device' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Token Reveal Modal -->
      <div
        v-if="store.newDeviceToken"
        class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
      >
        <div class="bg-apex-dark border border-apex-border rounded-lg shadow-2xl w-full max-w-lg mx-4 p-6">
          <div class="flex items-center gap-2 mb-4">
            <span class="w-3 h-3 rounded-full bg-green-400"></span>
            <h2 class="text-lg font-medium text-white">Device Token Created</h2>
          </div>

          <!-- Token display -->
          <div class="bg-black/40 border border-apex-border rounded p-3 mb-3">
            <code class="text-gold text-sm break-all select-all">{{ store.newDeviceToken }}</code>
          </div>

          <!-- Warning -->
          <p class="text-amber-400 text-sm mb-4">
            This token is shown once. Save it securely -- it cannot be retrieved later.
          </p>

          <!-- Actions -->
          <div class="flex gap-3">
            <button
              @click="copyToken"
              class="flex-1 px-4 py-2 bg-white/5 text-gray-300 rounded hover:bg-white/10 transition-colors"
            >
              {{ copied ? 'Copied!' : 'Copy Token' }}
            </button>
            <button
              @click="downloadConfig"
              class="flex-1 px-4 py-2 bg-white/5 text-gray-300 rounded hover:bg-white/10 transition-colors"
            >
              Download config.json
            </button>
          </div>

          <button
            @click="store.clearNewToken()"
            class="w-full mt-3 px-4 py-2 bg-gold text-black rounded font-medium hover:bg-gold/90 transition-colors"
          >
            Done
          </button>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
/* Minimal scoped styles - Tailwind handles the rest */
code {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}
</style>
