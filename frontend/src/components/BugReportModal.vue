<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { useToast } from '@/composables/useToast'
import api from '@/services/api'

const props = defineProps({
  show: Boolean,
})
const emit = defineEmits(['close'])

const route = useRoute()
const { showToast } = useToast()

const category = ref('bug')
const description = ref('')
const submitting = ref(false)

async function submit() {
  if (!description.value.trim() || description.value.trim().length < 10) {
    showToast('Please describe the issue in at least 10 characters.', 'warning')
    return
  }

  submitting.value = true
  try {
    await api.post('/api/v1/feedback/report', {
      category: category.value,
      description: description.value.trim(),
      page: route.fullPath,
      browser_info: navigator.userAgent,
    })
    showToast('Report submitted. Thank you for the feedback!', 'success')
    description.value = ''
    category.value = 'bug'
    emit('close')
  } catch (e) {
    console.error('Failed to submit report:', e)
    showToast('Failed to submit report. Please try again.')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="show"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      @click.self="emit('close')"
    >
      <div class="bg-apex-card border border-apex-border rounded-xl p-6 w-full max-w-lg">
        <h3 class="text-lg font-bold text-gold mb-4">Report an Issue</h3>

        <!-- Category -->
        <div class="mb-4">
          <label class="block text-sm text-gray-400 mb-1">Category</label>
          <div class="flex gap-2">
            <button
              v-for="cat in ['bug', 'feedback', 'question']"
              :key="cat"
              @click="category = cat"
              class="px-3 py-1.5 text-sm rounded-lg border transition-colors capitalize"
              :class="category === cat
                ? 'bg-gold/20 border-gold text-gold'
                : 'bg-white/5 border-white/10 text-gray-400 hover:border-white/30'"
            >
              {{ cat === 'bug' ? 'Bug' : cat === 'feedback' ? 'Feedback' : 'Question' }}
            </button>
          </div>
        </div>

        <!-- Description -->
        <div class="mb-4">
          <label class="block text-sm text-gray-400 mb-1">Description</label>
          <textarea
            v-model="description"
            rows="5"
            class="w-full px-3 py-2 bg-apex-dark border border-apex-border rounded-lg text-white placeholder-gray-500 focus:border-gold focus:outline-none resize-none text-sm"
            :placeholder="category === 'bug'
              ? 'What happened? What did you expect to happen? Steps to reproduce...'
              : category === 'feedback'
                ? 'What could be improved? What do you like?'
                : 'What would you like to know?'"
          ></textarea>
          <div class="text-xs text-gray-500 mt-1">
            Page: {{ route.fullPath }}
          </div>
        </div>

        <!-- Actions -->
        <div class="flex gap-3">
          <button
            @click="emit('close')"
            class="flex-1 px-4 py-2 text-sm text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            @click="submit"
            :disabled="submitting || description.trim().length < 10"
            class="flex-1 px-4 py-2 text-sm bg-gold text-black font-medium rounded-lg hover:bg-gold/90 transition-colors disabled:opacity-50"
          >
            {{ submitting ? 'Sending...' : 'Submit Report' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
