<script setup>
/**
 * File Tabs Component for Cortex Diver
 *
 * Manages open file tabs with dirty state indicators.
 */

import { computed } from 'vue'

const props = defineProps({
  tabs: {
    type: Array,
    default: () => [],
    // Each tab: { id, name, fileType, isDirty }
  },
  activeTabId: {
    type: String,
    default: null,
  },
})

const emit = defineEmits(['select', 'close', 'close-others', 'close-all'])

function getIcon(fileType) {
  const icons = {
    document: '📜',
    code: '⚗️',
    image: '🪞',
    data: '💎',
    archive: '🗃️',
    other: '✧',
  }
  return icons[fileType] || icons.other
}

function handleMiddleClick(event, tabId) {
  if (event.button === 1) {
    event.preventDefault()
    emit('close', tabId)
  }
}

function handleContextMenu(event, tabId) {
  // For now, just close - could expand to full context menu
  event.preventDefault()
}
</script>

<template>
  <div class="flex items-center bg-apex-darker border-b border-apex-border overflow-x-auto">
    <!-- Tabs -->
    <div class="flex items-center min-w-0">
      <div
        v-for="tab in tabs"
        :key="tab.id"
        @click="emit('select', tab.id)"
        @mousedown="handleMiddleClick($event, tab.id)"
        @contextmenu="handleContextMenu($event, tab.id)"
        class="flex items-center gap-2 px-3 py-2 border-r border-apex-border cursor-pointer transition-colors whitespace-nowrap group"
        :class="{
          'bg-apex-dark text-white': tab.id === activeTabId,
          'text-gray-400 hover:text-gray-200 hover:bg-apex-border/30': tab.id !== activeTabId,
        }"
      >
        <!-- File icon -->
        <span class="text-sm">{{ getIcon(tab.fileType) }}</span>

        <!-- Filename -->
        <span class="text-sm max-w-32 truncate">{{ tab.name }}</span>

        <!-- Dirty indicator -->
        <span
          v-if="tab.isDirty"
          class="w-2 h-2 rounded-full bg-amber-500"
          title="Unsaved changes"
        ></span>

        <!-- Close button -->
        <button
          @click.stop="emit('close', tab.id)"
          class="opacity-0 group-hover:opacity-100 hover:text-red-400 transition-opacity ml-1"
          title="Close (Middle click)"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Spacer -->
    <div class="flex-1"></div>

    <!-- Tab actions -->
    <div v-if="tabs.length > 0" class="flex items-center px-2">
      <button
        @click="emit('close-all')"
        class="text-xs text-gray-500 hover:text-gray-300 px-2 py-1"
        title="Close all tabs"
      >
        Close All
      </button>
    </div>
  </div>
</template>
