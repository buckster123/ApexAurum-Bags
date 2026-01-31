<script setup>
/**
 * The Vault - File Browser View
 *
 * User file management with hierarchical folders, upload/download,
 * grid/list views, and storage tracking.
 *
 * In dev mode, transforms into Cortex Diver - a full IDE experience.
 */

import { ref, computed, onMounted, watch, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useFilesStore } from '@/stores/files'
import { useSound } from '@/composables/useSound'
import { useDevMode } from '@/composables/useDevMode'
import CortexDiver from '@/components/cortex/CortexDiver.vue'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const router = useRouter()
const store = useFilesStore()
const { showToast } = useToast()
const { sounds, playTone } = useSound()
const { devMode } = useDevMode()

// Cortex Diver mode (activated in dev mode)
const cortexMode = ref(false)

// Alchemical sounds for The Vault
const vaultSounds = {
  upload: () => playTone(523, 0.15, 'sine', 0.2),      // Crystallization
  folderOpen: () => playTone(392, 0.1, 'triangle', 0.15), // Unsealing
  delete: () => playTone(220, 0.2, 'sawtooth', 0.1),   // Dissolution
  success: () => sounds.success(),
}

// Local state
const showNewFolderModal = ref(false)
const newFolderName = ref('')
const showDeleteConfirm = ref(false)
const deleteTarget = ref(null)
const showRenameModal = ref(false)
const renameTarget = ref(null)
const renameValue = ref('')
const dragOver = ref(false)
const previewData = ref(null)
const showPreview = ref(false)
const searchInput = ref(null)  // Template ref for search input

// ═══════════════════════════════════════════════════════════════════════════════
// LIFECYCLE
// ═══════════════════════════════════════════════════════════════════════════════

onMounted(async () => {
  const folderId = route.params.folderId || null
  await store.fetchDirectory(folderId)

  // Add keyboard shortcuts
  window.addEventListener('keydown', handleKeyboard)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyboard)
})

watch(() => route.params.folderId, async (newId) => {
  await store.fetchDirectory(newId || null)
  // Play unsealing sound when entering a folder
  if (newId) {
    vaultSounds.folderOpen()
  }
})

// ═══════════════════════════════════════════════════════════════════════════════
// KEYBOARD SHORTCUTS
// ═══════════════════════════════════════════════════════════════════════════════

function handleKeyboard(event) {
  // Don't trigger shortcuts when typing in inputs
  const target = event.target
  if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
    // Allow Escape to close modals even in inputs
    if (event.key === 'Escape') {
      closeAllModals()
    }
    return
  }

  // Don't trigger if any modal is open (except Escape)
  const modalOpen = showNewFolderModal.value || showDeleteConfirm.value ||
                    showRenameModal.value || showPreview.value
  if (modalOpen && event.key !== 'Escape') return

  switch (event.key.toLowerCase()) {
    case 'n':
      // N - New folder (Conjure Chamber)
      event.preventDefault()
      showNewFolderModal.value = true
      break

    case 'u':
      // U - Upload
      event.preventDefault()
      triggerUpload()
      break

    case 'delete':
    case 'backspace':
      // Delete - Delete selected or last clicked
      if (store.isSelecting) {
        event.preventDefault()
        confirmDeleteSelected()
      }
      break

    case 'f':
      // F - Toggle favorite on selected file
      if (store.selectedIds.size === 1) {
        event.preventDefault()
        const id = Array.from(store.selectedIds)[0]
        const file = store.files.find(f => f.id === id)
        if (file) {
          store.toggleFavorite(id)
          vaultSounds.success()
        }
      }
      break

    case '/':
      // / - Focus search
      event.preventDefault()
      searchInput.value?.focus()
      break

    case 'escape':
      // Escape - Close modals, clear selection
      closeAllModals()
      store.clearSelection()
      break

    case 'a':
      // Ctrl+A - Select all
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault()
        store.selectAll()
      }
      break

    case 'g':
      // G - Grid view
      event.preventDefault()
      store.setViewMode('grid')
      break

    case 'l':
      // L - List view
      event.preventDefault()
      store.setViewMode('list')
      break
  }
}

