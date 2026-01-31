<script setup>
/**
 * Terminal Panel - Code Execution for Cortex Diver
 *
 * Run code and see output in a terminal-like interface.
 * Supports Python, JavaScript (Node), and Shell scripts.
 */

import { ref, computed, nextTick, watch } from 'vue'
import { useSound } from '@/composables/useSound'
import api from '@/services/api'

const props = defineProps({
  activeFile: {
    type: Object,
    default: null,
    // { id, name, fileType }
  },
})

const emit = defineEmits(['close'])

const { playTone } = useSound()

// Terminal state
const output = ref([])  // Array of { type: 'stdout'|'stderr'|'system', content: string }
const isRunning = ref(false)
const lastResult = ref(null)
const outputContainer = ref(null)

// Supported extensions
const executableExtensions = ['py', 'js', 'sh', 'bash']

// Check if current file can be executed
const canExecute = computed(() => {
  if (!props.activeFile?.name) return false
  const ext = props.activeFile.name.split('.').pop()?.toLowerCase()
  return executableExtensions.includes(ext)
})

const fileExtension = computed(() => {
  if (!props.activeFile?.name) return ''
  return props.activeFile.name.split('.').pop()?.toLowerCase() || ''
})

const languageName = computed(() => {
  const names = {
    py: 'Python',
    js: 'JavaScript',
    sh: 'Shell',
    bash: 'Bash',
  }
  return names[fileExtension.value] || 'Unknown'
})

// Sound effects
const terminalSounds = {
  run: () => {
    playTone(440, 0.05, 'square', 0.1)
    setTimeout(() => playTone(554, 0.05, 'square', 0.1), 50)
  },
  success: () => playTone(880, 0.1, 'sine', 0.15),
  error: () => {
    playTone(220, 0.1, 'sawtooth', 0.15)
    setTimeout(() => playTone(196, 0.1, 'sawtooth', 0.1), 100)
  },
  clear: () => playTone(330, 0.05, 'sine', 0.1),
}

// Execute the current file
async function runCode() {
  if (!props.activeFile?.id || !canExecute.value || isRunning.value) return

  isRunning.value = true
  terminalSounds.run()

  // Add system message
  addOutput('system', `Running ${props.activeFile.name}...`)

  try {
    const response = await api.post(`/api/v1/files/${props.activeFile.id}/execute`)
    lastResult.value = response.data

    // Add stdout
    if (response.data.stdout) {
      addOutput('stdout', response.data.stdout)
    }

    // Add stderr
    if (response.data.stderr) {
      addOutput('stderr', response.data.stderr)
    }

    // Add result summary
    const status = response.data.success ? 'completed' : 'failed'
    const exitCode = response.data.exit_code
    const time = response.data.execution_time
    addOutput('system', `Process ${status} (exit code: ${exitCode}) in ${time}s`)

    // Sound feedback
    if (response.data.success) {
      terminalSounds.success()
    } else {
      terminalSounds.error()
    }

  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || 'Execution failed'
    addOutput('stderr', `Error: ${errorMsg}`)
    terminalSounds.error()
  } finally {
    isRunning.value = false
  }
}

// Add output to terminal
function addOutput(type, content) {
  output.value.push({
    id: Date.now() + Math.random(),
    type,
    content,
    timestamp: new Date().toLocaleTimeString(),
  })
  scrollToBottom()
}

// Clear terminal
function clearTerminal() {
  output.value = []
  lastResult.value = null
  terminalSounds.clear()
}

// Scroll to bottom
async function scrollToBottom() {
  await nextTick()
  if (outputContainer.value) {
    outputContainer.value.scrollTop = outputContainer.value.scrollHeight
  }
}

// Watch for file changes to clear terminal
watch(() => props.activeFile?.id, () => {
  // Optionally clear on file change
  // clearTerminal()
})
</script>

<template>
  <div class="flex flex-col h-full bg-apex-darker border-t border-apex-border">
    <!-- Header -->
    <div class="flex items-center justify-between px-3 py-2 border-b border-apex-border bg-apex-dark">
      <div class="flex items-center gap-3">
        <span class="text-green-400 font-mono text-sm">$</span>
        <span class="text-xs text-gray-400 uppercase tracking-wider">Terminal</span>
        <span
          v-if="activeFile"
          class="text-xs text-gray-500"
        >
          {{ activeFile.name }}
        </span>
      </div>

      <div class="flex items-center gap-2">
        <!-- Run button -->
        <button
          @click="runCode"
          :disabled="!canExecute || isRunning"
          class="flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors"
          :class="canExecute && !isRunning
            ? 'bg-green-600 hover:bg-green-500 text-white'
            : 'bg-gray-700 text-gray-500 cursor-not-allowed'"
          :title="canExecute ? `Run ${languageName} (F5)` : 'Cannot execute this file type'"
        >
          <svg v-if="!isRunning" class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clip-rule="evenodd" />
          </svg>
          <svg v-else class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          {{ isRunning ? 'Running...' : 'Run' }}
        </button>

        <!-- Clear button -->
        <button
          @click="clearTerminal"
          class="text-gray-500 hover:text-gray-300 text-xs px-2 py-1"
          title="Clear terminal"
        >
          Clear
        </button>

        <!-- Close button -->
        <button
          @click="emit('close')"
          class="text-gray-500 hover:text-gray-300"
          title="Close terminal"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Output area -->
    <div
      ref="outputContainer"
      class="flex-1 overflow-y-auto p-3 font-mono text-sm"
    >
      <!-- Empty state -->
      <div
        v-if="output.length === 0"
        class="text-gray-600 text-center py-8"
      >
        <div class="text-2xl mb-2">$_</div>
        <p v-if="canExecute">Press <kbd class="px-1.5 py-0.5 bg-apex-dark rounded text-xs">F5</kbd> or click Run to execute</p>
        <p v-else class="text-amber-600">Select a Python, JavaScript, or Shell file to run</p>
      </div>

      <!-- Output lines -->
      <div
        v-for="line in output"
        :key="line.id"
        class="mb-1 whitespace-pre-wrap break-all"
        :class="{
          'text-gray-300': line.type === 'stdout',
          'text-red-400': line.type === 'stderr',
          'text-amber-500 text-xs': line.type === 'system',
        }"
      >
        <span v-if="line.type === 'system'" class="text-gray-600">[{{ line.timestamp }}] </span>
        <span v-if="line.type === 'stdout'" class="text-green-500 select-none">❯ </span>
        <span v-if="line.type === 'stderr'" class="text-red-500 select-none">✗ </span>
        {{ line.content }}
      </div>

      <!-- Running indicator -->
      <div
        v-if="isRunning"
        class="flex items-center gap-2 text-amber-400"
      >
        <div class="animate-pulse">●</div>
        <span>Running...</span>
      </div>
    </div>

    <!-- Status bar -->
    <div class="flex items-center justify-between px-3 py-1 border-t border-apex-border text-xs text-gray-600 bg-apex-dark">
      <div class="flex items-center gap-3">
        <span v-if="canExecute" class="text-green-500">● {{ languageName }}</span>
        <span v-else class="text-gray-500">● No runtime</span>
      </div>
      <div v-if="lastResult" class="flex items-center gap-3">
        <span :class="lastResult.success ? 'text-green-500' : 'text-red-500'">
          Exit: {{ lastResult.exit_code }}
        </span>
        <span>{{ lastResult.execution_time }}s</span>
        <span v-if="lastResult.truncated" class="text-amber-500">Truncated</span>
      </div>
    </div>
  </div>
</template>
