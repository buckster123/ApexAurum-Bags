/**
 * usePixelSprites - Pixel Art Sprite System for Village RPG
 *
 * All pixel art defined as code — no external image files needed.
 * Characters use palette-swap templates, buildings and terrain use direct colors.
 * Offscreen canvas caching for O(1) per-frame rendering.
 *
 * "The village awakens in pixels"
 */

import { ref } from 'vue'

// ═══════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════

export const SPRITE_SCALE = 3
const CHAR_W = 16
const CHAR_H = 24
const BUILD_SIZE = 32
const TILE_SIZE = 16

// Palette index keys: 0=transparent, 1=outline, 2=skin, 3=robe, 4=accent, 5=hair, 6=boots
const PALETTE_KEYS = [null, 'outline', 'skin', 'robe', 'accent', 'hair', 'boots']

const AGENT_PALETTES = {
  CLAUDE:  { outline: '#1a1a2e', skin: '#f5c6a0', robe: '#0077cc', accent: '#00aaff', hair: '#3a2a1a', boots: '#4a3728' },
  AZOTH:   { outline: '#1a1a2e', skin: '#f5c6a0', robe: '#b8860b', accent: '#FFD700', hair: '#f0e68c', boots: '#4a3728' },
  VAJRA:   { outline: '#1a1a2e', skin: '#f5c6a0', robe: '#0277bd', accent: '#4FC3F7', hair: '#1a237e', boots: '#4a3728' },
  ELYSIAN: { outline: '#1a1a2e', skin: '#f5c6a0', robe: '#c2185b', accent: '#ff69b4', hair: '#e8b4ff', boots: '#4a3728' },
  KETHER:  { outline: '#1a1a2e', skin: '#f5c6a0', robe: '#6a1b9a', accent: '#9370db', hair: '#d1c4e9', boots: '#4a3728' },
}

// ═══════════════════════════════════════════════════════════════
// CHARACTER SPRITE TEMPLATES (16x24, palette indices)
// ═══════════════════════════════════════════════════════════════
// Each row is 16 values. 24 rows per frame.
// 0=transparent, 1=outline, 2=skin, 3=robe, 4=accent, 5=hair, 6=boots

// prettier-ignore
const CHAR_IDLE_0 = [
  0,0,0,0,0,0,5,5,5,5,0,0,0,0,0,0,
  0,0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,
  0,0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,
  0,0,0,0,1,2,2,2,2,2,2,1,0,0,0,0,
  0,0,0,0,2,1,2,2,2,1,2,2,0,0,0,0,
  0,0,0,0,1,2,2,2,2,2,2,1,0,0,0,0,
  0,0,0,0,0,1,2,2,2,2,1,0,0,0,0,0,
  0,0,0,0,1,3,4,4,4,4,3,1,0,0,0,0,
  0,0,0,1,3,3,3,4,4,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,1,3,3,3,3,3,3,3,3,3,3,1,0,0,
  0,0,1,3,3,3,3,3,3,3,3,3,3,1,0,0,
  0,0,1,3,3,3,3,3,3,3,3,3,3,1,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,1,1,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,1,1,3,3,1,0,0,0,0,
  0,0,0,0,1,6,6,1,1,6,6,1,0,0,0,0,
  0,0,0,0,1,6,6,1,1,6,6,1,0,0,0,0,
  0,0,0,0,0,1,1,0,0,1,1,0,0,0,0,0,
]

// Idle frame 1: slight arm shift
// prettier-ignore
const CHAR_IDLE_1 = [
  0,0,0,0,0,0,5,5,5,5,0,0,0,0,0,0,
  0,0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,
  0,0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,
  0,0,0,0,1,2,2,2,2,2,2,1,0,0,0,0,
  0,0,0,0,2,1,2,2,2,1,2,2,0,0,0,0,
  0,0,0,0,1,2,2,2,2,2,2,1,0,0,0,0,
  0,0,0,0,0,1,2,2,2,2,1,0,0,0,0,0,
  0,0,0,0,1,3,4,4,4,4,3,1,0,0,0,0,
  0,0,0,1,3,3,3,4,4,3,3,3,1,0,0,0,
  0,0,1,3,3,3,3,3,3,3,3,3,3,1,0,0,
  0,0,1,3,3,3,3,3,3,3,3,3,3,1,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,1,1,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,1,1,3,3,1,0,0,0,0,
  0,0,0,0,1,6,6,1,1,6,6,1,0,0,0,0,
  0,0,0,0,1,6,6,1,1,6,6,1,0,0,0,0,
  0,0,0,0,0,1,1,0,0,1,1,0,0,0,0,0,
]

