<script setup>
import { watch, computed } from 'vue'
import { RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useDevMode } from '@/composables/useDevMode'
import { useMusicStore } from '@/stores/music'
import Navbar from '@/components/Navbar.vue'
import AlchemicalParticles from '@/components/AlchemicalParticles.vue'
import MusicPlayer from '@/components/music/MusicPlayer.vue'
import ToastContainer from '@/components/ToastContainer.vue'

const auth = useAuthStore()
const music = useMusicStore()
const { pacMode, justActivatedPac } = useDevMode()

// Add bottom padding when music player is visible
const hasActivePlayer = computed(() => !!music.currentTrack)

// Apply pac-mode class to body for global styling
watch(pacMode, (active) => {
  if (active) {
    document.body.classList.add('pac-mode')
  } else {
    document.body.classList.remove('pac-mode')
  }
}, { immediate: true })
</script>

<template>
  <div
    class="min-h-screen transition-all duration-1000"
    :class="{
      'bg-apex-darker': !pacMode,
      'pac-activate': justActivatedPac
    }"
  >
    <!-- Alchemical floating symbols (PAC mode only) -->
    <AlchemicalParticles />

    <!-- Navbar -->
    <Navbar v-if="auth.isAuthenticated" />

    <!-- Main content -->
    <main
      :class="[
        auth.isAuthenticated ? 'pt-16' : '',
        hasActivePlayer ? 'pb-20' : ''
      ]"
      class="relative"
    >
      <RouterView />
    </main>

    <!-- Persistent Music Player -->
    <MusicPlayer v-if="auth.isAuthenticated" />

    <!-- Global Toast Notifications -->
    <ToastContainer />

    <!-- Global Beta Footer -->
    <footer class="relative border-t border-apex-border bg-apex-darker/80 py-3 px-4 text-center">
      <div class="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-center gap-2 sm:gap-6 text-xs text-gray-500">
        <span class="px-2 py-0.5 bg-amber-500/10 text-amber-400 rounded text-[10px] font-semibold uppercase tracking-wider">Beta</span>
        <span>&copy; 2026 ApexAurum</span>
        <div class="flex gap-4">
          <router-link to="/terms" class="hover:text-gray-300 transition-colors">Terms</router-link>
          <router-link to="/privacy" class="hover:text-gray-300 transition-colors">Privacy</router-link>
        </div>
      </div>
    </footer>
  </div>
</template>

<style>
/* Global scrollbar styling */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #1a1a1a;
}

::-webkit-scrollbar-thumb {
  background: #444;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #555;
}

/* PAC mode scrollbar */
.pac-mode ::-webkit-scrollbar-track {
  background: #0a0612;
}

.pac-mode ::-webkit-scrollbar-thumb {
  background: rgba(255, 215, 0, 0.3);
}

.pac-mode ::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 215, 0, 0.5);
}
</style>
