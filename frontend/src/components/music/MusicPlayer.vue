<script setup>
/**
 * MusicPlayer - Sticky bottom audio player
 *
 * Like Spotify's mini-player. Shows current track, play controls,
 * progress bar, and volume. Integrates with the music store.
 */

import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import { useMusicStore } from '@/stores/music'

const music = useMusicStore()

// Audio element ref
const audioRef = ref(null)

// Local state for progress dragging
const isDragging = ref(false)
const dragProgress = ref(0)

// Waveform animation
const waveformBars = ref([0.3, 0.5, 0.7, 0.4, 0.8, 0.6, 0.3, 0.5])

const displayProgress = computed(() =>
  isDragging.value ? dragProgress.value : music.progressPercent
)

// Watch for track changes
watch(() => music.currentTrack, (newTrack) => {
  if (newTrack && audioRef.value) {
    audioRef.value.src = music.getAudioUrl(newTrack.id)
    audioRef.value.load()
    if (music.isPlaying) {
      audioRef.value.play().catch(e => {
        console.warn('Track play failed (will retry on gesture):', e)
      })
    }
  }
}, { immediate: true })

// Watch for play/pause changes
watch(() => music.isPlaying, (playing) => {
  if (audioRef.value) {
    if (playing) {
      // Reset position if audio ended (replay scenario)
      if (audioRef.value.ended) {
        audioRef.value.currentTime = 0
      }
      audioRef.value.play().catch(e => {
        console.warn('Playback failed:', e)
        music.pausePlayback()
      })
    } else {
      audioRef.value.pause()
    }
  }
})

// Watch for volume changes
watch(() => music.volume, (vol) => {
  if (audioRef.value) {
    audioRef.value.volume = vol
  }
}, { immediate: true })

// Watch for seek requests
watch(() => music.currentTime, (time) => {
  if (audioRef.value && !isDragging.value) {
    // Only seek if difference is significant (not from timeupdate)
    if (Math.abs(audioRef.value.currentTime - time) > 1) {
      audioRef.value.currentTime = time
    }
  }
})

// Audio event handlers
function onTimeUpdate() {
  if (audioRef.value && !isDragging.value) {
    music.currentTime = audioRef.value.currentTime
  }
}

function onLoadedMetadata() {
  if (audioRef.value) {
    music.duration = audioRef.value.duration
    audioRef.value.volume = music.volume
  }
}

function onEnded() {
  music.playNext()
}

function onError(e) {
  console.error('Audio error:', e)
  // Don't hide the player on error - just pause so user can retry or close
  music.pausePlayback()
}

// Progress bar interaction
function onProgressMouseDown(e) {
  isDragging.value = true
  updateDragProgress(e)
  window.addEventListener('mousemove', onProgressMouseMove)
  window.addEventListener('mouseup', onProgressMouseUp)
}

function onProgressMouseMove(e) {
  if (isDragging.value) {
    updateDragProgress(e)
  }
}

function onProgressMouseUp() {
  if (isDragging.value) {
    music.seekTo(dragProgress.value)
    if (audioRef.value) {
      audioRef.value.currentTime = (dragProgress.value / 100) * music.duration
    }
    isDragging.value = false
  }
  window.removeEventListener('mousemove', onProgressMouseMove)
  window.removeEventListener('mouseup', onProgressMouseUp)
}

function updateDragProgress(e) {
  const bar = e.target.closest('.progress-bar')
  if (bar) {
    const rect = bar.getBoundingClientRect()
    const percent = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100))
    dragProgress.value = percent
  }
}

// Volume slider
function onVolumeChange(e) {
  music.setVolume(parseFloat(e.target.value))
}

// Waveform animation
let waveformInterval = null

// Song ready notification (from Village WebSocket)
const songReadyBanner = ref(null)
let bannerTimeout = null

function onMusicComplete(e) {
  const detail = e.detail || {}
  songReadyBanner.value = {
    title: detail.message || 'Song ready!',
    agent: detail.agent_id,
  }
  // Auto-dismiss after 8 seconds
  if (bannerTimeout) clearTimeout(bannerTimeout)
  bannerTimeout = setTimeout(() => { songReadyBanner.value = null }, 8000)
  // Refresh the library
  music.fetchLibrary()
}

onMounted(() => {
  waveformInterval = setInterval(() => {
    if (music.isPlaying) {
      waveformBars.value = waveformBars.value.map(() =>
        0.2 + Math.random() * 0.8
      )
    }
  }, 150)

  window.addEventListener('music-complete', onMusicComplete)
})