// Walk down frame 0 (left foot forward)
// prettier-ignore
const CHAR_WALK_DOWN_0 = [
  0,0,0,0,0,0,5,5,5,5,0,0,0,0,0,0,
  0,0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,
  0,0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,
  0,0,0,0,1,2,2,2,2,2,2,1,0,0,0,0,
  0,0,0,0,2,1,2,2,2,1,2,2,0,0,0,0,
  0,0,0,0,1,2,2,2,2,2,2,1,0,0,0,0,
  0,0,0,0,0,1,2,2,2,2,1,0,0,0,0,0,
  0,0,0,0,1,3,4,4,4,4,3,1,0,0,0,0,
  0,0,0,1,3,3,3,4,4,3,3,3,1,0,0,0,
  0,0,1,3,3,3,3,3,3,3,3,3,3,1,0,0,
  0,0,1,3,3,3,3,3,3,3,3,3,3,1,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,1,1,3,3,1,0,0,0,0,
  0,0,0,0,1,6,6,1,0,1,3,1,0,0,0,0,
  0,0,0,1,6,6,1,0,0,1,3,1,0,0,0,0,
  0,0,0,1,6,6,1,0,0,1,6,6,1,0,0,0,
  0,0,0,0,1,1,0,0,0,1,6,6,1,0,0,0,
  0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,0,
]

// Walk down frame 1 (right foot forward)
// prettier-ignore
const CHAR_WALK_DOWN_1 = [
  0,0,0,0,0,0,5,5,5,5,0,0,0,0,0,0,
  0,0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,
  0,0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,
  0,0,0,0,1,2,2,2,2,2,2,1,0,0,0,0,
  0,0,0,0,2,1,2,2,2,1,2,2,0,0,0,0,
  0,0,0,0,1,2,2,2,2,2,2,1,0,0,0,0,
  0,0,0,0,0,1,2,2,2,2,1,0,0,0,0,0,
  0,0,0,0,1,3,4,4,4,4,3,1,0,0,0,0,
  0,0,0,1,3,3,3,4,4,3,3,3,1,0,0,0,
  0,0,1,3,3,3,3,3,3,3,3,3,3,1,0,0,
  0,0,1,3,3,3,3,3,3,3,3,3,3,1,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,1,1,3,3,1,0,0,0,0,
  0,0,0,0,1,3,1,0,1,6,6,1,0,0,0,0,
  0,0,0,0,1,3,1,0,0,1,6,6,1,0,0,0,
  0,0,0,1,6,6,1,0,0,0,1,6,1,0,0,0,
  0,0,0,1,6,6,1,0,0,0,0,1,0,0,0,0,
  0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0,
]

// Walk left frame 0
// prettier-ignore
const CHAR_WALK_LEFT_0 = [
  0,0,0,0,0,5,5,5,5,0,0,0,0,0,0,0,
  0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,0,
  0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,0,
  0,0,0,1,2,2,2,2,2,1,0,0,0,0,0,0,
  0,0,0,1,1,2,2,2,2,1,0,0,0,0,0,0,
  0,0,0,1,2,2,2,2,2,1,0,0,0,0,0,0,
  0,0,0,0,1,2,2,2,1,0,0,0,0,0,0,0,
  0,0,0,1,4,4,4,3,3,1,0,0,0,0,0,0,
  0,0,1,3,3,4,3,3,3,3,1,0,0,0,0,0,
  0,1,3,3,3,3,3,3,3,3,1,0,0,0,0,0,
  0,1,3,3,3,3,3,3,3,3,1,0,0,0,0,0,
  0,0,1,3,3,3,3,3,3,3,1,0,0,0,0,0,
  0,0,1,3,3,3,3,3,3,3,1,0,0,0,0,0,
  0,0,0,1,3,3,3,3,3,1,0,0,0,0,0,0,
  0,0,0,1,3,3,3,3,3,1,0,0,0,0,0,0,
  0,0,0,1,3,3,3,3,3,1,0,0,0,0,0,0,
  0,0,0,0,1,3,3,3,1,0,0,0,0,0,0,0,
  0,0,0,0,1,3,3,3,1,0,0,0,0,0,0,0,
  0,0,0,0,1,3,1,3,1,0,0,0,0,0,0,0,
  0,0,0,0,1,6,1,1,6,1,0,0,0,0,0,0,
  0,0,0,1,6,6,1,1,6,6,0,0,0,0,0,0,
  0,0,0,1,6,1,0,0,1,0,0,0,0,0,0,0,
  0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,
  0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
]

