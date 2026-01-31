/**
 * useDraggableZones - Shared drag layout persistence for village views
 *
 * Handles loading, saving, merging, and resetting custom building layouts
 * from localStorage. Used by both 2D Canvas and 3D Isometric views.
 *
 * "Rearrange the village to your will"
 */

import { ref } from 'vue'

const LAYOUT_VERSION = 1

export function useDraggableZones(storageKey, defaultZones) {
  const hasCustomLayout = ref(!!localStorage.getItem(storageKey))

  function loadLayout() {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return null
    try {
      const data = JSON.parse(raw)
      if (data.version !== LAYOUT_VERSION || !data.zones) return null
      return data
    } catch {
      localStorage.removeItem(storageKey)
      return null
    }
  }

  function saveLayout(zones) {
    localStorage.setItem(storageKey, JSON.stringify({ version: LAYOUT_VERSION, zones }))
    hasCustomLayout.value = true
  }

  function applyLayout(zoneObjects, savedLayout) {
    if (!savedLayout?.zones) return
    for (const [name, pos] of Object.entries(savedLayout.zones)) {
      if (zoneObjects[name]) {
        // Merge saved position into live zone object (preserves all other properties)
        Object.assign(zoneObjects[name], pos)
      }
    }
  }

  function resetLayout() {
    localStorage.removeItem(storageKey)
    hasCustomLayout.value = false
  }

  return { loadLayout, saveLayout, applyLayout, resetLayout, hasCustomLayout }
}
