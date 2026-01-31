/**
 * Cortex Store - IDE State Management
 *
 * Manages open files, tabs, editor state, and AI integration for Cortex Diver.
 * "Dive deep into the code"
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

export const useCortexStore = defineStore('cortex', () => {
  // ═══════════════════════════════════════════════════════════════════════════════
  // STATE
  // ═══════════════════════════════════════════════════════════════════════════════

  // Open files/tabs
  const openTabs = ref([])  // { id, name, fileType, isDirty }
  const activeTabId = ref(null)

  // File contents (keyed by file ID)
  const fileContents = ref({})
  const originalContents = ref({})  // For dirty checking
  const fileLanguages = ref({})

  // Editor state
  const cursor = ref(null)  // { line, column }
  const selection = ref(null)  // { text, range, action? }

  // Loading state
  const loading = ref(false)
  const error = ref(null)

  // ═══════════════════════════════════════════════════════════════════════════════
  // COMPUTED
  // ═══════════════════════════════════════════════════════════════════════════════

  const activeTab = computed(() =>
    openTabs.value.find(t => t.id === activeTabId.value)
  )

  const hasUnsavedChanges = computed(() =>
    openTabs.value.some(t => t.isDirty)
  )

  // ═══════════════════════════════════════════════════════════════════════════════
  // TAB MANAGEMENT
  // ═══════════════════════════════════════════════════════════════════════════════

  function setActiveTab(tabId) {
    if (openTabs.value.find(t => t.id === tabId)) {
      activeTabId.value = tabId
    }
  }

  async function openFile(file) {
    // Check if already open
    const existingTab = openTabs.value.find(t => t.id === file.id)
    if (existingTab) {
      activeTabId.value = file.id
      return
    }

    loading.value = true
    error.value = null

    try {
      // Fetch file content
      const response = await api.get(`/api/v1/files/${file.id}/content`)
      const data = response.data

      // Store content
      fileContents.value[file.id] = data.content
      originalContents.value[file.id] = data.content
      fileLanguages.value[file.id] = data.language || 'plaintext'

      // Add tab
      openTabs.value.push({
        id: file.id,
        name: file.name,
        fileType: file.file_type,
        isDirty: false,
      })

      // Set as active
      activeTabId.value = file.id
    } catch (e) {
      console.error('Failed to open file:', e)
      error.value = e.response?.data?.detail || 'Failed to open file'
      throw e
    } finally {
      loading.value = false
    }
  }

  function closeTab(tabId) {
    const index = openTabs.value.findIndex(t => t.id === tabId)
    if (index === -1) return

    // Remove tab
    openTabs.value.splice(index, 1)

    // Clean up content
    delete fileContents.value[tabId]
    delete originalContents.value[tabId]
    delete fileLanguages.value[tabId]

    // Update active tab
    if (activeTabId.value === tabId) {
      if (openTabs.value.length > 0) {
        // Select adjacent tab
        const newIndex = Math.min(index, openTabs.value.length - 1)
        activeTabId.value = openTabs.value[newIndex].id
      } else {
        activeTabId.value = null
      }
    }
  }

  function closeAllTabs() {
    openTabs.value = []
    activeTabId.value = null
    fileContents.value = {}
    originalContents.value = {}
    fileLanguages.value = {}
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // CONTENT MANAGEMENT
  // ═══════════════════════════════════════════════════════════════════════════════

  function setFileContent(fileId, content) {
    fileContents.value[fileId] = content

    // Update dirty state
    const tab = openTabs.value.find(t => t.id === fileId)
    if (tab) {
      tab.isDirty = content !== originalContents.value[fileId]
    }
  }

  async function saveFile(fileId) {
    const content = fileContents.value[fileId]
    if (content === undefined) return

    loading.value = true
    error.value = null

    try {
      await api.put(`/api/v1/files/${fileId}/content`, { content })

      // Update original content (no longer dirty)
      originalContents.value[fileId] = content

      // Update tab state
      const tab = openTabs.value.find(t => t.id === fileId)
      if (tab) {
        tab.isDirty = false
      }
    } catch (e) {
      console.error('Failed to save file:', e)
      error.value = e.response?.data?.detail || 'Failed to save file'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function saveAllFiles() {
    const dirtyTabs = openTabs.value.filter(t => t.isDirty)
    for (const tab of dirtyTabs) {
      await saveFile(tab.id)
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // EDITOR STATE
  // ═══════════════════════════════════════════════════════════════════════════════

  function setCursor(pos) {
    cursor.value = pos
  }

  function setSelection(sel) {
    selection.value = sel
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // PERSISTENCE
  // ═══════════════════════════════════════════════════════════════════════════════

  // Save open tabs to sessionStorage for recovery
  function persistState() {
    const state = {
      openTabs: openTabs.value.map(t => ({
        id: t.id,
        name: t.name,
        fileType: t.fileType,
      })),
      activeTabId: activeTabId.value,
    }
    sessionStorage.setItem('cortex_state', JSON.stringify(state))
  }

  function restoreState() {
    try {
      const saved = sessionStorage.getItem('cortex_state')
      if (saved) {
        const state = JSON.parse(saved)
        // Note: We don't restore content, just tab references
        // User will need to reload files
        return state
      }
    } catch (e) {
      console.error('Failed to restore cortex state:', e)
    }
    return null
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // RETURN
  // ═══════════════════════════════════════════════════════════════════════════════

  return {
    // State
    openTabs,
    activeTabId,
    fileContents,
    fileLanguages,
    cursor,
    selection,
    loading,
    error,

    // Computed
    activeTab,
    hasUnsavedChanges,

    // Tab management
    setActiveTab,
    openFile,
    closeTab,
    closeAllTabs,

    // Content management
    setFileContent,
    saveFile,
    saveAllFiles,

    // Editor state
    setCursor,
    setSelection,

    // Persistence
    persistState,
    restoreState,
  }
})