// Walk left frame 1
// prettier-ignore
const CHAR_WALK_LEFT_1 = [
  0,0,0,0,0,5,5,5,5,0,0,0,0,0,0,0,
  0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,0,
  0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,0,
  0,0,0,1,2,2,2,2,2,1,0,0,0,0,0,0,
  0,0,0,1,1,2,2,2,2,1,0,0,0,0,0,0,
  0,0,0,1,2,2,2,2,2,1,0,0,0,0,0,0,
  0,0,0,0,1,2,2,2,1,0,0,0,0,0,0,0,
  0,0,0,1,4,4,4,3,3,1,0,0,0,0,0,0,
  0,0,1,3,3,4,3,3,3,3,1,0,0,0,0,0,
  0,1,3,3,3,3,3,3,3,3,1,0,0,0,0,0,
  0,1,3,3,3,3,3,3,3,3,1,0,0,0,0,0,
  0,0,1,3,3,3,3,3,3,3,1,0,0,0,0,0,
  0,0,1,3,3,3,3,3,3,3,1,0,0,0,0,0,
  0,0,0,1,3,3,3,3,3,1,0,0,0,0,0,0,
  0,0,0,1,3,3,3,3,3,1,0,0,0,0,0,0,
  0,0,0,1,3,3,3,3,3,1,0,0,0,0,0,0,
  0,0,0,0,1,3,3,3,1,0,0,0,0,0,0,0,
  0,0,0,0,1,3,3,3,1,0,0,0,0,0,0,0,
  0,0,0,0,1,3,1,3,1,0,0,0,0,0,0,0,
  0,0,0,0,1,6,1,1,6,1,0,0,0,0,0,0,
  0,0,0,0,1,6,0,0,6,6,1,0,0,0,0,0,
  0,0,0,0,0,1,0,1,6,1,0,0,0,0,0,0,
  0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,
  0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
]

// Working frame 0: arms raised
// prettier-ignore
const CHAR_WORK_0 = [
  0,0,0,0,0,0,5,5,5,5,0,0,0,0,0,0,
  0,0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,
  0,0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,
  0,0,0,0,1,2,2,2,2,2,2,1,0,0,0,0,
  0,0,0,0,2,1,2,2,2,1,2,2,0,0,0,0,
  0,0,0,0,1,2,2,2,2,2,2,1,0,0,0,0,
  0,0,0,0,0,1,2,2,2,2,1,0,0,0,0,0,
  0,0,0,0,1,3,4,4,4,4,3,1,0,0,0,0,
  0,2,1,1,3,3,3,4,4,3,3,3,1,1,2,0,
  0,0,2,1,3,3,3,3,3,3,3,3,1,2,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,1,1,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,1,1,3,3,1,0,0,0,0,
  0,0,0,0,1,6,6,1,1,6,6,1,0,0,0,0,
  0,0,0,0,1,6,6,1,1,6,6,1,0,0,0,0,
  0,0,0,0,0,1,1,0,0,1,1,0,0,0,0,0,
]

