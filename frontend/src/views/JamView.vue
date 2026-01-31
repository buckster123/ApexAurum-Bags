<template>
  <div class="jam-view min-h-screen bg-gray-900 text-white p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-8">
      <div>
        <h1 class="text-3xl font-bold flex items-center gap-3">
          <span class="text-4xl">🎸</span>
          Village Band Studio
        </h1>
        <p class="text-gray-400 mt-1">Collaborative music composition</p>
      </div>

      <button
        @click="showCreateModal = true"
        class="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 rounded-lg font-semibold hover:from-purple-500 hover:to-pink-500 transition-all flex items-center gap-2"
      >
        <span>🎵</span>
        New Jam Session
      </button>
    </div>

    <!-- Stats Bar -->
    <div class="grid grid-cols-4 gap-4 mb-8">
      <div class="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
        <div class="text-2xl font-bold text-purple-400">{{ jam.sessions.length }}</div>
        <div class="text-gray-400 text-sm">Total Sessions</div>
      </div>
      <div class="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
        <div class="text-2xl font-bold text-green-400">{{ jam.activeSessions.length }}</div>
        <div class="text-gray-400 text-sm">Active Jams</div>
      </div>
      <div class="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
        <div class="text-2xl font-bold text-blue-400">{{ jam.completedSessions.length }}</div>
        <div class="text-gray-400 text-sm">Completed</div>
      </div>
      <div class="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
        <div class="text-2xl font-bold text-yellow-400">{{ totalNotes }}</div>
        <div class="text-gray-400 text-sm">Total Notes</div>
      </div>
    </div>

    <!-- Main Content -->
    <div class="grid grid-cols-3 gap-6">
      <!-- Sessions List -->
      <div class="col-span-1 bg-gray-800/50 rounded-xl border border-gray-700 p-4">
        <h2 class="text-lg font-semibold mb-4 flex items-center gap-2">
          <span>📋</span> Sessions
        </h2>

        <div v-if="jam.isLoading" class="text-center py-8 text-gray-400">
          Loading sessions...
        </div>

        <div v-else-if="jam.sessions.length === 0" class="text-center py-8 text-gray-500">
          <div class="text-4xl mb-2">🎸</div>
          <p>No jam sessions yet</p>
          <p class="text-sm">Create one to get the band together!</p>
        </div>

        <div v-else class="space-y-3 max-h-[600px] overflow-y-auto">
          <div
            v-for="session in jam.sessions"
            :key="session.id"
            @click="selectSession(session.id)"
            class="p-3 rounded-lg cursor-pointer transition-all border"
            :class="[
              jam.currentSession?.id === session.id
                ? 'bg-purple-900/50 border-purple-500'
                : 'bg-gray-700/50 border-gray-600 hover:border-gray-500'
            ]"
          >
            <div class="flex items-start justify-between">
              <div class="font-medium">{{ session.title }}</div>
              <span
                class="text-xs px-2 py-0.5 rounded-full"
                :class="jam.getStateBadge(session.state).color"
              >
                {{ jam.getStateBadge(session.state).label }}
              </span>
            </div>
            <div class="text-sm text-gray-400 mt-1">{{ session.style || 'No style set' }}</div>
            <div class="flex items-center gap-3 mt-2 text-xs text-gray-500">
              <span>👥 {{ session.participant_count }}</span>
              <span>🎵 {{ session.track_count }} tracks</span>
              <span>Round {{ session.current_round }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Session Details / Studio -->
      <div class="col-span-2">
        <div v-if="!jam.currentSession" class="bg-gray-800/50 rounded-xl border border-gray-700 p-8 text-center">
          <div class="text-6xl mb-4">🎤</div>
          <h3 class="text-xl font-semibold mb-2">Select a Jam Session</h3>
          <p class="text-gray-400">Choose a session from the list or create a new one</p>
        </div>

        <div v-else class="space-y-6">
          <!-- Session Header -->
          <div class="bg-gray-800/50 rounded-xl border border-gray-700 p-6">
            <div class="flex items-start justify-between">
              <div>
                <h2 class="text-2xl font-bold">{{ jam.currentSession.title }}</h2>
                <p class="text-gray-400">{{ jam.currentSession.style || 'No style specified' }}</p>
              </div>
              <div class="flex items-center gap-3">
                <span
                  class="px-3 py-1 rounded-full text-sm font-medium"
                  :class="jam.getStateBadge(jam.currentSession.state).color"
                >
                  {{ jam.getStateBadge(jam.currentSession.state).label }}
                </span>
                <button
                  v-if="jam.currentSession.state === 'forming' || jam.currentSession.state === 'jamming'"
                  @click="showAutoJamModal = true"
                  :disabled="jam.isAutoJamming"
                  class="px-4 py-2 bg-green-600 hover:bg-green-500 rounded-lg font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
                >
                  <span v-if="jam.isAutoJamming" class="animate-pulse">🎵</span>
                  <span v-else>🎸</span>
                  {{ jam.isAutoJamming ? 'Jamming...' : 'Auto-Jam' }}
                </button>
                <button
                  v-if="jam.isAutoJamming"
                  @click="jam.stopAutoJam()"
                  class="px-4 py-2 bg-red-600 hover:bg-red-500 rounded-lg font-medium transition-colors"
                >
                  Stop
                </button>
                <button
                  v-if="jam.currentSession.state === 'jamming' && !jam.isAutoJamming"
                  @click="showFinalizeModal = true"
                  class="px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded-lg font-medium transition-colors"
                >
                  Finalize
                </button>
              </div>
            </div>

            <!-- Session Meta -->
            <div class="flex items-center gap-6 mt-4 text-sm">
              <div class="flex items-center gap-2">
                <span class="text-gray-500">Tempo:</span>
                <span class="font-medium">{{ jam.currentSession.tempo }} BPM</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-gray-500">Key:</span>
                <span class="font-medium">{{ jam.currentSession.musical_key }}</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-gray-500">Mode:</span>
                <span class="font-medium capitalize">{{ jam.currentSession.mode }}</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-gray-500">Round:</span>
                <span class="font-medium">{{ jam.currentSession.current_round }} / {{ jam.currentSession.max_rounds }}</span>
              </div>
            </div>

            <!-- Inspiration -->
            <div v-if="jam.currentSession.inspiration" class="mt-4 p-3 bg-gray-700/50 rounded-lg">
              <span class="text-gray-400 text-sm">Inspiration:</span>
              <p class="text-gray-300">{{ jam.currentSession.inspiration }}</p>
            </div>
          </div>

          <!-- Participants -->
          <div class="bg-gray-800/50 rounded-xl border border-gray-700 p-6">
            <h3 class="text-lg font-semibold mb-4 flex items-center gap-2">
              <span>👥</span> The Band
            </h3>
            <div class="grid grid-cols-4 gap-4">
              <div
                v-for="participant in jam.currentSession.participants"
                :key="participant.id"
                class="p-4 rounded-lg border text-center"
                :style="{ borderColor: jam.getAgentColor(participant.agent_id) + '80' }"
              >
                <div class="text-2xl mb-1">{{ jam.getRoleIcon(participant.role) }}</div>
                <div
                  class="font-bold"
                  :style="{ color: jam.getAgentColor(participant.agent_id) }"
                >
                  {{ participant.agent_id }}
                </div>
                <div class="text-sm text-gray-400 capitalize">{{ participant.role }}</div>
                <div class="text-xs text-gray-500 mt-2">
                  {{ participant.contributions }} contributions
                </div>
              </div>
            </div>
          </div>

          <!-- Live Streaming Panel (during auto-jam) -->
          <div
            v-if="jam.isAutoJamming || jam.streamingEvents.length > 0"
            class="bg-gradient-to-r from-green-900/30 to-blue-900/30 rounded-xl border border-green-500/30 p-6"
          >
            <h3 class="text-lg font-semibold mb-4 flex items-center gap-2">
              <span class="animate-pulse" v-if="jam.isAutoJamming">🎵</span>
              <span v-else>🎧</span>
              {{ jam.isAutoJamming ? 'Live Session' : 'Session Replay' }}
              <span v-if="jam.streamingRound" class="text-sm font-normal text-gray-400">
                Round {{ jam.streamingRound }}
              </span>
            </h3>

            <!-- Agent contributions in real-time -->
            <div v-if="Object.keys(jam.streamingAgents).length > 0" class="space-y-3 mb-4">
              <div
                v-for="(data, agentId) in jam.streamingAgents"
                :key="agentId"
                class="p-3 rounded-lg bg-black/30 border-l-4"
                :style="{ borderColor: jam.getAgentColor(agentId) }"
              >
                <div class="flex items-center gap-2 mb-1">
                  <span>{{ jam.getRoleIcon(data.role) }}</span>
                  <span class="font-medium" :style="{ color: jam.getAgentColor(agentId) }">
                    {{ agentId }}
                  </span>
                  <span v-if="data.toolCalls?.length" class="text-xs text-green-400">
                    {{ data.toolCalls.length }} tool call{{ data.toolCalls.length > 1 ? 's' : '' }}
                  </span>
                </div>
                <p class="text-sm text-gray-300">{{ data.content }}</p>
                <!-- Tool calls -->
                <div v-if="data.toolCalls?.length" class="mt-2 space-y-1">
                  <div
                    v-for="(tc, idx) in data.toolCalls"
                    :key="idx"
                    class="text-xs px-2 py-1 bg-gray-800 rounded flex items-center gap-2"
                  >
                    <span class="text-green-400 font-mono">{{ tc.name }}</span>
                    <span v-if="tc.input?.notes" class="text-gray-400">
                      {{ Array.isArray(tc.input.notes) ? tc.input.notes.slice(0, 6).join(', ') : '' }}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Event timeline -->
            <div class="space-y-1 max-h-48 overflow-y-auto text-xs font-mono text-gray-500">
              <div v-for="(event, idx) in jam.streamingEvents.slice(-15)" :key="idx">
                <span v-if="event.type === 'start'" class="text-green-400">
                  ▶ Session started ({{ event.num_rounds }} rounds)
                </span>
                <span v-else-if="event.type === 'round_start'" class="text-blue-400">
                  ── Round {{ event.round_number }} ──
                </span>
                <span v-else-if="event.type === 'round_complete'" class="text-gray-400">
                  ✓ Round {{ event.round_number }} complete ({{ event.total_notes }} notes total)
                </span>
                <span v-else-if="event.type === 'finalizing'" class="text-yellow-400">
                  ⚡ Finalizing {{ event.total_notes }} notes...
                </span>
                <span v-else-if="event.type === 'midi_created'" class="text-purple-400">
                  🎼 MIDI created ({{ event.note_count }} notes)
                </span>
                <span v-else-if="event.type === 'suno_started'" class="text-pink-400">
                  🎧 Suno generation started
                </span>
                <span v-else-if="event.type === 'end'" class="text-green-400">
                  ✦ Session complete! {{ event.total_notes }} notes, {{ event.total_tracks }} tracks
                </span>
              </div>
            </div>
          </div>

          <!-- Tracks / Contributions -->
          <div class="bg-gray-800/50 rounded-xl border border-gray-700 p-6">
            <h3 class="text-lg font-semibold mb-4 flex items-center gap-2">
              <span>🎼</span> Tracks
              <span class="text-sm font-normal text-gray-400">({{ jam.totalNotes }} notes total)</span>
            </h3>

            <div v-if="jam.currentTracks.length === 0" class="text-center py-8 text-gray-500">
              <div class="text-3xl mb-2">🎵</div>
              <p>No contributions yet</p>
              <p class="text-sm">The band is warming up...</p>
            </div>

            <div v-else class="space-y-4">
              <!-- Group by round -->
              <div v-for="(tracks, round) in jam.tracksByRound" :key="round">
                <div class="text-sm text-gray-500 mb-2">Round {{ round }}</div>
                <div class="space-y-2">
                  <div
                    v-for="track in tracks"
                    :key="track.id"
                    class="p-4 rounded-lg border-l-4 bg-gray-700/30"
                    :style="{ borderColor: jam.getAgentColor(track.agent_id) }"
                  >
                    <div class="flex items-center justify-between mb-2">
                      <div class="flex items-center gap-2">
                        <span>{{ jam.getRoleIcon(track.role) }}</span>
                        <span
                          class="font-medium"
                          :style="{ color: jam.getAgentColor(track.agent_id) }"
                        >
                          {{ track.agent_id }}
                        </span>
                        <span class="text-gray-500 text-sm">({{ track.role }})</span>
                      </div>
                      <span class="text-sm text-gray-400">{{ track.notes?.length || 0 }} notes</span>
                    </div>

                    <!-- Notes visualization -->
                    <div class="flex flex-wrap gap-1 mb-2">
                      <span
                        v-for="(note, idx) in (track.notes || []).slice(0, 16)"
                        :key="idx"
                        class="px-2 py-0.5 bg-gray-600 rounded text-xs font-mono"
                      >
                        {{ note.note }}
                      </span>
                      <span v-if="(track.notes?.length || 0) > 16" class="text-gray-500 text-xs">
                        +{{ track.notes.length - 16 }} more
                      </span>
                    </div>

                    <p v-if="track.description" class="text-sm text-gray-400 italic">
                      "{{ track.description }}"
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Final Track (if complete) -->
          <div
            v-if="jam.currentSession.state === 'complete' && jam.currentSession.final_music_task_id"
            class="bg-gradient-to-r from-purple-900/50 to-pink-900/50 rounded-xl border border-purple-500/50 p-6"
          >
            <h3 class="text-lg font-semibold mb-4 flex items-center gap-2">
              <span>🎧</span> Final Track
            </h3>
            <p class="text-gray-300 mb-4">
              The Village Band has created something beautiful! Check it in the Music Library.
            </p>
            <router-link
              :to="{ name: 'music' }"
              class="inline-block px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded-lg font-medium transition-colors"
            >
              View in Music Library
            </router-link>
          </div>
        </div>
      </div>
    </div>

    <!-- Auto-Jam Modal -->
    <div
      v-if="showAutoJamModal"
      class="fixed inset-0 bg-black/70 flex items-center justify-center z-50"
      @click.self="showAutoJamModal = false"
    >
      <div class="bg-gray-800 rounded-xl p-6 w-full max-w-md border border-gray-700">
        <h3 class="text-xl font-bold mb-4 flex items-center gap-2">
          <span>🎸</span> Auto-Jam
        </h3>

        <p class="text-gray-400 mb-4">
          The Village Band will collaborate for multiple rounds, with each agent
          contributing notes and discussing the composition.
        </p>

        <div class="mb-4">
          <label class="block text-sm text-gray-400 mb-1">Rounds to play</label>
          <input
            v-model.number="autoJamRounds"
            type="number"
            min="1"
            max="10"
            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:border-green-500 focus:outline-none"
          />
          <p class="text-xs text-gray-500 mt-1">
            Each round: all agents contribute in parallel
          </p>
        </div>

        <div class="flex justify-end gap-3">
          <button
            @click="showAutoJamModal = false"
            class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            @click="launchAutoJam"
            class="px-6 py-2 bg-green-600 hover:bg-green-500 rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <span>🎸</span> Let's Jam!
          </button>
        </div>
      </div>
    </div>

    <!-- Create Session Modal -->
    <div
      v-if="showCreateModal"
      class="fixed inset-0 bg-black/70 flex items-center justify-center z-50"
      @click.self="showCreateModal = false"
    >
      <div class="bg-gray-800 rounded-xl p-6 w-full max-w-lg border border-gray-700">
        <h3 class="text-xl font-bold mb-6 flex items-center gap-2">
          <span>🎸</span> New Jam Session
        </h3>

        <div class="space-y-4">
          <div>
            <label class="block text-sm text-gray-400 mb-1">Title</label>
            <input
              v-model="newSession.title"
              type="text"
              class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:border-purple-500 focus:outline-none"
              placeholder="Cosmic Journey"
            />
          </div>

          <div>
            <label class="block text-sm text-gray-400 mb-1">Style / Genre</label>
            <input
              v-model="newSession.style"
              type="text"
              class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:border-purple-500 focus:outline-none"
              placeholder="ethereal ambient space, reverb, cosmic"
            />
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm text-gray-400 mb-1">Tempo (BPM)</label>
              <input
                v-model.number="newSession.tempo"
                type="number"
                min="40"
                max="200"
                class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:border-purple-500 focus:outline-none"
              />
            </div>
            <div>
              <label class="block text-sm text-gray-400 mb-1">Key</label>
              <select
                v-model="newSession.musicalKey"
                class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:border-purple-500 focus:outline-none"
              >
                <option>C</option>
                <option>Cm</option>
                <option>D</option>
                <option>Dm</option>
                <option>E</option>
                <option>Em</option>
                <option>F</option>
                <option>Fm</option>
                <option>G</option>
                <option>Gm</option>
                <option>A</option>
                <option>Am</option>
                <option>B</option>
                <option>Bm</option>
              </select>
            </div>
          </div>

          <div>
            <label class="block text-sm text-gray-400 mb-1">Mode</label>
            <div class="grid grid-cols-3 gap-2">
              <button
                v-for="mode in ['conductor', 'jam', 'auto']"
                :key="mode"
                @click="newSession.mode = mode"
                class="px-4 py-2 rounded-lg border transition-colors capitalize"
                :class="[
                  newSession.mode === mode
                    ? 'bg-purple-600 border-purple-500'
                    : 'bg-gray-700 border-gray-600 hover:border-gray-500'
                ]"
              >
                {{ mode }}
              </button>
            </div>
            <p class="text-xs text-gray-500 mt-1">
              {{ modeDescriptions[newSession.mode] }}
            </p>
          </div>

          <div>
            <label class="block text-sm text-gray-400 mb-1">Inspiration (optional)</label>
            <textarea
              v-model="newSession.inspiration"
              rows="2"
              class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:border-purple-500 focus:outline-none resize-none"
              placeholder="A dreamy journey through the cosmos..."
            ></textarea>
          </div>

          <div>
            <label class="block text-sm text-gray-400 mb-1">Max Rounds</label>
            <input
              v-model.number="newSession.maxRounds"
              type="number"
              min="1"
              max="20"
              class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:border-purple-500 focus:outline-none"
            />
          </div>
        </div>

        <div class="flex justify-end gap-3 mt-6">
          <button
            @click="showCreateModal = false"
            class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            @click="createNewSession"
            :disabled="jam.isCreating"
            class="px-6 py-2 bg-purple-600 hover:bg-purple-500 rounded-lg font-medium transition-colors disabled:opacity-50"
          >
            {{ jam.isCreating ? 'Creating...' : 'Create Session' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Finalize Modal -->
    <div
      v-if="showFinalizeModal"
      class="fixed inset-0 bg-black/70 flex items-center justify-center z-50"
      @click.self="showFinalizeModal = false"
    >
      <div class="bg-gray-800 rounded-xl p-6 w-full max-w-md border border-gray-700">
        <h3 class="text-xl font-bold mb-6 flex items-center gap-2">
          <span>🎧</span> Finalize Jam Session
        </h3>

        <p class="text-gray-400 mb-4">
          This will merge all {{ jam.totalNotes }} notes into a MIDI file and send it to Suno for AI transformation.
        </p>

        <div class="space-y-4">
          <div>
            <label class="block text-sm text-gray-400 mb-1">
              Audio Influence ({{ Math.round(finalizeOptions.audioInfluence * 100) }}%)
            </label>
            <input
              v-model.number="finalizeOptions.audioInfluence"
              type="range"
              min="0"
              max="1"
              step="0.1"
              class="w-full"
            />
            <p class="text-xs text-gray-500">
              How closely Suno follows the MIDI composition
            </p>
          </div>

          <div>
            <label class="block text-sm text-gray-400 mb-1">Style Override (optional)</label>
            <input
              v-model="finalizeOptions.styleOverride"
              type="text"
              class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:border-purple-500 focus:outline-none"
              :placeholder="jam.currentSession?.style || 'Keep original style'"
            />
          </div>
        </div>

        <div class="flex justify-end gap-3 mt-6">
          <button
            @click="showFinalizeModal = false"
            class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            @click="finalizeJam"
            :disabled="jam.isFinalizing"
            class="px-6 py-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 rounded-lg font-medium transition-colors disabled:opacity-50"
          >
            {{ jam.isFinalizing ? 'Finalizing...' : 'Create Masterpiece' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useJamStore } from '@/stores/jam'

const jam = useJamStore()

// Modals
const showCreateModal = ref(false)
const showFinalizeModal = ref(false)
const showAutoJamModal = ref(false)

// Auto-jam
const autoJamRounds = ref(3)

// New session form
const newSession = ref({
  title: '',
  style: '',
  tempo: 120,
  musicalKey: 'Am',
  mode: 'jam',
  inspiration: '',
  maxRounds: 5
})

// Finalize options
const finalizeOptions = ref({
  audioInfluence: 0.5,
  styleOverride: ''
})

// Mode descriptions
const modeDescriptions = {
  conductor: 'You direct each agent step by step',
  jam: 'Agents collaborate with style guidance',
  auto: 'Full creative freedom for the band'
}

// Computed
const totalNotes = computed(() => {
  return jam.sessions.reduce((sum, s) => sum + (s.track_count || 0), 0)
})

// Actions
async function selectSession(sessionId) {
  await jam.fetchSession(sessionId)
}

async function createNewSession() {
  const session = await jam.createSession(newSession.value)
  if (session) {
    showCreateModal.value = false
    newSession.value = {
      title: '',
      style: '',
      tempo: 120,
      musicalKey: 'Am',
      mode: 'jam',
      inspiration: '',
      maxRounds: 5
    }
  }
}

async function startJam() {
  if (jam.currentSession) {
    await jam.startSession(jam.currentSession.id)
  }
}

async function launchAutoJam() {
  if (jam.currentSession) {
    showAutoJamModal.value = false
    jam.clearStreamingState()
    await jam.startAutoJam(jam.currentSession.id, autoJamRounds.value)
  }
}

async function finalizeJam() {
  if (jam.currentSession) {
    const result = await jam.finalizeSession(jam.currentSession.id, {
      audioInfluence: finalizeOptions.value.audioInfluence,
      styleOverride: finalizeOptions.value.styleOverride || undefined
    })
    if (result) {
      showFinalizeModal.value = false
    }
  }
}

// Lifecycle
onMounted(() => {
  jam.fetchSessions()
})
</script>

<style scoped>
.jam-view {
  min-height: 100vh;
}

/* Custom range slider */
input[type="range"] {
  -webkit-appearance: none;
  appearance: none;
  height: 8px;
  background: #374151;
  border-radius: 4px;
  outline: none;
}

input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  background: #9333ea;
  border-radius: 50%;
  cursor: pointer;
}

input[type="range"]::-moz-range-thumb {
  width: 20px;
  height: 20px;
  background: #9333ea;
  border-radius: 50%;
  cursor: pointer;
  border: none;
}
</style>
