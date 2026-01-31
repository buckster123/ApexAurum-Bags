<script setup>
import { ref, onMounted } from 'vue'
import { useNurseryStore } from '@/stores/nursery'
import NurseryDataGarden from '@/components/nursery/NurseryDataGarden.vue'
import NurseryTrainingForge from '@/components/nursery/NurseryTrainingForge.vue'
import NurseryModelCradle from '@/components/nursery/NurseryModelCradle.vue'
import NurseryApprentices from '@/components/nursery/NurseryApprentices.vue'
import NurseryVillageFeed from '@/components/nursery/NurseryVillageFeed.vue'

const nursery = useNurseryStore()

const activeTab = ref('garden')
const tabs = [
  { id: 'garden', label: 'Data Garden' },
  { id: 'forge', label: 'Training Forge' },
  { id: 'cradle', label: 'Model Cradle' },
  { id: 'apprentices', label: 'Apprentices' },
  { id: 'feed', label: 'Village Feed' },
]

onMounted(async () => {
  await nursery.fetchDatasets()
  await nursery.fetchStats()
  await nursery.checkTogetherAccess()
})
</script>

<template>
  <div class="min-h-screen bg-apex-dark text-white pt-20 px-4">
    <div class="max-w-6xl mx-auto">

      <!-- Header -->
      <div class="mb-8">
        <h1 class="text-3xl font-serif text-gold">The Nursery</h1>
        <p class="text-gray-400 mt-1">Model Training Studio</p>
      </div>

      <!-- Tier Gate -->
      <div v-if="nursery.tierRequired" class="card border-amber-500/30 bg-amber-500/5 mb-8">
        <h2 class="text-xl font-bold text-amber-400 mb-2">Adept Tier Required</h2>
        <p class="text-gray-400 mb-4">
          The Nursery is available to Adept-tier subscribers ($30/mo).
          Train models, generate datasets, and raise apprentice minds.
        </p>
        <router-link
          to="/billing"
          class="inline-block px-6 py-2 bg-gold text-black font-bold rounded-lg hover:bg-gold/90 transition-colors"
        >
          Upgrade to Adept
        </router-link>
      </div>

      <!-- Tab Bar -->
      <div v-if="!nursery.tierRequired" class="flex gap-4 mb-8 border-b border-apex-border overflow-x-auto">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          class="pb-3 px-2 whitespace-nowrap transition-colors"
          :class="activeTab === tab.id
            ? 'text-gold border-b-2 border-gold'
            : 'text-gray-400 hover:text-white'"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- Tab Content -->
      <template v-if="!nursery.tierRequired">
        <NurseryDataGarden v-if="activeTab === 'garden'" />
        <NurseryTrainingForge v-if="activeTab === 'forge'" />
        <NurseryModelCradle v-if="activeTab === 'cradle'" @navigate-tab="activeTab = $event" />
        <NurseryApprentices v-if="activeTab === 'apprentices'" />
        <NurseryVillageFeed v-if="activeTab === 'feed'" />
      </template>

    </div>
  </div>
</template>