// Working frame 1: arms higher + sparkle accent
// prettier-ignore
const CHAR_WORK_1 = [
  0,0,0,4,0,0,5,5,5,5,0,0,4,0,0,0,
  0,0,4,0,0,5,5,5,5,5,5,0,0,4,0,0,
  0,0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,
  0,0,0,0,1,2,2,2,2,2,2,1,0,0,0,0,
  0,0,0,0,2,1,2,2,2,1,2,2,0,0,0,0,
  0,0,0,0,1,2,2,2,2,2,2,1,0,0,0,0,
  0,0,0,0,0,1,2,2,2,2,1,0,0,0,0,0,
  0,2,0,0,1,3,4,4,4,4,3,1,0,0,2,0,
  2,0,2,1,3,3,3,4,4,3,3,3,1,2,0,2,
  0,2,0,1,3,3,3,3,3,3,3,3,1,0,2,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,1,1,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,1,1,3,3,1,0,0,0,0,
  0,0,0,0,1,6,6,1,1,6,6,1,0,0,0,0,
  0,0,0,0,1,6,6,1,1,6,6,1,0,0,0,0,
  0,0,0,0,0,1,1,0,0,1,1,0,0,0,0,0,
]

// Working frame 2: sparkles dispersed
// prettier-ignore
const CHAR_WORK_2 = [
  0,4,0,0,0,0,5,5,5,5,0,0,0,0,4,0,
  0,0,0,0,0,5,5,5,5,5,5,0,0,0,0,0,
  0,0,0,4,0,5,5,5,5,5,5,0,4,0,0,0,
  0,0,0,0,1,2,2,2,2,2,2,1,0,0,0,0,
  0,0,0,0,2,1,2,2,2,1,2,2,0,0,0,0,
  0,0,0,0,1,2,2,2,2,2,2,1,0,0,0,0,
  0,0,0,0,0,1,2,2,2,2,1,0,0,0,0,0,
  0,0,0,0,1,3,4,4,4,4,3,1,0,0,0,0,
  0,0,2,1,3,3,3,4,4,3,3,3,1,2,0,0,
  0,2,0,1,3,3,3,3,3,3,3,3,1,0,2,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,1,3,3,3,3,3,3,3,3,1,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,3,3,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,1,1,3,3,1,0,0,0,0,
  0,0,0,0,1,3,3,1,1,3,3,1,0,0,0,0,
  0,0,0,0,1,6,6,1,1,6,6,1,0,0,0,0,
  0,0,0,0,1,6,6,1,1,6,6,1,0,0,0,0,
  0,0,0,0,0,1,1,0,0,1,1,0,0,0,0,0,
]

// Walk up uses idle base (back of head = hair color dominant)
const CHAR_WALK_UP_0 = CHAR_WALK_DOWN_0 // Simplified: same silhouette
const CHAR_WALK_UP_1 = CHAR_WALK_DOWN_1

// Animation frame sets
const CHAR_FRAMES = {
  idle:       [CHAR_IDLE_0, CHAR_IDLE_1],
  walk_down:  [CHAR_WALK_DOWN_0, CHAR_WALK_DOWN_1],
  walk_up:    [CHAR_WALK_UP_0, CHAR_WALK_UP_1],
  walk_left:  [CHAR_WALK_LEFT_0, CHAR_WALK_LEFT_1],
  walk_right: null, // Generated by flipping walk_left
  working:    [CHAR_WORK_0, CHAR_WORK_1, CHAR_WORK_2],
}

// ═══════════════════════════════════════════════════════════════
// BUILDING SPRITES (32x32, direct hex colors)
// ═══════════════════════════════════════════════════════════════

