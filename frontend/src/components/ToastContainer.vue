<script setup>
import { useToast } from '@/composables/useToast'

const { toasts, removeToast } = useToast()

const typeStyles = {
  success: 'bg-green-500/15 border-green-500/40 text-green-400',
  error: 'bg-red-500/15 border-red-500/40 text-red-400',
  warning: 'bg-amber-500/15 border-amber-500/40 text-amber-400',
  info: 'bg-blue-500/15 border-blue-500/40 text-blue-400',
}

const typeIcons = {
  success: '\u2713',
  error: '\u2717',
  warning: '\u26A0',
  info: '\u2139',
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm w-full pointer-events-none">
      <TransitionGroup
        enter-active-class="transition-all duration-300 ease-out"
        leave-active-class="transition-all duration-200 ease-in"
        enter-from-class="opacity-0 translate-x-8"
        leave-to-class="opacity-0 translate-x-8"
      >
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="pointer-events-auto flex items-start gap-3 px-4 py-3 rounded-lg border backdrop-blur-sm shadow-lg"
          :class="typeStyles[toast.type] || typeStyles.info"
        >
          <span class="text-sm font-bold mt-0.5 shrink-0">{{ typeIcons[toast.type] || typeIcons.info }}</span>
          <span class="text-sm flex-1">{{ toast.message }}</span>
          <button
            @click="removeToast(toast.id)"
            class="text-white/40 hover:text-white/80 transition-colors shrink-0 ml-2"
          >
            &times;
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>
