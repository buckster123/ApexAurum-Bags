/**
 * The Vault - Files Store
 *
 * Manages user file storage with folders, upload/download, and quota tracking.
 * "Every alchemist needs a sanctum"
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

export const useFilesStore = defineStore('files', () => {
  // ═══════════════════════════════════════════════════════════════════════════════
  // STATE
  // ═══════════════════════════════════════════════════════════════════════════════

  // Directory state
  const currentFolder = ref(null)    // null = root
  const folderPath = ref([])         // Breadcrumb trail
  const folders = ref([])
  const files = ref([])

  // Selection state
  const selectedIds = ref(new Set())
  const clipboard = ref({ items: [], mode: null })  // mode: 'copy' | 'cut'

  // View state
  const viewMode = ref(localStorage.getItem('vault_view') || 'grid')  // 'grid' | 'list'
  const sortBy = ref(localStorage.getItem('vault_sort') || 'name')    // 'name', 'date', 'size', 'type'
  const sortAsc = ref(localStorage.getItem('vault_sort_asc') !== 'false')
  const searchQuery = ref('')
  const filterType = ref(null)  // null, 'document', 'image', 'code', 'data', 'archive'

  // Upload state
  const uploading = ref(false)
  const uploadProgress = ref({})  // { tempId: { name, progress, status } }

  // Storage stats
  const storageUsed = ref(0)
  const storageQuota = ref(5 * 1024 * 1024 * 1024)  // 5GB default

  // Loading state
  const loading = ref(false)
  const error = ref(null)

  // ═══════════════════════════════════════════════════════════════════════════════
  // COMPUTED
  // ═══════════════════════════════════════════════════════════════════════════════

  const sortedFolders = computed(() => {
    const sorted = [...folders.value]
    sorted.sort((a, b) => {
      if (sortBy.value === 'name') {
        return sortAsc.value
          ? a.name.localeCompare(b.name)
          : b.name.localeCompare(a.name)
      }
      if (sortBy.value === 'date') {
        return sortAsc.value
          ? new Date(a.updated_at) - new Date(b.updated_at)
          : new Date(b.updated_at) - new Date(a.updated_at)
      }
      return 0
    })
    return sorted
  })

  const sortedFiles = computed(() => {
    let filtered = [...files.value]

    // Apply search filter
    if (searchQuery.value) {
      const query = searchQuery.value.toLowerCase()
      filtered = filtered.filter(f =>
        f.name.toLowerCase().includes(query) ||
        (f.description || '').toLowerCase().includes(query)
      )
    }

    // Apply type filter
    if (filterType.value) {
      filtered = filtered.filter(f => f.file_type === filterType.value)
    }

    // Sort
    filtered.sort((a, b) => {
      if (sortBy.value === 'name') {
        return sortAsc.value
          ? a.name.localeCompare(b.name)
          : b.name.localeCompare(a.name)
      }
      if (sortBy.value === 'date') {
        return sortAsc.value
          ? new Date(a.updated_at) - new Date(b.updated_at)
          : new Date(b.updated_at) - new Date(a.updated_at)
      }
      if (sortBy.value === 'size') {
        return sortAsc.value
          ? a.size_bytes - b.size_bytes
          : b.size_bytes - a.size_bytes
      }
      if (sortBy.value === 'type') {
        return sortAsc.value
          ? a.file_type.localeCompare(b.file_type)
          : b.file_type.localeCompare(a.file_type)
      }
      return 0
    })

    return filtered
  })

  const isSelecting = computed(() => selectedIds.value.size > 0)

  const storagePercent = computed(() =>
    Math.min(100, (storageUsed.value / storageQuota.value) * 100)
  )

  const storageColor = computed(() => {
    if (storagePercent.value >= 90) return 'bg-red-500'
    if (storagePercent.value >= 75) return 'bg-yellow-500'
    return 'bg-green-500'
  })

  const formattedStorageUsed = computed(() => formatBytes(storageUsed.value))
  const formattedStorageQuota = computed(() => formatBytes(storageQuota.value))

  // ═══════════════════════════════════════════════════════════════════════════════
  // HELPERS
  // ═══════════════════════════════════════════════════════════════════════════════

  function formatBytes(bytes) {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }

  function getFileIcon(fileType) {
    // Alchemical icons for The Vault
    const icons = {
      document: '📜',  // Sealed scroll - written wisdom
      code: '⚗️',      // Alchemical formula - transmutation recipes
      image: '🪞',     // Scrying mirror - captured reflections
      data: '💎',      // Faceted stone - crystallized knowledge
      archive: '🗃️',   // Sealed chest - compressed essence
      other: '✧',      // Mystical artifact
    }
    return icons[fileType] || icons.other
  }

  // Essence capacity status message
  const essenceStatus = computed(() => {
    if (storagePercent.value >= 90) return 'The vessel nears its limit!'
    if (storagePercent.value >= 75) return 'Essence grows dense...'
    return 'Essence flows freely'
  })

  // ═══════════════════════════════════════════════════════════════════════════════
  // DIRECTORY ACTIONS
  // ═══════════════════════════════════════════════════════════════════════════════

  async function fetchDirectory(folderId = null) {
    loading.value = true
    error.value = null

    try {
      const endpoint = folderId
        ? `/api/v1/files/folder/${folderId}`
        : '/api/v1/files'

      const response = await api.get(endpoint)
      const data = response.data

      currentFolder.value = data.current_folder
      folderPath.value = data.path || []
      folders.value = data.folders || []
      files.value = data.files || []
      storageUsed.value = data.storage_used || 0
      storageQuota.value = data.storage_quota || 5 * 1024 * 1024 * 1024

      // Clear selection when navigating
      selectedIds.value = new Set()
    } catch (e) {
      console.error('Failed to fetch directory:', e)
      error.value = e.response?.data?.detail || 'Failed to load files'
    } finally {
      loading.value = false
    }
  }

  async function navigateToFolder(folderId) {
    await fetchDirectory(folderId)
  }

  async function navigateUp() {
    if (currentFolder.value?.parent_id) {
      await fetchDirectory(currentFolder.value.parent_id)
    } else {
      await fetchDirectory(null)
    }
  }

  async function navigateToRoot() {
    await fetchDirectory(null)
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // FOLDER ACTIONS
  // ═══════════════════════════════════════════════════════════════════════════════

  async function createFolder(name, parentId = null) {
    try {
      const response = await api.post('/api/v1/files/folder', {
        name,
        parent_id: parentId || currentFolder.value?.id || null,
      })

      // Refresh directory
      await fetchDirectory(currentFolder.value?.id)
      return response.data
    } catch (e) {
      console.error('Failed to create folder:', e)
      throw e.response?.data?.detail || 'Failed to create folder'
    }
  }

  async function renameFolder(folderId, newName) {
    try {
      await api.patch(`/api/v1/files/folder/${folderId}`, { name: newName })
      await fetchDirectory(currentFolder.value?.id)
    } catch (e) {
      console.error('Failed to rename folder:', e)
      throw e.response?.data?.detail || 'Failed to rename folder'
    }
  }

  async function deleteFolder(folderId) {
    try {
      await api.delete(`/api/v1/files/folder/${folderId}`)
      await fetchDirectory(currentFolder.value?.id)
    } catch (e) {
      console.error('Failed to delete folder:', e)
      throw e.response?.data?.detail || 'Failed to delete folder'
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // FILE ACTIONS
  // ═══════════════════════════════════════════════════════════════════════════════

  async function uploadFiles(fileList) {
    uploading.value = true
    const results = []

    for (const file of fileList) {
      const tempId = `upload_${Date.now()}_${Math.random()}`
      uploadProgress.value[tempId] = {
        name: file.name,
        progress: 0,
        status: 'uploading',
      }

      try {
        const formData = new FormData()
        formData.append('file', file)
        if (currentFolder.value?.id) {
          formData.append('folder_id', currentFolder.value.id)
        }

        const response = await api.post('/api/v1/files/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
          onUploadProgress: (progressEvent) => {
            const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
            if (uploadProgress.value[tempId]) {
              uploadProgress.value[tempId].progress = percent
            }
          },
        })

        uploadProgress.value[tempId].status = 'complete'
        results.push(response.data)
      } catch (e) {
        console.error('Upload failed:', e)
        uploadProgress.value[tempId].status = 'error'
        uploadProgress.value[tempId].error = e.response?.data?.detail || 'Upload failed'
      }
    }

    // Clean up progress after delay
    setTimeout(() => {
      for (const id of Object.keys(uploadProgress.value)) {
        if (uploadProgress.value[id].status !== 'uploading') {
          delete uploadProgress.value[id]
        }
      }
    }, 3000)

    uploading.value = false
    await fetchDirectory(currentFolder.value?.id)
    return results
  }

  async function downloadFile(fileId) {
    try {
      // Get the file metadata first
      const metaResponse = await api.get(`/api/v1/files/${fileId}`)
      const filename = metaResponse.data.original_filename

      // Download the file
      const response = await api.get(`/api/v1/files/${fileId}/download`, {
        responseType: 'blob',
      })

      // Create download link
      const blob = new Blob([response.data])
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (e) {
      console.error('Download failed:', e)
      throw e.response?.data?.detail || 'Download failed'
    }
  }

  async function previewFile(fileId) {
    try {
      const response = await api.get(`/api/v1/files/${fileId}/preview`)
      return response.data
    } catch (e) {
      console.error('Preview failed:', e)
      throw e.response?.data?.detail || 'Preview failed'
    }
  }

  async function renameFile(fileId, newName) {
    try {
      await api.patch(`/api/v1/files/${fileId}`, { name: newName })
      await fetchDirectory(currentFolder.value?.id)
    } catch (e) {
      console.error('Failed to rename file:', e)
      throw e.response?.data?.detail || 'Failed to rename file'
    }
  }

  async function deleteFile(fileId) {
    try {
      await api.delete(`/api/v1/files/${fileId}`)
      await fetchDirectory(currentFolder.value?.id)
    } catch (e) {
      console.error('Failed to delete file:', e)
      throw e.response?.data?.detail || 'Failed to delete file'
    }
  }

  async function toggleFavorite(fileId) {
    try {
      const file = files.value.find(f => f.id === fileId)
      if (!file) return

      await api.patch(`/api/v1/files/${fileId}`, { favorite: !file.favorite })
      file.favorite = !file.favorite
    } catch (e) {
      console.error('Failed to toggle favorite:', e)
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // BULK ACTIONS
  // ═══════════════════════════════════════════════════════════════════════════════

  async function moveItems(fileIds, folderIds, targetFolderId) {
    try {
      await api.post('/api/v1/files/move', {
        file_ids: fileIds,
        folder_ids: folderIds,
        target_folder_id: targetFolderId,
      })
      selectedIds.value = new Set()
      await fetchDirectory(currentFolder.value?.id)
    } catch (e) {
      console.error('Failed to move items:', e)
      throw e.response?.data?.detail || 'Failed to move items'
    }
  }

  async function deleteSelected() {
    const fileIds = []
    const folderIds = []

    for (const id of selectedIds.value) {
      if (files.value.find(f => f.id === id)) {
        fileIds.push(id)
      } else if (folders.value.find(f => f.id === id)) {
        folderIds.push(id)
      }
    }

    try {
      await api.post('/api/v1/files/delete', {
        file_ids: fileIds,
        folder_ids: folderIds,
      })
      selectedIds.value = new Set()
      await fetchDirectory(currentFolder.value?.id)
    } catch (e) {
      console.error('Failed to delete items:', e)
      throw e.response?.data?.detail || 'Failed to delete items'
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // SELECTION
  // ═══════════════════════════════════════════════════════════════════════════════

  function toggleSelect(id) {
    if (selectedIds.value.has(id)) {
      selectedIds.value.delete(id)
    } else {
      selectedIds.value.add(id)
    }
    // Trigger reactivity
    selectedIds.value = new Set(selectedIds.value)
  }

  function selectAll() {
    const allIds = [
      ...folders.value.map(f => f.id),
      ...files.value.map(f => f.id),
    ]
    selectedIds.value = new Set(allIds)
  }

  function clearSelection() {
    selectedIds.value = new Set()
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // VIEW SETTINGS
  // ═══════════════════════════════════════════════════════════════════════════════

  function setViewMode(mode) {
    viewMode.value = mode
    localStorage.setItem('vault_view', mode)
  }

  function setSortBy(field) {
    if (sortBy.value === field) {
      sortAsc.value = !sortAsc.value
    } else {
      sortBy.value = field
      sortAsc.value = true
    }
    localStorage.setItem('vault_sort', field)
    localStorage.setItem('vault_sort_asc', sortAsc.value.toString())
  }

  function setFilterType(type) {
    filterType.value = type === filterType.value ? null : type
  }

  function setSearchQuery(query) {
    searchQuery.value = query
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // SPECIAL LISTINGS
  // ═══════════════════════════════════════════════════════════════════════════════

  async function fetchRecentFiles() {
    try {
      const response = await api.get('/api/v1/files/recent')
      return response.data
    } catch (e) {
      console.error('Failed to fetch recent files:', e)
      return []
    }
  }

  async function fetchFavoriteFiles() {
    try {
      const response = await api.get('/api/v1/files/favorites')
      return response.data
    } catch (e) {
      console.error('Failed to fetch favorites:', e)
      return []
    }
  }

  async function searchFiles(query, fileType = null) {
    try {
      const params = { q: query }
      if (fileType) params.file_type = fileType
      const response = await api.get('/api/v1/files/search/files', { params })
      return response.data
    } catch (e) {
      console.error('Search failed:', e)
      return []
    }
  }

  async function fetchStats() {
    try {
      const response = await api.get('/api/v1/files/stats')
      return response.data
    } catch (e) {
      console.error('Failed to fetch stats:', e)
      return null
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // CLIPBOARD (COPY/CUT/PASTE)
  // ═══════════════════════════════════════════════════════════════════════════════

  function copyToClipboard(mode = 'copy') {
    const items = []
    for (const id of selectedIds.value) {
      const file = files.value.find(f => f.id === id)
      if (file) {
        items.push({ type: 'file', id })
      } else {
        const folder = folders.value.find(f => f.id === id)
        if (folder) {
          items.push({ type: 'folder', id })
        }
      }
    }
    clipboard.value = { items, mode }
  }

  async function paste() {
    if (!clipboard.value.items.length) return

    const fileIds = clipboard.value.items
      .filter(i => i.type === 'file')
      .map(i => i.id)
    const folderIds = clipboard.value.items
      .filter(i => i.type === 'folder')
      .map(i => i.id)

    if (clipboard.value.mode === 'cut') {
      await moveItems(fileIds, folderIds, currentFolder.value?.id || null)
      clipboard.value = { items: [], mode: null }
    } else {
      // Copy operation - would need a copy endpoint
      // For now, just clear clipboard
      console.warn('Copy/paste not yet implemented')
      clipboard.value = { items: [], mode: null }
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // RETURN
  // ═══════════════════════════════════════════════════════════════════════════════

  return {
    // State
    currentFolder,
    folderPath,
    folders,
    files,
    selectedIds,
    clipboard,
    viewMode,
    sortBy,
    sortAsc,
    searchQuery,
    filterType,
    uploading,
    uploadProgress,
    storageUsed,
    storageQuota,
    loading,
    error,

    // Computed
    sortedFolders,
    sortedFiles,
    isSelecting,
    storagePercent,
    storageColor,
    formattedStorageUsed,
    formattedStorageQuota,
    essenceStatus,

    // Helpers
    formatBytes,
    getFileIcon,

    // Directory actions
    fetchDirectory,
    navigateToFolder,
    navigateUp,
    navigateToRoot,

    // Folder actions
    createFolder,
    renameFolder,
    deleteFolder,

    // File actions
    uploadFiles,
    downloadFile,
    previewFile,
    renameFile,
    deleteFile,
    toggleFavorite,

    // Bulk actions
    moveItems,
    deleteSelected,

    // Selection
    toggleSelect,
    selectAll,
    clearSelection,

    // View settings
    setViewMode,
    setSortBy,
    setFilterType,
    setSearchQuery,

    // Special listings
    fetchRecentFiles,
    fetchFavoriteFiles,
    searchFiles,
    fetchStats,

    // Clipboard
    copyToClipboard,
    paste,
  }
})