function generateBuilding(baseColor, roofColor, accentColor, feature) {
  const canvas = document.createElement('canvas')
  canvas.width = BUILD_SIZE * SPRITE_SCALE
  canvas.height = BUILD_SIZE * SPRITE_SCALE
  const ctx = canvas.getContext('2d')
  ctx.imageSmoothingEnabled = false
  const s = SPRITE_SCALE

  // Foundation / walls
  ctx.fillStyle = baseColor
  ctx.fillRect(4*s, 10*s, 24*s, 18*s)

  // Outline
  ctx.strokeStyle = '#1a1a2e'
  ctx.lineWidth = s
  ctx.strokeRect(4*s + s/2, 10*s + s/2, 24*s - s, 18*s - s)

  // Roof (triangle)
  ctx.fillStyle = roofColor
  ctx.beginPath()
  ctx.moveTo(2*s, 12*s)
  ctx.lineTo(16*s, 2*s)
  ctx.lineTo(30*s, 12*s)
  ctx.closePath()
  ctx.fill()
  ctx.strokeStyle = '#1a1a2e'
  ctx.lineWidth = s
  ctx.stroke()

  // Door
  ctx.fillStyle = '#2a1a0e'
  ctx.fillRect(13*s, 20*s, 6*s, 8*s)
  ctx.fillStyle = accentColor
  ctx.fillRect(17*s, 23*s, s, s) // Door handle

  // Feature (icon/decoration unique to each building)
  if (feature) feature(ctx, s, accentColor)

  return canvas
}

const BUILDING_GENERATORS = {
  village_square: (ctx, s, accent) => {
    // Fountain - no roof, open plaza with water
    const canvas = ctx.canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    // Stone floor
    ctx.fillStyle = '#666677'
    ctx.fillRect(2*s, 2*s, 28*s, 28*s)
    ctx.strokeStyle = '#555566'
    ctx.lineWidth = s
    for (let i = 0; i < 4; i++) {
      ctx.strokeRect((2 + i*7)*s, 2*s, 7*s, 28*s)
    }
    // Fountain basin
    ctx.fillStyle = '#4a4a5e'
    ctx.beginPath()
    ctx.arc(16*s, 16*s, 8*s, 0, Math.PI * 2)
    ctx.fill()
    // Water
    ctx.fillStyle = '#4FC3F7'
    ctx.beginPath()
    ctx.arc(16*s, 16*s, 6*s, 0, Math.PI * 2)
    ctx.fill()
    // Center spout
    ctx.fillStyle = '#888899'
    ctx.fillRect(15*s, 12*s, 2*s, 8*s)
  },
  dj_booth: (ctx, s, accent) => {
    // Music notes on wall
    ctx.fillStyle = accent
    ctx.font = `${8*s}px serif`
    ctx.fillText('\u266B', 7*s, 19*s)
    ctx.fillText('\u266A', 20*s, 22*s)
  },
  memory_garden: (ctx, s, accent) => {
    // Flowers
    ctx.fillStyle = '#22aa44'
    ctx.fillRect(6*s, 14*s, 3*s, 3*s)
    ctx.fillRect(23*s, 14*s, 3*s, 3*s)
    ctx.fillStyle = accent
    ctx.fillRect(7*s, 13*s, s, s)
    ctx.fillRect(24*s, 13*s, s, s)
  },
  file_shed: (ctx, s, accent) => {
    // Scroll icon on wall
    ctx.fillStyle = '#f5e6c8'
    ctx.fillRect(8*s, 14*s, 5*s, 6*s)
    ctx.fillStyle = accent
    ctx.fillRect(9*s, 15*s, 3*s, s)
    ctx.fillRect(9*s, 17*s, 3*s, s)
  },
  workshop: (ctx, s, accent) => {
    // Anvil + fire glow
    ctx.fillStyle = '#777788'
    ctx.fillRect(20*s, 16*s, 6*s, 4*s)
    ctx.fillRect(22*s, 14*s, 2*s, 2*s)
    ctx.fillStyle = accent
    ctx.fillRect(8*s, 14*s, 3*s, 3*s) // Fire
    ctx.fillStyle = '#ff6600'
    ctx.fillRect(9*s, 13*s, s, s) // Flame tip
  },
  bridge_portal: (ctx, s, accent) => {
    // Portal glow in doorway
    ctx.fillStyle = accent
    ctx.globalAlpha = 0.6
    ctx.beginPath()
    ctx.arc(16*s, 22*s, 3*s, 0, Math.PI * 2)
    ctx.fill()
    ctx.globalAlpha = 0.3
    ctx.beginPath()
    ctx.arc(16*s, 22*s, 5*s, 0, Math.PI * 2)
    ctx.fill()
    ctx.globalAlpha = 1.0
  },
  library: (ctx, s, accent) => {
    // Books on shelves
    const bookColors = ['#cc3333', '#3333cc', '#33cc33', accent, '#cccc33']
    for (let i = 0; i < 5; i++) {
      ctx.fillStyle = bookColors[i]
      ctx.fillRect((7 + i*3)*s, 14*s, 2*s, 5*s)
    }
  },
  watchtower: (ctx, s, accent) => {
    // Flag on top
    ctx.fillStyle = accent
    ctx.fillRect(15*s, 3*s, s, 5*s) // Pole
    ctx.fillRect(16*s, 3*s, 4*s, 3*s) // Flag
  },
}

