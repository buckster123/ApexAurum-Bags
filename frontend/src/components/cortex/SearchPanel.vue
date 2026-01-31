<script setup>
/**
 * Search Panel - Content Search for Cortex Diver
 *
 * Search inside file contents across the vault.
 * "The All-Seeing Eye finds all"
 */

import { ref, watch } from 'vue'
import api from '@/services/api'
import { useSound } from '@/composables/useSound'

const props = defineProps({
  folderId: {
    type: String,
    default: null,
  },
})

const emit = defineEmits(['close', 'open-file', 'go-to-line'])

const { playTone } = useSound()

// Search state
const query = ref('')
const results = ref([])
const loading = ref(false)
const error = ref(null)
const stats = ref(null)

// Debounce timer
let searchTimeout = null

// Sounds
const searchSounds = {
  search: () => playTone(440, 0.05, 'triangle', 0.1),
  found: () => playTone(659, 0.08, 'sine', 0.12),
  notFound: () => playTone(330, 0.1, 'sine', 0.08),
}

// Perform search
async function performSearch() {
  if (!query.value.trim() || query.value.length < 2) {
    results.value = []
    stats.value = null
    return
  }

  loading.value = true
  error.value = null
  searchSounds.search()

  try {
    const response = await api.get('/api/v1/files/search/content', {
      params: {
        q: query.value,
        folder_id: props.folderId || undefined,
        limit: 20,
        context_lines: 2,
      }
    })

    results.value = response.data.results || []
    stats.value = {
      total: response.data.total_matches,
      filesSearched: response.data.files_searched,
    }

    if (results.value.length > 0) {
      searchSounds.found()
    } else {
      searchSounds.notFound()
    }

  } catch (e) {
    console.error('Search failed:', e)
    error.value = e.response?.data?.detail || 'Search failed'
    results.value = []
    stats.value = null
  } finally {
    loading.value = false
  }
}

// Debounced search
function onQueryChange() {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(performSearch, 300)
}

// Watch query changes
watch(query, onQueryChange)

// Handle clicking on a result
function handleResultClick(result, match) {
  emit('open-file', result.file_id, match.line)
}

// Clear search
function clearSearch() {
  query.value = ''
  results.value = []
  stats.value = null
}

// Highlight matches in content
function highlightMatch(content, query) {
  if (!query) return content
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(`(${escaped})`, 'gi')
  return content.replace(regex, '<mark class="bg-amber-500/40 text-amber-200 px-0.5 rounded">$1</mark>')
}
</script>

<template>
  <div class="flex flex-col h-full bg-apex-darker">
    <!-- Header -->
    <div class="flex items-center gap-2 px-3 py-2 border-b border-apex-border">
      <span class="text-amber-400">🔍</span>
      <span class="text-xs text-amber-400 uppercase tracking-wider font-medium">Search</span>
      <span class="flex-1"></span>
      <button
        @click="emit('close')"
        class="text-gray-500 hover:text-gray-300"
        title="Close search"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Search input -->
    <div class="px-3 py-2 border-b border-apex-border">
      <div class="relative">
        <input
          v-model="query"
          type="text"
          placeholder="Search in files..."
          class="w-full bg-apex-dark border border-apex-border rounded-lg pl-8 pr-8 py-2 text-sm text-white placeholder-gray-500 focus:border-amber-600/50 focus:outline-none"
          @keydown.escape="clearSearch"
        />
        <svg
          class="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <button
          v-if="query"
          @click="clearSearch"
          class="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Stats -->
      <div v-if="stats" class="mt-1 text-xs text-gray-500">
        {{ stats.total }} match{{ stats.total !== 1 ? 'es' : '' }} in {{ results.length }} file{{ results.length !== 1 ? 's' : '' }}
        <span class="text-gray-600">· {{ stats.filesSearched }} searched</span>
      </div>
    </div>

    <!-- Results -->
    <div class="flex-1 overflow-y-auto">
      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-8 text-amber-400">
        <div class="animate-spin mr-2">⟳</div>
        <span class="text-sm">Searching...</span>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="p-4 text-center text-red-400 text-sm">
        {{ error }}
      </div>

      <!-- No results -->
      <div v-else-if="query && !loading && results.length === 0" class="p-4 text-center text-gray-500">
        <p class="text-sm">No matches found</p>
        <p class="text-xs mt-1">Try a different search term</p>
      </div>

      <!-- Empty state -->
      <div v-else-if="!query" class="flex flex-col items-center justify-center h-full text-gray-600">
        <div class="text-3xl mb-2 opacity-30">👁️</div>
        <p class="text-sm">Search file contents</p>
        <p class="text-xs mt-1">The All-Seeing Eye finds all</p>
      </div>

      <!-- Results list -->
      <div v-else class="divide-y divide-apex-border/50">
        <div
          v-for="result in results"
          :key="result.file_id"
          class="p-3"
        >
          <!-- File header -->
          <div class="flex items-center gap-2 mb-2">
            <span class="text-amber-400">📄</span>
            <span class="text-sm font-medium text-gray-200">{{ result.file_name }}</span>
            <span class="text-xs text-gray-500">{{ result.match_count }} match{{ result.match_count !== 1 ? 'es' : '' }}</span>
          </div>

          <!-- Matches -->
          <div class="space-y-1.5">
            <button
              v-for="match in result.matches"
              :key="match.line"
              @click="handleResultClick(result, match)"
              class="w-full text-left group"
            >
              <div class="flex items-start gap-2 px-2 py-1.5 rounded bg-apex-dark/50 hover:bg-amber-900/20 border border-transparent hover:border-amber-600/30 transition-colors">
                <span class="text-xs text-gray-500 font-mono w-8 text-right flex-shrink-0 pt-0.5">
                  {{ match.line }}
                </span>
                <div class="flex-1 font-mono text-xs overflow-hidden">
                  <!-- Context before -->
                  <div v-if="match.context_before" class="text-gray-600 truncate">
                    {{ match.context_before.split('\n').slice(-1)[0] }}
                  </div>
                  <!-- Match line -->
                  <div
                    class="text-gray-300 group-hover:text-white"
                    v-html="highlightMatch(match.content, query)"
                  ></div>
                  <!-- Context after -->
                  <div v-if="match.context_after" class="text-gray-600 truncate">
                    {{ match.context_after.split('\n')[0] }}
                  </div>
                </div>
              </div>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