function closeAllModals() {
  showNewFolderModal.value = false
  showDeleteConfirm.value = false
  showRenameModal.value = false
  showPreview.value = false
  previewData.value = null
}

function confirmDeleteSelected() {
  // Get first selected item for the confirmation modal
  const id = Array.from(store.selectedIds)[0]
  const file = store.files.find(f => f.id === id)
  const folder = store.folders.find(f => f.id === id)
  if (file || folder) {
    deleteTarget.value = {
      item: file || folder,
      isFolder: !!folder,
      isMultiple: store.selectedIds.size > 1,
      count: store.selectedIds.size
    }
    showDeleteConfirm.value = true
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════════════════════════

function navigateToFolder(folderId) {
  if (folderId) {
    router.push({ name: 'folder', params: { folderId } })
  } else {
    router.push({ name: 'files' })
  }
}

function handleItemClick(event, item, isFolder) {
  // Ctrl/Cmd+click or Shift+click for selection
  if (event.ctrlKey || event.metaKey || event.shiftKey) {
    event.preventDefault()
    store.toggleSelect(item.id)
    return
  }

  // Normal click - navigate or preview
  if (isFolder) {
    navigateToFolder(item.id)
  } else {
    openPreview(item)
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// FOLDER ACTIONS
// ═══════════════════════════════════════════════════════════════════════════════

async function createFolder() {
  if (!newFolderName.value.trim()) return
  try {
    await store.createFolder(newFolderName.value.trim())
    // Play folder open sound (chamber conjured)
    vaultSounds.folderOpen()
    showNewFolderModal.value = false
    newFolderName.value = ''
  } catch (e) {
    showToast('Failed to create folder. Please try again.')
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// FILE ACTIONS
// ═══════════════════════════════════════════════════════════════════════════════

function triggerUpload() {
  document.getElementById('file-upload-input').click()
}

async function handleFileUpload(event) {
  const files = event.target.files
  if (files.length > 0) {
    const results = await store.uploadFiles(Array.from(files))
    // Play crystallization sound on successful upload
    if (results.length > 0) {
      vaultSounds.upload()
    }
  }
  event.target.value = ''  // Reset input
}

// Drag and drop
function handleDragOver(event) {
  event.preventDefault()
  dragOver.value = true
}

function handleDragLeave() {
  dragOver.value = false
}

async function handleDrop(event) {
  event.preventDefault()
  dragOver.value = false
  const files = event.dataTransfer.files
  if (files.length > 0) {
    const results = await store.uploadFiles(Array.from(files))
    // Play crystallization sound on successful upload
    if (results.length > 0) {
      vaultSounds.upload()
    }
  }
}

async function openPreview(file) {
  try {
    previewData.value = await store.previewFile(file.id)
    previewData.value.file = file
    showPreview.value = true
  } catch (e) {
    // If preview fails, just download
    await store.downloadFile(file.id)
  }
}

function closePreview() {
  showPreview.value = false
  previewData.value = null
}

async function downloadPreviewFile() {
  if (previewData.value?.file) {
    await store.downloadFile(previewData.value.file.id)
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// RENAME / DELETE
// ═══════════════════════════════════════════════════════════════════════════════

function openRename(item, isFolder) {
  renameTarget.value = { item, isFolder }
  renameValue.value = item.name
  showRenameModal.value = true
}

async function submitRename() {
  if (!renameValue.value.trim()) return
  try {
    if (renameTarget.value.isFolder) {
      await store.renameFolder(renameTarget.value.item.id, renameValue.value.trim())
    } else {
      await store.renameFile(renameTarget.value.item.id, renameValue.value.trim())
    }
    showRenameModal.value = false
  } catch (e) {
    showToast('Failed to rename. Please try again.')
  }
}

function openDelete(item, isFolder) {
  deleteTarget.value = { item, isFolder }
  showDeleteConfirm.value = true
}

async function confirmDelete() {
  try {
    // Handle bulk delete
    if (deleteTarget.value.isMultiple) {
      await store.deleteSelected()
    } else if (deleteTarget.value.isFolder) {
      await store.deleteFolder(deleteTarget.value.item.id)
    } else {
      await store.deleteFile(deleteTarget.value.item.id)
    }
    // Play dissolution sound
    vaultSounds.delete()
    showDeleteConfirm.value = false
  } catch (e) {
    showToast('Failed to delete. Please try again.')
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONTEXT MENU
// ═══════════════════════════════════════════════════════════════════════════════

const contextMenu = ref({ show: false, x: 0, y: 0, item: null, isFolder: false })

function showContextMenu(event, item, isFolder) {
  event.preventDefault()
  contextMenu.value = {
    show: true,
    x: event.clientX,
    y: event.clientY,
    item,
    isFolder,
  }
}

function hideContextMenu() {
  contextMenu.value.show = false
}

function contextAction(action) {
  const { item, isFolder } = contextMenu.value
  hideContextMenu()

  switch (action) {
    case 'open':
      handleItemClick(item, isFolder)
      break
    case 'download':
      store.downloadFile(item.id)
      break
    case 'rename':
      openRename(item, isFolder)
      break
    case 'delete':
      openDelete(item, isFolder)
      break
    case 'favorite':
      store.toggleFavorite(item.id)
      break
  }
}

// Close context menu on click outside
function handleGlobalClick() {
  if (contextMenu.value.show) {
    hideContextMenu()
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════════════════

function formatDate(dateStr) {
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function enterCortexMode() {
  cortexMode.value = true
  // Play activation sound
  playTone(659, 0.1, 'sine', 0.2)
  setTimeout(() => playTone(880, 0.15, 'sine', 0.2), 100)
}

function exitCortexMode() {
  cortexMode.value = false
}
</script>

<template>
  <!-- Cortex Diver Mode (Dev Mode IDE) -->
  <CortexDiver
    v-if="cortexMode && devMode"
    :folder-id="route.params.folderId"
    @exit-cortex="exitCortexMode"
  />

  <!-- Standard Vault View -->
  <div
    v-else
    class="min-h-screen bg-apex-dark pt-16"
    @click="handleGlobalClick"
    @dragover="handleDragOver"
    @dragleave="handleDragLeave"
    @drop="handleDrop"
  >
    <!-- Drag overlay - Transmutation Portal -->
    <div
      v-if="dragOver"
      class="fixed inset-0 bg-amber-500/10 border-4 border-dashed border-amber-500 z-50 flex flex-col items-center justify-center pointer-events-none"
    >
      <div class="text-4xl mb-2">⚗️</div>
      <div class="text-xl text-amber-400 font-bold">Release to transmit</div>
    </div>

    <div class="max-w-7xl mx-auto px-4 py-6">
      <!-- Header -->
      <div class="flex items-center justify-between mb-6">
        <div>
          <h1 class="text-2xl font-bold text-white flex items-center gap-2">
            <span class="text-gold">The Vault</span>
            <span class="text-lg opacity-50">⚗️</span>
            <!-- Cortex Diver toggle (dev mode only) -->
            <button
              v-if="devMode"
              @click="enterCortexMode"
              class="ml-4 px-3 py-1 text-xs bg-gradient-to-r from-amber-900/50 to-purple-900/50 border border-amber-600/30 rounded-full text-amber-300 hover:text-amber-100 hover:border-amber-500/50 transition-all"
              title="Enter Cortex Diver IDE"
            >
              <span class="mr-1">🧠</span>
              CORTEX DIVER
            </button>
          </h1>
          <p class="text-gray-400 text-sm mt-1">Your alchemical sanctum</p>
        </div>

        <!-- Essence Capacity -->
        <div class="text-right">
          <div class="text-sm text-amber-400/80">
            Essence: {{ store.formattedStorageUsed }} of {{ store.formattedStorageQuota }}
          </div>
          <div class="text-xs text-gray-500 mt-0.5">{{ store.essenceStatus }}</div>
          <div class="w-32 h-2 bg-apex-darker rounded-full mt-1 overflow-hidden">
            <div
              class="h-full transition-all duration-300 bg-gradient-to-r from-amber-600 to-gold"
              :style="{ width: `${store.storagePercent}%` }"
            ></div>
          </div>
          <!-- Keyboard hint -->
          <div class="text-xs text-gray-600 mt-1 hidden lg:block">
            <kbd class="px-1 py-0.5 bg-apex-darker rounded text-xs">N</kbd> new
            <kbd class="px-1 py-0.5 bg-apex-darker rounded text-xs ml-1">U</kbd> upload
            <kbd class="px-1 py-0.5 bg-apex-darker rounded text-xs ml-1">/</kbd> search
          </div>
        </div>
      </div>

      <!-- Toolbar -->
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <!-- Upload button -->
        <button
          @click="triggerUpload"
          class="btn-primary flex items-center gap-2"
          :disabled="store.uploading"
          title="Upload Files (U)"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
          <span class="hidden sm:inline">Upload</span>
        </button>
        <input
          id="file-upload-input"
          type="file"
          multiple
          class="hidden"
          @change="handleFileUpload"
        />

        <!-- New folder button -->
        <button
          @click="showNewFolderModal = true"
          class="btn-ghost flex items-center gap-2"
          title="New Folder (N)"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 13h6m-3-3v6m-9 1V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
          </svg>
          <span class="hidden sm:inline">New Folder</span>
        </button>

        <!-- Search bar -->
        <div class="relative flex-1 max-w-xs">
          <input
            ref="searchInput"
            type="text"
            :value="store.searchQuery"
            @input="store.setSearchQuery($event.target.value)"
            placeholder="Search artifacts... (/)"
            class="w-full bg-apex-darker border border-apex-border rounded-lg pl-9 pr-3 py-2 text-sm text-gray-300 placeholder-gray-500 focus:border-amber-600/50 focus:outline-none"
          />
          <svg class="w-4 h-4 text-gray-500 absolute left-3 top-1/2 -translate-y-1/2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>

        <div class="hidden sm:block flex-1"></div>

        <!-- View mode toggle -->
        <div class="flex items-center bg-apex-darker rounded-lg p-1">
          <button
            @click="store.setViewMode('grid')"
            class="p-2 rounded transition-colors"
            :class="store.viewMode === 'grid' ? 'bg-apex-border text-gold' : 'text-gray-400 hover:text-white'"
          >
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zM11 13a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
            </svg>
          </button>
          <button
            @click="store.setViewMode('list')"
            class="p-2 rounded transition-colors"
            :class="store.viewMode === 'list' ? 'bg-apex-border text-gold' : 'text-gray-400 hover:text-white'"
          >
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M3 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clip-rule="evenodd" />
            </svg>
          </button>
        </div>

        <!-- Sort dropdown -->
        <select
          :value="store.sortBy"
          @change="store.setSortBy($event.target.value)"
          class="bg-apex-darker border border-apex-border rounded-lg px-3 py-2 text-sm text-gray-300"
        >
          <option value="name">Name</option>
          <option value="date">Date</option>
          <option value="size">Size</option>
          <option value="type">Type</option>
        </select>
      </div>

      <!-- Selection toolbar -->
      <div
        v-if="store.isSelecting"
        class="flex items-center gap-3 mb-4 p-3 bg-amber-900/20 border border-amber-600/30 rounded-lg"
      >
        <span class="text-amber-200 text-sm font-medium">
          {{ store.selectedIds.size }} {{ store.selectedIds.size === 1 ? 'item' : 'items' }} selected
        </span>
        <div class="flex-1"></div>
        <button
          @click="confirmDeleteSelected"
          class="text-red-400 hover:text-red-300 text-sm flex items-center gap-1"
          title="Delete selected (Delete)"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
          Dissolve
        </button>
        <button
          @click="store.clearSelection"
          class="text-gray-400 hover:text-white text-sm"
          title="Clear selection (Esc)"
        >
          Clear
        </button>
      </div>

      <!-- Breadcrumb -->
      <div class="flex items-center gap-2 text-sm mb-4 overflow-x-auto pb-2">
        <button
          @click="navigateToFolder(null)"
          class="text-gold hover:underline flex items-center gap-1 whitespace-nowrap"
        >
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z" />
          </svg>
          Home
        </button>
        <template v-for="(item, index) in store.folderPath" :key="item.id">
          <span class="text-amber-600/60 mx-1">∴</span>
          <button
            @click="navigateToFolder(item.id)"
            class="text-gray-300 hover:text-gold hover:underline whitespace-nowrap"
            :class="{ 'text-white font-medium': index === store.folderPath.length - 1 }"
          >
            {{ item.name }}
          </button>
        </template>
      </div>

      <!-- Loading state -->
      <div v-if="store.loading" class="flex items-center justify-center py-20">
        <div class="animate-spin rounded-full h-8 w-8 border-2 border-gold border-t-transparent"></div>
      </div>

      <!-- Error state -->
      <div v-else-if="store.error" class="text-center py-20">
        <p class="text-red-400">{{ store.error }}</p>
        <button @click="store.fetchDirectory(route.params.folderId)" class="btn-ghost mt-4">
          Retry
        </button>
      </div>

      <!-- Empty state - Alchemical -->
      <div
        v-else-if="store.sortedFolders.length === 0 && store.sortedFiles.length === 0"
        class="text-center py-20"
      >
        <div class="text-5xl mb-2 opacity-60">⚗️</div>
        <div class="text-amber-600/40 text-sm mb-4 font-mono">∴ &nbsp; &nbsp; ∴</div>
        <p class="text-gray-400 text-lg">The chamber awaits</p>
        <p class="text-gray-500 text-sm mt-2">Transmit artifacts or conjure a new chamber</p>
      </div>

      <!-- Grid View -->
      <div v-else-if="store.viewMode === 'grid'" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
        <!-- Folders -->
        <div
          v-for="folder in store.sortedFolders"
          :key="folder.id"
          @click="handleItemClick($event, folder, true)"
          @contextmenu="showContextMenu($event, folder, true)"
          class="bg-apex-darker rounded-lg p-4 cursor-pointer hover:bg-apex-border transition-colors group relative"
          :class="{ 'ring-2 ring-amber-500/50 bg-amber-900/10': store.selectedIds.has(folder.id) }"
        >
          <!-- Selection indicator -->
          <div
            v-if="store.selectedIds.has(folder.id)"
            class="absolute top-2 left-2 w-5 h-5 bg-amber-500 rounded-full flex items-center justify-center"
          >
            <svg class="w-3 h-3 text-black" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
            </svg>
          </div>
          <div class="text-4xl mb-2 text-center">📁</div>
          <p class="text-sm text-white truncate text-center">{{ folder.name }}</p>
          <p class="text-xs text-gray-500 text-center mt-1">
            {{ folder.folder_count }} folders, {{ folder.file_count }} files
          </p>
        </div>

        <!-- Files -->
        <div
          v-for="file in store.sortedFiles"
          :key="file.id"
          @click="handleItemClick($event, file, false)"
          @contextmenu="showContextMenu($event, file, false)"
          class="bg-apex-darker rounded-lg p-4 cursor-pointer hover:bg-apex-border transition-colors group relative"
          :class="{ 'ring-2 ring-amber-500/50 bg-amber-900/10': store.selectedIds.has(file.id) }"
        >
          <!-- Selection indicator -->
          <div
            v-if="store.selectedIds.has(file.id)"
            class="absolute top-2 left-2 w-5 h-5 bg-amber-500 rounded-full flex items-center justify-center"
          >
            <svg class="w-3 h-3 text-black" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
            </svg>
          </div>
          <!-- Favorite indicator -->
          <div v-if="file.favorite" class="absolute top-2 right-2 text-gold">
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
            </svg>
          </div>
          <div class="text-4xl mb-2 text-center">{{ store.getFileIcon(file.file_type) }}</div>
          <p class="text-sm text-white truncate text-center">{{ file.name }}</p>
          <p class="text-xs text-gray-500 text-center mt-1">{{ store.formatBytes(file.size_bytes) }}</p>
        </div>
      </div>

      <!-- List View -->
      <div v-else class="bg-apex-darker rounded-lg overflow-hidden">
        <table class="w-full">
          <thead>
            <tr class="border-b border-apex-border text-left text-sm text-gray-400">
              <th class="px-4 py-3 font-medium">Name</th>
              <th class="px-4 py-3 font-medium hidden sm:table-cell">Type</th>
              <th class="px-4 py-3 font-medium hidden md:table-cell">Size</th>
              <th class="px-4 py-3 font-medium hidden lg:table-cell">Modified</th>
              <th class="px-4 py-3 font-medium w-10"></th>
            </tr>
          </thead>
          <tbody>
            <!-- Folders -->
            <tr
              v-for="folder in store.sortedFolders"
              :key="folder.id"
              @click="handleItemClick($event, folder, true)"
              @contextmenu="showContextMenu($event, folder, true)"
              class="border-b border-apex-border/50 hover:bg-apex-border/50 cursor-pointer transition-colors group"
              :class="{ 'bg-amber-900/10': store.selectedIds.has(folder.id) }"
            >
              <td class="px-4 py-3">
                <div class="flex items-center gap-3">
                  <!-- Selection checkbox -->
                  <div
                    @click.stop="store.toggleSelect(folder.id)"
                    class="w-5 h-5 rounded border flex items-center justify-center cursor-pointer transition-colors"
                    :class="store.selectedIds.has(folder.id)
                      ? 'bg-amber-500 border-amber-500'
                      : 'border-gray-600 hover:border-amber-500/50 opacity-0 group-hover:opacity-100'"
                  >
                    <svg v-if="store.selectedIds.has(folder.id)" class="w-3 h-3 text-black" fill="currentColor" viewBox="0 0 20 20">
                      <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                    </svg>
                  </div>
                  <span class="text-xl">📁</span>
                  <span class="text-white">{{ folder.name }}</span>
                </div>
              </td>
              <td class="px-4 py-3 text-gray-400 hidden sm:table-cell">Folder</td>
              <td class="px-4 py-3 text-gray-400 hidden md:table-cell">--</td>
              <td class="px-4 py-3 text-gray-400 hidden lg:table-cell">{{ formatDate(folder.updated_at) }}</td>
              <td class="px-4 py-3 text-center">
                <button
                  @click.stop="showContextMenu($event, folder, true)"
                  class="text-gray-400 hover:text-white p-1"
                >
                  <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
                  </svg>
                </button>
              </td>
            </tr>

            <!-- Files -->
            <tr
              v-for="file in store.sortedFiles"
              :key="file.id"
              @click="handleItemClick($event, file, false)"
              @contextmenu="showContextMenu($event, file, false)"
              class="border-b border-apex-border/50 hover:bg-apex-border/50 cursor-pointer transition-colors group"
              :class="{ 'bg-amber-900/10': store.selectedIds.has(file.id) }"
            >
              <td class="px-4 py-3">
                <div class="flex items-center gap-3">
                  <!-- Selection checkbox -->
                  <div
                    @click.stop="store.toggleSelect(file.id)"
                    class="w-5 h-5 rounded border flex items-center justify-center cursor-pointer transition-colors"
                    :class="store.selectedIds.has(file.id)
                      ? 'bg-amber-500 border-amber-500'
                      : 'border-gray-600 hover:border-amber-500/50 opacity-0 group-hover:opacity-100'"
                  >
                    <svg v-if="store.selectedIds.has(file.id)" class="w-3 h-3 text-black" fill="currentColor" viewBox="0 0 20 20">
                      <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                    </svg>
                  </div>
                  <span class="text-xl">{{ store.getFileIcon(file.file_type) }}</span>
                  <span class="text-white">{{ file.name }}</span>
                  <span v-if="file.favorite" class="text-gold">
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                    </svg>
                  </span>
                </div>
              </td>
              <td class="px-4 py-3 text-gray-400 capitalize hidden sm:table-cell">{{ file.file_type }}</td>
              <td class="px-4 py-3 text-gray-400 hidden md:table-cell">{{ store.formatBytes(file.size_bytes) }}</td>
              <td class="px-4 py-3 text-gray-400 hidden lg:table-cell">{{ formatDate(file.updated_at) }}</td>
              <td class="px-4 py-3 text-center">
                <button
                  @click.stop="showContextMenu($event, file, false)"
                  class="text-gray-400 hover:text-white p-1"
                >
                  <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
                  </svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Upload progress -->
      <div v-if="Object.keys(store.uploadProgress).length > 0" class="fixed bottom-4 right-4 bg-apex-dark border border-apex-border rounded-lg shadow-xl p-4 w-80">
        <h3 class="text-sm font-medium text-white mb-3">Uploading</h3>
        <div v-for="(upload, id) in store.uploadProgress" :key="id" class="mb-2">
          <div class="flex items-center justify-between text-sm">
            <span class="text-gray-300 truncate flex-1">{{ upload.name }}</span>
            <span class="text-gray-400 ml-2">
              {{ upload.status === 'complete' ? 'Done' : upload.status === 'error' ? 'Failed' : `${upload.progress}%` }}
            </span>
          </div>
          <div class="w-full h-1 bg-apex-darker rounded-full mt-1 overflow-hidden">
            <div
              class="h-full transition-all duration-300"
              :class="{
                'bg-gold': upload.status === 'uploading',
                'bg-green-500': upload.status === 'complete',
                'bg-red-500': upload.status === 'error',
              }"
              :style="{ width: `${upload.progress}%` }"
            ></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Context Menu - Alchemical Actions -->
    <div
      v-if="contextMenu.show"
      class="fixed bg-apex-dark border border-amber-900/30 rounded-lg shadow-xl py-2 z-50"
      :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
    >
      <button
        @click="contextAction('open')"
        class="w-full px-4 py-2 text-left text-sm text-gray-300 hover:bg-amber-900/20 hover:text-amber-200"
      >
        {{ contextMenu.isFolder ? '⊛ Enter Chamber' : '◉ Examine' }}
      </button>
      <button
        v-if="!contextMenu.isFolder"
        @click="contextAction('download')"
        class="w-full px-4 py-2 text-left text-sm text-gray-300 hover:bg-amber-900/20 hover:text-amber-200"
      >
        ↓ Distill
      </button>
      <button
        v-if="!contextMenu.isFolder"
        @click="contextAction('favorite')"
        class="w-full px-4 py-2 text-left text-sm text-gray-300 hover:bg-amber-900/20 hover:text-amber-200"
      >
        {{ contextMenu.item?.favorite ? '☆ Unstar Artifact' : '★ Star Artifact' }}
      </button>
      <hr class="my-2 border-amber-900/30" />
      <button
        @click="contextAction('rename')"
        class="w-full px-4 py-2 text-left text-sm text-gray-300 hover:bg-amber-900/20 hover:text-amber-200"
      >
        ∿ Transmute
      </button>
      <button
        @click="contextAction('delete')"
        class="w-full px-4 py-2 text-left text-sm text-red-400 hover:bg-red-900/20 hover:text-red-300"
      >
        ⊗ Dissolve
      </button>
    </div>

    <!-- New Folder Modal -->
    <Teleport to="body">
      <div v-if="showNewFolderModal" class="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
        <div class="bg-apex-dark border border-apex-border rounded-lg p-6 w-full max-w-md">
          <h2 class="text-lg font-bold text-amber-200 mb-4">⊛ Conjure Chamber</h2>
          <input
            v-model="newFolderName"
            type="text"
            placeholder="Chamber name"
            class="w-full bg-apex-darker border border-apex-border rounded-lg px-4 py-2 text-white mb-4"
            @keyup.enter="createFolder"
            autofocus
          />
          <div class="flex justify-end gap-3">
            <button @click="showNewFolderModal = false" class="btn-ghost">Cancel</button>
            <button @click="createFolder" class="btn-primary">Create</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Rename Modal -->
    <Teleport to="body">
      <div v-if="showRenameModal" class="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
        <div class="bg-apex-dark border border-apex-border rounded-lg p-6 w-full max-w-md">
          <h2 class="text-lg font-bold text-white mb-4">Rename</h2>
          <input
            v-model="renameValue"
            type="text"
            class="w-full bg-apex-darker border border-apex-border rounded-lg px-4 py-2 text-white mb-4"
            @keyup.enter="submitRename"
            autofocus
          />
          <div class="flex justify-end gap-3">
            <button @click="showRenameModal = false" class="btn-ghost">Cancel</button>
            <button @click="submitRename" class="btn-primary">Rename</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Delete Confirmation Modal -->
    <Teleport to="body">
      <div v-if="showDeleteConfirm" class="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
        <div class="bg-apex-dark border border-apex-border rounded-lg p-6 w-full max-w-md">
          <h2 class="text-lg font-bold text-red-400 mb-4">
            ⊗ Dissolve {{ deleteTarget?.isMultiple ? `${deleteTarget.count} Items` : (deleteTarget?.isFolder ? 'Chamber' : 'Artifact') }}
          </h2>
          <p class="text-gray-300 mb-4">
            <template v-if="deleteTarget?.isMultiple">
              Dissolve <span class="text-white font-medium">{{ deleteTarget.count }} items</span> into the void?
            </template>
            <template v-else>
              Dissolve <span class="text-white font-medium">{{ deleteTarget?.item?.name }}</span> into the void?
            </template>
            <span v-if="deleteTarget?.isFolder || deleteTarget?.isMultiple" class="text-red-400 block mt-1">
              All contents will be lost to the aether.
            </span>
          </p>
          <div class="flex justify-end gap-3">
            <button @click="showDeleteConfirm = false" class="btn-ghost">Preserve</button>
            <button @click="confirmDelete" class="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg">Dissolve</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Preview Modal -->
    <Teleport to="body">
      <div v-if="showPreview" class="fixed inset-0 bg-black/80 z-50 flex flex-col">
        <!-- Header -->
        <div class="flex items-center justify-between p-4 border-b border-apex-border">
          <div class="flex items-center gap-3">
            <span class="text-2xl">{{ store.getFileIcon(previewData?.file?.file_type) }}</span>
            <span class="text-white font-medium">{{ previewData?.file?.name }}</span>
          </div>
          <div class="flex items-center gap-2">
            <button @click="downloadPreviewFile" class="btn-ghost">
              Download
            </button>
            <button @click="closePreview" class="text-gray-400 hover:text-white p-2">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <!-- Content -->
        <div class="flex-1 overflow-auto p-4">
          <!-- Image preview -->
          <div v-if="previewData?.file?.file_type === 'image'" class="flex items-center justify-center h-full">
            <img
              :src="`/api/v1/files/${previewData.file.id}/preview`"
              :alt="previewData.file.name"
              class="max-w-full max-h-full object-contain"
            />
          </div>

          <!-- Text/code preview -->
          <div v-else-if="previewData?.content" class="bg-apex-darker rounded-lg p-4 h-full overflow-auto">
            <pre class="text-sm text-gray-300 whitespace-pre-wrap font-mono">{{ previewData.content }}</pre>
            <p v-if="previewData.truncated" class="text-yellow-400 text-sm mt-4">
              (Showing first {{ previewData.lines_shown }} lines)
            </p>
          </div>

          <!-- No preview -->
          <div v-else class="flex flex-col items-center justify-center h-full text-gray-400">
            <div class="text-6xl mb-4">{{ store.getFileIcon(previewData?.file?.file_type) }}</div>
            <p>Preview not available for this file type</p>
            <button @click="downloadPreviewFile" class="btn-primary mt-4">Download File</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