const BUILDING_CONFIGS = {
  village_square: { base: '#666677',  roof: '#555566',  accent: '#4FC3F7' },
  dj_booth:       { base: '#4a2866',  roof: '#6b3fa0',  accent: '#e040fb' },
  memory_garden:  { base: '#2d5a1e',  roof: '#3d7a2e',  accent: '#76ff03' },
  file_shed:      { base: '#5d4037',  roof: '#795548',  accent: '#ffcc02' },
  workshop:       { base: '#555555',  roof: '#777777',  accent: '#ff5722' },
  bridge_portal:  { base: '#4a4a6a',  roof: '#6060a0',  accent: '#b388ff' },
  library:        { base: '#1a4a7a',  roof: '#2a6aaa',  accent: '#64b5f6' },
  watchtower:     { base: '#5a5a5a',  roof: '#7a7a7a',  accent: '#ffc107' },
}

// ═══════════════════════════════════════════════════════════════
// TERRAIN TILES (16x16, direct hex colors)
// ═══════════════════════════════════════════════════════════════

function generateTerrainTile(type) {
  const canvas = document.createElement('canvas')
  canvas.width = TILE_SIZE * SPRITE_SCALE
  canvas.height = TILE_SIZE * SPRITE_SCALE
  const ctx = canvas.getContext('2d')
  ctx.imageSmoothingEnabled = false
  const s = SPRITE_SCALE

  if (type === 'grass_0' || type === 'grass_1') {
    // Base green
    ctx.fillStyle = type === 'grass_0' ? '#2d5a1e' : '#2a5520'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    // Sparse lighter grass blades
    ctx.fillStyle = type === 'grass_0' ? '#3d7a2e' : '#357028'
    const seed = type === 'grass_0' ? 0 : 7
    for (let i = 0; i < 8; i++) {
      const px = ((i * 5 + seed) % 16)
      const py = ((i * 7 + seed + 3) % 16)
      ctx.fillRect(px * s, py * s, s, s)
    }
    // Dark spots for depth
    ctx.fillStyle = type === 'grass_0' ? '#254e18' : '#234a16'
    for (let i = 0; i < 4; i++) {
      const px = ((i * 11 + seed + 2) % 16)
      const py = ((i * 9 + seed + 5) % 16)
      ctx.fillRect(px * s, py * s, s, s)
    }
  } else if (type === 'path') {
    // Dirt path
    ctx.fillStyle = '#8b7355'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    // Pebbles
    ctx.fillStyle = '#a08a6c'
    for (let i = 0; i < 6; i++) {
      const px = (i * 7 + 2) % 16
      const py = (i * 5 + 1) % 16
      ctx.fillRect(px * s, py * s, s, s)
    }
    ctx.fillStyle = '#7a6548'
    for (let i = 0; i < 4; i++) {
      const px = (i * 9 + 4) % 16
      const py = (i * 11 + 3) % 16
      ctx.fillRect(px * s, py * s, s, s)
    }
  }

  return canvas
}

// ═══════════════════════════════════════════════════════════════
// SPRITE CACHE
// ═══════════════════════════════════════════════════════════════

const spriteCache = new Map()   // "CLAUDE_idle_0" -> canvas
const buildingCache = new Map() // "village_square" -> canvas
const terrainCache = new Map()  // "grass_0" -> canvas
let cacheBuilt = false