onUnmounted(() => {
  if (waveformInterval) {
    clearInterval(waveformInterval)
  }
  if (bannerTimeout) {
    clearTimeout(bannerTimeout)
  }
  window.removeEventListener('mousemove', onProgressMouseMove)
  window.removeEventListener('mouseup', onProgressMouseUp)
  window.removeEventListener('music-complete', onMusicComplete)
})
</script>

<template>
  <!-- Hidden audio element -->
  <audio
    ref="audioRef"
    @timeupdate="onTimeUpdate"
    @loadedmetadata="onLoadedMetadata"
    @ended="onEnded"
    @error="onError"
  />

  <!-- Song ready notification banner -->
  <Transition name="slide-up">
    <div
      v-if="songReadyBanner"
      class="fixed bottom-20 left-0 right-0 z-50 flex justify-center pointer-events-none"
    >
      <div class="bg-gold/90 text-apex-dark px-6 py-3 rounded-xl shadow-lg flex items-center gap-3 pointer-events-auto">
        <span class="text-lg">🎵</span>
        <span class="font-medium">{{ songReadyBanner.title }}</span>
        <button @click="songReadyBanner = null" class="ml-2 text-apex-dark/60 hover:text-apex-dark text-lg">&times;</button>
      </div>
    </div>
  </Transition>

  <!-- Player UI - only show when track is loaded -->
  <Transition name="slide-up">
    <div
      v-if="music.currentTrack"
      class="fixed bottom-0 left-0 right-0 h-20 bg-apex-dark/95 backdrop-blur-xl border-t border-apex-border z-40"
    >
      <!-- Progress bar (thin line at top) -->
      <div
        class="progress-bar absolute top-0 left-0 right-0 h-1 bg-apex-darker cursor-pointer group"
        @mousedown="onProgressMouseDown"
      >
        <div
          class="h-full bg-gradient-to-r from-gold to-amber-400 transition-all duration-75"
          :style="{ width: `${displayProgress}%` }"
        />
        <!-- Hover dot -->
        <div
          class="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-gold rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
          :style="{ left: `${displayProgress}%`, marginLeft: '-6px' }"
        />
      </div>

      <div class="max-w-7xl mx-auto px-4 h-full flex items-center justify-between gap-4">
        <!-- Track Info -->
        <div class="flex items-center gap-4 min-w-0 flex-1">
          <!-- Album art / Waveform -->
          <div class="w-14 h-14 bg-gradient-to-br from-apex-dark to-apex-card rounded-lg flex items-center justify-center overflow-hidden flex-shrink-0">
            <div v-if="music.isPlaying" class="flex items-end gap-0.5 h-8">
              <div
                v-for="(bar, i) in waveformBars"
                :key="i"
                class="w-1 bg-gold rounded-full transition-all duration-150"
                :style="{ height: `${bar * 100}%` }"
              />
            </div>
            <span v-else class="text-3xl">🎵</span>
          </div>

          <!-- Title & Style -->
          <div class="min-w-0">
            <h3 class="font-medium truncate text-white">
              {{ music.currentTrack.title || 'Untitled' }}
            </h3>
            <p class="text-sm text-gray-400 truncate">
              {{ music.currentTrack.style || music.currentTrack.agent_id || 'AI Generated' }}
            </p>
          </div>

          <!-- Favorite button -->
          <button
            @click="music.toggleFavorite(music.currentTrack.id)"
            class="text-xl transition-transform hover:scale-110 flex-shrink-0"
          >
            {{ music.currentTrack.favorite ? '⭐' : '☆' }}
          </button>
        </div>

        <!-- Playback Controls -->
        <div class="flex items-center gap-4">
          <!-- Previous -->
          <button
            @click="music.playPrevious"
            class="text-gray-400 hover:text-white transition-colors"
            title="Previous"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M8.445 14.832A1 1 0 0010 14v-2.798l5.445 3.63A1 1 0 0017 14V6a1 1 0 00-1.555-.832L10 8.798V6a1 1 0 00-1.555-.832l-6 4a1 1 0 000 1.664l6 4z" />
            </svg>
          </button>

          <!-- Play/Pause -->
          <button
            @click="music.togglePlayback"
            class="w-12 h-12 bg-gold hover:bg-amber-400 rounded-full flex items-center justify-center text-apex-dark transition-all hover:scale-105"
          >
            <svg v-if="music.isPlaying" xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
            </svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 ml-0.5" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clip-rule="evenodd" />
            </svg>
          </button>

          <!-- Next -->
          <button
            @click="music.playNext"
            class="text-gray-400 hover:text-white transition-colors"
            title="Next"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M4.555 5.168A1 1 0 003 6v8a1 1 0 001.555.832L10 11.202V14a1 1 0 001.555.832l6-4a1 1 0 000-1.664l-6-4A1 1 0 0010 6v2.798l-5.445-3.63z" />
            </svg>
          </button>
        </div>

        <!-- Time & Volume -->
        <div class="flex items-center gap-4 flex-1 justify-end">
          <!-- Time display -->
          <span class="text-sm text-gray-400 tabular-nums min-w-[80px] text-right">
            {{ music.formattedCurrentTime }} / {{ music.formattedDuration }}
          </span>

          <!-- Volume -->
          <div class="flex items-center gap-2">
            <button
              @click="music.setVolume(music.volume > 0 ? 0 : 0.8)"
              class="text-gray-400 hover:text-white transition-colors"
            >
              <svg v-if="music.volume === 0" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M9.383 3.076A1 1 0 0110 4v12a1 1 0 01-1.707.707L4.586 13H2a1 1 0 01-1-1V8a1 1 0 011-1h2.586l3.707-3.707a1 1 0 011.09-.217zM12.293 7.293a1 1 0 011.414 0L15 8.586l1.293-1.293a1 1 0 111.414 1.414L16.414 10l1.293 1.293a1 1 0 01-1.414 1.414L15 11.414l-1.293 1.293a1 1 0 01-1.414-1.414L13.586 10l-1.293-1.293a1 1 0 010-1.414z" clip-rule="evenodd" />
              </svg>
              <svg v-else-if="music.volume < 0.5" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M9.383 3.076A1 1 0 0110 4v12a1 1 0 01-1.707.707L4.586 13H2a1 1 0 01-1-1V8a1 1 0 011-1h2.586l3.707-3.707a1 1 0 011.09-.217zM14.657 2.929a1 1 0 011.414 0A9.972 9.972 0 0119 10a9.972 9.972 0 01-2.929 7.071 1 1 0 01-1.414-1.414A7.971 7.971 0 0017 10c0-2.21-.894-4.208-2.343-5.657a1 1 0 010-1.414z" clip-rule="evenodd" />
              </svg>
              <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M9.383 3.076A1 1 0 0110 4v12a1 1 0 01-1.707.707L4.586 13H2a1 1 0 01-1-1V8a1 1 0 011-1h2.586l3.707-3.707a1 1 0 011.09-.217zM14.657 2.929a1 1 0 011.414 0A9.972 9.972 0 0119 10a9.972 9.972 0 01-2.929 7.071 1 1 0 01-1.414-1.414A7.971 7.971 0 0017 10c0-2.21-.894-4.208-2.343-5.657a1 1 0 010-1.414zm-2.829 2.828a1 1 0 011.415 0A5.983 5.983 0 0115 10a5.984 5.984 0 01-1.757 4.243 1 1 0 01-1.415-1.415A3.984 3.984 0 0013 10a3.983 3.983 0 00-1.172-2.828 1 1 0 010-1.415z" clip-rule="evenodd" />
              </svg>
            </button>
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              :value="music.volume"
              @input="onVolumeChange"
              class="w-20 accent-gold"
            />
          </div>

          <!-- Close button -->
          <button
            @click="music.stopPlayback"
            class="text-gray-400 hover:text-white transition-colors ml-2"
            title="Close player"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.slide-up-enter-active,
.slide-up-leave-active {
  transition: transform 0.3s ease, opacity 0.3s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}

/* Custom range slider styling */
input[type="range"] {
  -webkit-appearance: none;
  appearance: none;
  background: transparent;
  cursor: pointer;
}

input[type="range"]::-webkit-slider-track {
  height: 4px;
  background: #374151;
  border-radius: 2px;
}

input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 12px;
  height: 12px;
  background: #d4af37;
  border-radius: 50%;
  margin-top: -4px;
  transition: transform 0.15s;
}

input[type="range"]::-webkit-slider-thumb:hover {
  transform: scale(1.2);
}

input[type="range"]::-moz-range-track {
  height: 4px;
  background: #374151;
  border-radius: 2px;
}

input[type="range"]::-moz-range-thumb {
  width: 12px;
  height: 12px;
  background: #d4af37;
  border-radius: 50%;
  border: none;
}
</style>