function renderCharFrame(frameData, palette) {
  const canvas = document.createElement('canvas')
  canvas.width = CHAR_W * SPRITE_SCALE
  canvas.height = CHAR_H * SPRITE_SCALE
  const ctx = canvas.getContext('2d')
  ctx.imageSmoothingEnabled = false

  for (let py = 0; py < CHAR_H; py++) {
    for (let px = 0; px < CHAR_W; px++) {
      const idx = frameData[py * CHAR_W + px]
      if (idx === 0) continue // transparent
      const key = PALETTE_KEYS[idx]
      if (!key || !palette[key]) continue
      ctx.fillStyle = palette[key]
      ctx.fillRect(px * SPRITE_SCALE, py * SPRITE_SCALE, SPRITE_SCALE, SPRITE_SCALE)
    }
  }
  return canvas
}

function flipCanvasHorizontal(source) {
  const canvas = document.createElement('canvas')
  canvas.width = source.width
  canvas.height = source.height
  const ctx = canvas.getContext('2d')
  ctx.imageSmoothingEnabled = false
  ctx.translate(canvas.width, 0)
  ctx.scale(-1, 1)
  ctx.drawImage(source, 0, 0)
  return canvas
}

function initSpriteCache() {
  if (cacheBuilt) return

  // Build character sprites for each agent
  for (const [agentId, palette] of Object.entries(AGENT_PALETTES)) {
    for (const [animName, frames] of Object.entries(CHAR_FRAMES)) {
      if (animName === 'walk_right') continue // Generated from walk_left
      if (!frames) continue

      frames.forEach((frameData, frameIdx) => {
        const key = `${agentId}_${animName}_${frameIdx}`
        spriteCache.set(key, renderCharFrame(frameData, palette))
      })
    }

    // Generate walk_right by flipping walk_left
    const leftFrames = CHAR_FRAMES.walk_left
    if (leftFrames) {
      leftFrames.forEach((_, frameIdx) => {
        const leftKey = `${agentId}_walk_left_${frameIdx}`
        const leftCanvas = spriteCache.get(leftKey)
        if (leftCanvas) {
          spriteCache.set(`${agentId}_walk_right_${frameIdx}`, flipCanvasHorizontal(leftCanvas))
        }
      })
    }
  }

  // Build building sprites
  for (const [name, config] of Object.entries(BUILDING_CONFIGS)) {
    const featureFn = BUILDING_GENERATORS[name]
    if (name === 'village_square') {
      // Village square is special (no standard building shape)
      const canvas = document.createElement('canvas')
      canvas.width = BUILD_SIZE * SPRITE_SCALE
      canvas.height = BUILD_SIZE * SPRITE_SCALE
      const ctx = canvas.getContext('2d')
      ctx.imageSmoothingEnabled = false
      featureFn(ctx, SPRITE_SCALE, config.accent)
      buildingCache.set(name, canvas)
    } else {
      buildingCache.set(name, generateBuilding(config.base, config.roof, config.accent, featureFn))
    }
  }

  // Build terrain tiles
  for (const tileName of ['grass_0', 'grass_1', 'path']) {
    terrainCache.set(tileName, generateTerrainTile(tileName))
  }

  cacheBuilt = true
}

// ═══════════════════════════════════════════════════════════════
// PUBLIC API
// ═══════════════════════════════════════════════════════════════

function getSprite(agentName, animation, frameIndex) {
  const frames = CHAR_FRAMES[animation]
  const frameCount = animation === 'walk_right'
    ? (CHAR_FRAMES.walk_left?.length || 2)
    : (frames?.length || 2)
  const safeIndex = frameIndex % frameCount
  const key = `${agentName}_${animation}_${safeIndex}`
  return spriteCache.get(key) || spriteCache.get('CLAUDE_idle_0') || null
}

function getBuildingSprite(zoneName) {
  return buildingCache.get(zoneName) || null
}

function getTerrainTile(tileName) {
  return terrainCache.get(tileName) || null
}

export function usePixelSprites() {
  const spriteReady = ref(cacheBuilt)

  function init() {
    initSpriteCache()
    spriteReady.value = true
  }

  return {
    initSpriteCache: init,
    getSprite,
    getBuildingSprite,
    getTerrainTile,
    SPRITE_SCALE,
    spriteReady,
  }
}
