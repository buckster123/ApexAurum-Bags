/**
 * useVillageIsometric - Isometric 2.5D Village Scene
 *
 * Three.js isometric view of the Village with zone buildings and agent spheres.
 * Fixed camera angle like classic RPGs.
 *
 * Phase 5 Polish:
 * - Particle effects on tool completion (green=success, red=error)
 * - Click detection for agents and zones
 * - Speech bubbles for approval/input needed
 *
 * Phase 6: Pixel art billboard sprites from usePixelSprites system
 *
 * "Where agents walk between buildings in isometric splendor"
 */

import { ref, shallowRef, onMounted, onUnmounted } from 'vue'
import * as THREE from 'three'
import { usePixelSprites } from '@/composables/usePixelSprites'
import { useDraggableZones } from '@/composables/useDraggableZones'

// Polyfill for roundRect (not available in all browsers)
if (typeof CanvasRenderingContext2D !== 'undefined' && !CanvasRenderingContext2D.prototype.roundRect) {
  CanvasRenderingContext2D.prototype.roundRect = function(x, y, w, h, r) {
    if (w < 2 * r) r = w / 2
    if (h < 2 * r) r = h / 2
    this.moveTo(x + r, y)
    this.arcTo(x + w, y, x + w, y + h, r)
    this.arcTo(x + w, y + h, x, y + h, r)
    this.arcTo(x, y + h, x, y, r)
    this.arcTo(x, y, x + w, y, r)
    this.closePath()
    return this
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════

export const AGENT_COLORS = {
  AZOTH: '#FFD700',
  CLAUDE: '#00aaff',
  VAJRA: '#4FC3F7',
  ELYSIAN: '#ff69b4',
  KETHER: '#9370db',
  default: '#888888'
}

// Zone configurations with 3D positions
export const ZONES_3D = {
  village_square: {
    position: { x: 0, y: 0, z: 0 },
    size: { w: 8, h: 2, d: 8 },
    color: '#2d3436',
    label: 'Village Square'
  },
  dj_booth: {
    position: { x: -15, y: 0, z: 0 },
    size: { w: 5, h: 4, d: 4 },
    color: '#6c5ce7',
    label: 'DJ Booth'
  },
  memory_garden: {
    position: { x: 0, y: 0, z: -12 },
    size: { w: 7, h: 3, d: 4 },
    color: '#00b894',
    label: 'Memory Garden'
  },
  file_shed: {
    position: { x: 15, y: 0, z: 0 },
    size: { w: 5, h: 4, d: 4 },
    color: '#fdcb6e',
    label: 'File Shed'
  },
  workshop: {
    position: { x: 0, y: 0, z: 12 },
    size: { w: 6, h: 4, d: 4 },
    color: '#e17055',
    label: 'Workshop'
  },
  bridge_portal: {
    position: { x: 12, y: 0, z: -10 },
    size: { w: 5, h: 5, d: 4 },
    color: '#a29bfe',
    label: 'Bridge Portal'
  },
  library: {
    position: { x: -12, y: 0, z: -10 },
    size: { w: 5, h: 4, d: 4 },
    color: '#74b9ff',
    label: 'Library'
  },
  watchtower: {
    position: { x: -12, y: 0, z: 10 },
    size: { w: 4, h: 6, d: 4 },
    color: '#fd79a8',
    label: 'Watchtower'
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// PIXEL SPRITE -> THREE.JS TEXTURE BRIDGE
// ═══════════════════════════════════════════════════════════════════════════

function canvasToTexture(canvas) {
  if (!canvas) return null
  const texture = new THREE.CanvasTexture(canvas)
  texture.magFilter = THREE.NearestFilter
  texture.minFilter = THREE.NearestFilter
  texture.generateMipmaps = false
  return texture
}

function createBillboardSprite(canvas, width, height) {
  const texture = canvasToTexture(canvas)
  if (!texture) return null
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    alphaTest: 0.1,
    depthTest: true,
    depthWrite: false,
  })
  const sprite = new THREE.Sprite(material)
  sprite.scale.set(width, height, 1)
  return sprite
}

// ═══════════════════════════════════════════════════════════════════════════
// AGENT CLASS (3D)
// ═══════════════════════════════════════════════════════════════════════════

class Agent3D {
  constructor(id, scene, color, pixelSprites) {
    this.id = id
    this.color = color
    this.scene = scene
    this.pixelSprites = pixelSprites
    this.state = 'idle'
    this.currentZone = 'village_square'
    this.currentTool = null
    this.message = null
    this.targetPosition = new THREE.Vector3(0, 0, 0)

    // Animation state (mirrors 2D VillageCanvas Agent)
    this.facing = 'down'
    this.animFrame = 0
    this.animTimer = 0

    this.createMesh()
  }

  createMesh() {
    // Group holds sprite + glow ring + label
    this.group = new THREE.Group()
    this.group.userData = { type: 'agent', id: this.id }

    // Character sprite billboard (48x72 canvas -> ~3x4.5 world units)
    const WORLD_CHAR_W = 3
    const WORLD_CHAR_H = 4.5
    const idleCanvas = this.pixelSprites.getSprite(this.id, 'idle', 0)
    this.charSprite = createBillboardSprite(idleCanvas, WORLD_CHAR_W, WORLD_CHAR_H)
    if (this.charSprite) {
      this.charSprite.position.y = WORLD_CHAR_H / 2
      this.group.add(this.charSprite)
    }

    // Glow ring on ground (working state indicator)
    const ringGeometry = new THREE.RingGeometry(1.5, 2.0, 32)
    const ringMaterial = new THREE.MeshBasicMaterial({
      color: new THREE.Color(this.color),
      transparent: true,
      opacity: 0,
      side: THREE.DoubleSide
    })
    this.glowRing = new THREE.Mesh(ringGeometry, ringMaterial)
    this.glowRing.rotation.x = -Math.PI / 2
    this.glowRing.position.y = 0.05
    this.group.add(this.glowRing)

    // Name label
    this.createLabel()

    this.group.position.set(0, 0, 0)
    this.scene.add(this.group)
  }

  createLabel() {
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    canvas.width = 128
    canvas.height = 32
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 20px monospace'
    ctx.textAlign = 'center'
    ctx.shadowColor = '#000000'
    ctx.shadowBlur = 4
    ctx.fillText(this.id, 64, 22)

    const texture = new THREE.CanvasTexture(canvas)
    const material = new THREE.SpriteMaterial({ map: texture, transparent: true })
    this.label = new THREE.Sprite(material)
    this.label.scale.set(4, 1, 1)
    this.label.position.y = 5.5
    this.group.add(this.label)
  }

  updateSpriteTexture() {
    if (!this.charSprite || !this.pixelSprites) return

    let animation = 'idle'
    if (this.state === 'moving') {
      animation = `walk_${this.facing}`
    } else if (this.state === 'working') {
      animation = 'working'
    }

    const canvas = this.pixelSprites.getSprite(this.id, animation, this.animFrame)
    if (canvas) {
      const newTexture = canvasToTexture(canvas)
      if (newTexture) {
        if (this.charSprite.material.map) {
          this.charSprite.material.map.dispose()
        }
        this.charSprite.material.map = newTexture
        this.charSprite.material.needsUpdate = true
      }
    }
  }

  moveTo(zoneName) {
    const zone = ZONES_3D[zoneName]
    if (!zone) return
    this.currentZone = zoneName
    this.targetPosition.set(zone.position.x, 0, zone.position.z)
    this.state = 'moving'
  }

  startTool(toolName) {
    this.currentTool = toolName
    this.state = 'working'
    this.glowRing.material.opacity = 0.6
  }

  finishTool() {
    this.currentTool = null
    this.state = 'moving'
    this.glowRing.material.opacity = 0
    this.targetPosition.set(0, 0, 0)
    this.currentZone = 'village_square'
  }

  setMessage(msg) {
    this.message = msg
  }

  update(deltaTime) {
    const speed = 0.08
    const prevPos = this.group.position.clone()
    this.group.position.lerp(this.targetPosition, speed)

    // Determine facing from movement
    const dx = this.group.position.x - prevPos.x
    const dz = this.group.position.z - prevPos.z
    if (Math.abs(dx) > 0.01 || Math.abs(dz) > 0.01) {
      if (Math.abs(dx) > Math.abs(dz)) {
        this.facing = dx > 0 ? 'right' : 'left'
      } else {
        this.facing = dz > 0 ? 'down' : 'up'
      }
    }

    // Check if arrived
    if (this.group.position.distanceTo(this.targetPosition) < 0.1) {
      if (this.state === 'moving' && !this.currentTool) {
        this.state = 'idle'
      }
    }

    // Animation timer (ms-based, mirrors 2D Agent)
    this.animTimer += deltaTime * 1000
    if (this.state === 'moving') {
      if (this.animTimer >= 200) {
        this.animTimer = 0
        this.animFrame = (this.animFrame + 1) % 2
      }
    } else if (this.state === 'working') {
      if (this.animTimer >= 250) {
        this.animTimer = 0
        this.animFrame = (this.animFrame + 1) % 3
      }
      this.glowRing.rotation.z += 0.02
    } else {
      if (this.animTimer >= 600) {
        this.animTimer = 0
        this.animFrame = (this.animFrame + 1) % 2
      }
    }

    this.updateSpriteTexture()
  }

  // Backward compat: existing code accesses agent.mesh.position
  get mesh() {
    return this.group
  }

  dispose() {
    this.scene.remove(this.group)
    if (this.charSprite?.material?.map) this.charSprite.material.map.dispose()
    if (this.charSprite?.material) this.charSprite.material.dispose()
    if (this.glowRing) {
      this.glowRing.geometry.dispose()
      this.glowRing.material.dispose()
    }
    if (this.label?.material?.map) this.label.material.map.dispose()
    if (this.label?.material) this.label.material.dispose()
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// PARTICLE SYSTEM
// ═══════════════════════════════════════════════════════════════════════════

class ParticleSystem {
  constructor(scene) {
    this.scene = scene
    this.particleGroups = []
  }

  emit(position, color, count = 20, success = true) {
    const geometry = new THREE.BufferGeometry()
    const positions = new Float32Array(count * 3)
    const velocities = []
    const lifetimes = []

    // Initialize particles
    for (let i = 0; i < count; i++) {
      positions[i * 3] = position.x
      positions[i * 3 + 1] = position.y
      positions[i * 3 + 2] = position.z

      // Random velocity (burst outward)
      const theta = Math.random() * Math.PI * 2
      const phi = Math.random() * Math.PI - Math.PI / 2
      const speed = 0.1 + Math.random() * 0.2
      velocities.push({
        x: Math.cos(theta) * Math.cos(phi) * speed,
        y: Math.abs(Math.sin(phi) * speed) + 0.1, // Bias upward
        z: Math.sin(theta) * Math.cos(phi) * speed
      })
      lifetimes.push(1.0) // Full lifetime
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))

    const material = new THREE.PointsMaterial({
      color: new THREE.Color(color),
      size: success ? 0.4 : 0.3,
      transparent: true,
      opacity: 1,
      blending: THREE.AdditiveBlending,
      depthWrite: false
    })

    const particles = new THREE.Points(geometry, material)
    this.scene.add(particles)

    this.particleGroups.push({
      mesh: particles,
      velocities,
      lifetimes,
      age: 0,
      maxAge: 1.5
    })
  }

  emitSuccess(position) {
    this.emit(position, '#00ff88', 25, true)
    // Secondary sparkle
    setTimeout(() => this.emit(position, '#ffffff', 10, true), 100)
  }

  emitError(position) {
    this.emit(position, '#ff4444', 20, false)
    this.emit(position, '#ff8800', 10, false)
  }

  update(deltaTime) {
    for (let i = this.particleGroups.length - 1; i >= 0; i--) {
      const group = this.particleGroups[i]
      group.age += deltaTime

      if (group.age >= group.maxAge) {
        // Remove expired particles
        this.scene.remove(group.mesh)
        group.mesh.geometry.dispose()
        group.mesh.material.dispose()
        this.particleGroups.splice(i, 1)
        continue
      }

      // Update positions
      const positions = group.mesh.geometry.attributes.position.array
      const progress = group.age / group.maxAge

      for (let j = 0; j < group.velocities.length; j++) {
        const vel = group.velocities[j]
        positions[j * 3] += vel.x
        positions[j * 3 + 1] += vel.y - 0.01 * group.age // Gravity
        positions[j * 3 + 2] += vel.z
        group.lifetimes[j] -= deltaTime * 0.8
      }

      group.mesh.geometry.attributes.position.needsUpdate = true
      group.mesh.material.opacity = 1 - progress
    }
  }

  dispose() {
    for (const group of this.particleGroups) {
      this.scene.remove(group.mesh)
      group.mesh.geometry.dispose()
      group.mesh.material.dispose()
    }
    this.particleGroups = []
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// SPEECH BUBBLE
// ═══════════════════════════════════════════════════════════════════════════

class SpeechBubble {
  constructor(scene, position, message, type = 'info') {
    this.scene = scene
    this.message = message
    this.type = type
    this.age = 0
    this.maxAge = type === 'approval' ? 30 : 5 // Approval bubbles stay longer

    this.createMesh(position)
  }

  createMesh(position) {
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    canvas.width = 256
    canvas.height = 96

    // Background color based on type
    const bgColors = {
      info: 'rgba(40, 40, 60, 0.9)',
      approval: 'rgba(255, 200, 0, 0.95)',
      error: 'rgba(255, 60, 60, 0.9)',
      input: 'rgba(100, 100, 255, 0.9)'
    }

    const textColors = {
      info: '#ffffff',
      approval: '#000000',
      error: '#ffffff',
      input: '#ffffff'
    }

    // Draw bubble
    ctx.fillStyle = bgColors[this.type] || bgColors.info
    ctx.beginPath()
    ctx.roundRect(10, 10, 236, 66, 10)
    ctx.fill()

    // Draw pointer
    ctx.beginPath()
    ctx.moveTo(128 - 10, 76)
    ctx.lineTo(128, 96)
    ctx.lineTo(128 + 10, 76)
    ctx.fill()

    // Draw text
    ctx.fillStyle = textColors[this.type] || textColors.info
    ctx.font = 'bold 16px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'

    // Wrap text if needed
    const words = this.message.split(' ')
    let line = ''
    let y = 35
    const lineHeight = 20
    const maxWidth = 210

    for (const word of words) {
      const testLine = line + word + ' '
      if (ctx.measureText(testLine).width > maxWidth && line !== '') {
        ctx.fillText(line.trim(), 128, y)
        line = word + ' '
        y += lineHeight
      } else {
        line = testLine
      }
    }
    ctx.fillText(line.trim(), 128, y)

    // Icon for approval type
    if (this.type === 'approval') {
      ctx.font = '20px sans-serif'
      ctx.fillText('\u26a0\ufe0f', 30, 43)
    } else if (this.type === 'input') {
      ctx.font = '20px sans-serif'
      ctx.fillText('\u270f\ufe0f', 30, 43)
    }

    const texture = new THREE.CanvasTexture(canvas)
    const material = new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      depthTest: false
    })

    this.sprite = new THREE.Sprite(material)
    this.sprite.scale.set(6, 2.25, 1)
    this.sprite.position.set(position.x, position.y + 4, position.z)
    this.sprite.userData = { type: 'bubble', bubbleType: this.type }

    this.scene.add(this.sprite)
  }

  update(deltaTime, agentPosition) {
    this.age += deltaTime

    // Follow agent
    if (agentPosition) {
      this.sprite.position.x = agentPosition.x
      this.sprite.position.y = agentPosition.y + 4
      this.sprite.position.z = agentPosition.z
    }

    // Fade out near end (except approval which stays)
    if (this.type !== 'approval' && this.age > this.maxAge - 1) {
      this.sprite.material.opacity = this.maxAge - this.age
    }

    // Gentle bob
    this.sprite.position.y += Math.sin(this.age * 3) * 0.01

    return this.age < this.maxAge
  }

  dismiss() {
    this.age = this.maxAge
  }

  dispose() {
    this.scene.remove(this.sprite)
    this.sprite.material.map.dispose()
    this.sprite.material.dispose()
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// COMPOSABLE
// ═══════════════════════════════════════════════════════════════════════════

export function useVillageIsometric(containerRef, options = {}) {
  const isInitialized = ref(false)
  const activeZone = ref(null)
  const selectedAgent = shallowRef(null)
  const hoveredObject = shallowRef(null)
  const webglError = ref(null)

  let scene, camera, renderer
  let animationFrameId
  let zones = {}
  let agents = new Map()
  let clock
  let particleSystem
  let speechBubbles = []
  let raycaster
  let mouse

  // Pixel sprite system
  const { initSpriteCache, getSprite, getBuildingSprite, getTerrainTile, SPRITE_SCALE } = usePixelSprites()
  const pixelSprites = { getSprite, getBuildingSprite, getTerrainTile, SPRITE_SCALE }

  // Drag layout persistence
  const { loadLayout, saveLayout, resetLayout, hasCustomLayout } =
    useDraggableZones('village-layout-3d', ZONES_3D)

  // Store original default positions for reset
  const defaultPositions = {}
  for (const [name, config] of Object.entries(ZONES_3D)) {
    defaultPositions[name] = { x: config.position.x, z: config.position.z }
  }

  // Drag state for long-press-to-drag
  let dragState3D = null
  let groundMesh = null // Reference for ground rebuild

  function init() {
    if (!containerRef.value) return false

    const width = containerRef.value.clientWidth
    const height = containerRef.value.clientHeight

    // Guard against zero dimensions (can happen if container is hidden)
    if (width === 0 || height === 0) {
      console.warn('Village3D: Container has zero dimensions, skipping init')
      return false
    }

    // Check WebGL support first
    try {
      const canvas = document.createElement('canvas')
      const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl')
      if (!gl) {
        throw new Error('WebGL not supported')
      }
    } catch (e) {
      console.error('Village3D: WebGL not available:', e.message)
      webglError.value = 'WebGL is not available on this device. Please use 2D mode.'
      options.onWebGLError?.('WebGL not supported')
      return false
    }

    // Scene
    scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0a0a0f)

    // Orthographic camera for true isometric
    const aspect = width / height
    const frustumSize = 40
    camera = new THREE.OrthographicCamera(
      -frustumSize * aspect / 2,
      frustumSize * aspect / 2,
      frustumSize / 2,
      -frustumSize / 2,
      0.1,
      1000
    )

    // Isometric camera angle (45deg rotation, ~35deg tilt)
    camera.position.set(50, 50, 50)
    camera.lookAt(0, 0, 0)

    // Renderer - wrap in try/catch for WebGL context creation
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    } catch (e) {
      console.error('Village3D: Failed to create WebGL renderer:', e.message)
      webglError.value = 'Failed to create 3D renderer. Please use 2D mode.'
      options.onWebGLError?.(e.message)
      return false
    }

    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    containerRef.value.appendChild(renderer.domElement)

    // Lighting
    setupLighting()

    // Initialize pixel sprite cache
    initSpriteCache()

    // Ground plane
    createGround()

    // Zone buildings
    createZones()

    // Apply saved layout (move buildings to saved positions)
    const savedLayout = loadLayout()
    if (savedLayout?.zones) {
      for (const [name, pos] of Object.entries(savedLayout.zones)) {
        if (zones[name]?.mesh) {
          zones[name].mesh.position.set(pos.x, 0, pos.z)
          ZONES_3D[name].position.x = pos.x
          ZONES_3D[name].position.z = pos.z
        }
      }
      rebuildGround()
    }

    // Clock for animations
    clock = new THREE.Clock()

    // Particle system for effects
    particleSystem = new ParticleSystem(scene)

    // Raycaster for click detection
    raycaster = new THREE.Raycaster()
    mouse = new THREE.Vector2()

    // Add event listeners (mousedown/up for long-press drag)
    renderer.domElement.addEventListener('mousedown', handleMouseDown)
    renderer.domElement.addEventListener('mousemove', handleMouseMoveWithDrag)
    renderer.domElement.addEventListener('mouseup', handleMouseUp)
    renderer.domElement.addEventListener('mouseleave', handleMouseUp)
    renderer.domElement.addEventListener('touchstart', handleTouchStart)
    renderer.domElement.addEventListener('touchmove', handleTouchMove, { passive: false })
    renderer.domElement.addEventListener('touchend', handleTouchEnd)
    renderer.domElement.style.cursor = 'default'

    isInitialized.value = true
    return true
  }

  function setupLighting() {
    // Ambient light
    const ambient = new THREE.AmbientLight(0x404050, 0.6)
    scene.add(ambient)

    // Main directional light (sun)
    const sun = new THREE.DirectionalLight(0xffffff, 0.8)
    sun.position.set(30, 50, 30)
    sun.castShadow = true
    sun.shadow.mapSize.width = 2048
    sun.shadow.mapSize.height = 2048
    sun.shadow.camera.near = 0.5
    sun.shadow.camera.far = 150
    sun.shadow.camera.left = -40
    sun.shadow.camera.right = 40
    sun.shadow.camera.top = 40
    sun.shadow.camera.bottom = -40
    scene.add(sun)

    // Fill light
    const fill = new THREE.DirectionalLight(0x8080ff, 0.3)
    fill.position.set(-20, 20, -20)
    scene.add(fill)
  }

  function createGround() {
    const groundSize = 60

    // Composite terrain canvas with pixel art tiles
    const TILES_ACROSS = 20
    const tilePixels = 16 * pixelSprites.SPRITE_SCALE  // 48px per tile
    const canvasSize = TILES_ACROSS * tilePixels
    const terrainCanvas = document.createElement('canvas')
    terrainCanvas.width = canvasSize
    terrainCanvas.height = canvasSize
    const ctx = terrainCanvas.getContext('2d')
    ctx.imageSmoothingEnabled = false

    const tile0 = pixelSprites.getTerrainTile('grass_0')
    const tile1 = pixelSprites.getTerrainTile('grass_1')
    for (let y = 0; y < TILES_ACROSS; y++) {
      for (let x = 0; x < TILES_ACROSS; x++) {
        const tile = ((x + y) % 3 === 0) ? tile1 : tile0
        if (tile) ctx.drawImage(tile, x * tilePixels, y * tilePixels)
      }
    }

    // Draw dirt paths from village square to each zone
    const center = ZONES_3D.village_square.position
    const worldToUV = (wx, wz) => ({
      u: ((wx + groundSize / 2) / groundSize) * canvasSize,
      v: ((wz + groundSize / 2) / groundSize) * canvasSize,
    })

    const centerUV = worldToUV(center.x, center.z)
    ctx.strokeStyle = '#8b7355'
    ctx.lineWidth = 12
    ctx.lineCap = 'round'
    for (const [name, config] of Object.entries(ZONES_3D)) {
      if (name === 'village_square') continue
      const zoneUV = worldToUV(config.position.x, config.position.z)
      ctx.beginPath()
      ctx.moveTo(centerUV.u, centerUV.v)
      ctx.lineTo(zoneUV.u, zoneUV.v)
      ctx.stroke()
    }
    // Path border (darker)
    ctx.strokeStyle = '#6b5540'
    ctx.lineWidth = 16
    ctx.globalCompositeOperation = 'destination-over'
    for (const [name, config] of Object.entries(ZONES_3D)) {
      if (name === 'village_square') continue
      const zoneUV = worldToUV(config.position.x, config.position.z)
      ctx.beginPath()
      ctx.moveTo(centerUV.u, centerUV.v)
      ctx.lineTo(zoneUV.u, zoneUV.v)
      ctx.stroke()
    }
    ctx.globalCompositeOperation = 'source-over'

    const texture = new THREE.CanvasTexture(terrainCanvas)
    texture.magFilter = THREE.NearestFilter
    texture.minFilter = THREE.NearestFilter
    texture.generateMipmaps = false

    const groundGeometry = new THREE.PlaneGeometry(groundSize, groundSize)
    const groundMaterial = new THREE.MeshStandardMaterial({
      map: texture,
      roughness: 0.95,
      metalness: 0.0
    })
    const ground = new THREE.Mesh(groundGeometry, groundMaterial)
    ground.rotation.x = -Math.PI / 2
    ground.receiveShadow = true
    ground.userData = { type: 'ground' }
    scene.add(ground)
    groundMesh = ground
  }

  function rebuildGround() {
    // Remove old ground mesh
    if (groundMesh) {
      scene.remove(groundMesh)
      if (groundMesh.material.map) groundMesh.material.map.dispose()
      groundMesh.material.dispose()
      groundMesh.geometry.dispose()
      groundMesh = null
    }
    createGround()
  }

  function createZones() {
    for (const [name, config] of Object.entries(ZONES_3D)) {
      const zone = createZoneBuilding(name, config)
      zones[name] = zone
    }
  }

  function createZoneBuilding(name, config) {
    const { position, size, color, label } = config

    const buildingCanvas = pixelSprites.getBuildingSprite(name)
    const WORLD_BUILD_W = Math.max(size.w, 6)
    const WORLD_BUILD_H = Math.max(size.h, 6)

    let mesh
    let spriteMaterial = null

    if (buildingCanvas) {
      // Pixel art billboard
      mesh = new THREE.Group()
      const buildingSprite = createBillboardSprite(buildingCanvas, WORLD_BUILD_W, WORLD_BUILD_H)
      if (buildingSprite) {
        buildingSprite.position.y = WORLD_BUILD_H / 2
        mesh.add(buildingSprite)
        spriteMaterial = buildingSprite.material
      }
      mesh.position.set(position.x, 0, position.z)
    } else {
      // Fallback: colored box
      const geometry = new THREE.BoxGeometry(size.w, size.h, size.d)
      const material = new THREE.MeshStandardMaterial({
        color: new THREE.Color(color),
        emissive: new THREE.Color(color),
        emissiveIntensity: 0.15,
        roughness: 0.7,
        metalness: 0.1,
        transparent: true,
        opacity: 0.85
      })
      mesh = new THREE.Mesh(geometry, material)
      mesh.position.set(position.x, size.h / 2, position.z)
      mesh.castShadow = true
      mesh.receiveShadow = true
    }

    mesh.userData = { type: 'zone', name, label }
    scene.add(mesh)

    // Label above building
    const labelSprite = createLabelSprite(label)
    labelSprite.position.y = WORLD_BUILD_H + 1.0
    mesh.add(labelSprite)

    return { mesh, material: spriteMaterial || mesh.material, config }
  }

  function createLabelSprite(text) {
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    canvas.width = 256
    canvas.height = 64

    ctx.fillStyle = 'rgba(0,0,0,0.6)'
    ctx.fillRect(0, 0, 256, 64)

    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 24px monospace'
    ctx.textAlign = 'center'
    ctx.fillText(text, 128, 40)

    const texture = new THREE.CanvasTexture(canvas)
    const material = new THREE.SpriteMaterial({ map: texture, transparent: true })
    const sprite = new THREE.Sprite(material)
    sprite.scale.set(6, 1.5, 1)
    return sprite
  }

  function ensureAgent(agentId) {
    if (!agents.has(agentId)) {
      const color = AGENT_COLORS[agentId] || AGENT_COLORS.default
      const agent = new Agent3D(agentId, scene, color, pixelSprites)
      agents.set(agentId, agent)
    }
    return agents.get(agentId)
  }

  function setActiveZone(zoneName) {
    for (const [name, zone] of Object.entries(zones)) {
      const mat = zone.material
      if (mat && mat.isSpriteMaterial) {
        mat.opacity = (name === zoneName) ? 1.0 : 0.85
        mat.color.set(name === zoneName ? 0xffffff : 0xdddddd)
      } else if (mat && mat.emissiveIntensity !== undefined) {
        mat.emissiveIntensity = name === zoneName ? 0.4 : 0.15
      }
    }
    activeZone.value = zoneName
  }

  function handleToolStart(event) {
    const agent = ensureAgent(event.agent_id)
    agent.moveTo(event.zone)
    agent.startTool(event.tool)
    setActiveZone(event.zone)
  }

  function handleToolComplete(event) {
    const agent = agents.get(event.agent_id)
    if (agent) {
      // Emit particles at agent position
      const pos = agent.mesh.position.clone()
      if (event.success !== false) {
        particleSystem.emitSuccess(pos)
      } else {
        particleSystem.emitError(pos)
      }
      agent.finishTool()
    }
    setTimeout(() => setActiveZone(null), 500)
  }

  function handleToolError(event) {
    const agent = agents.get(event.agent_id)
    if (agent) {
      const pos = agent.mesh.position.clone()
      particleSystem.emitError(pos)
      agent.finishTool()

      // Show error bubble
      showBubble(event.agent_id, event.error || 'Error occurred', 'error')
    }
    setTimeout(() => setActiveZone(null), 500)
  }

  function showBubble(agentId, message, type = 'info') {
    const agent = agents.get(agentId)
    if (!agent) return

    // Remove existing bubble for this agent
    dismissBubble(agentId)

    const bubble = new SpeechBubble(scene, agent.mesh.position, message, type)
    bubble.agentId = agentId
    speechBubbles.push(bubble)

    return bubble
  }

  function showApprovalBubble(agentId, message) {
    return showBubble(agentId, message, 'approval')
  }

  function showInputBubble(agentId, message) {
    return showBubble(agentId, message, 'input')
  }

  function dismissBubble(agentId) {
    const idx = speechBubbles.findIndex(b => b.agentId === agentId)
    if (idx !== -1) {
      speechBubbles[idx].dismiss()
    }
  }

  function getMousePosition(event) {
    const rect = renderer.domElement.getBoundingClientRect()
    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  }

  function getIntersections() {
    raycaster.setFromCamera(mouse, camera)
    const objects = []

    // Collect agent meshes
    for (const agent of agents.values()) {
      objects.push(agent.mesh)
    }

    // Collect zone meshes
    for (const zone of Object.values(zones)) {
      objects.push(zone.mesh)
    }

    return raycaster.intersectObjects(objects, true)
  }

  function handleNormalClick(event) {
    getMousePosition(event)
    const intersections = getIntersections()

    if (intersections.length > 0) {
      let hit = intersections[0].object
      // Walk up parent chain to find object with userData.type
      while (hit && !hit.userData?.type) {
        hit = hit.parent
      }
      if (hit) {
        const userData = hit.userData
        if (userData.type === 'agent') {
          selectedAgent.value = userData.id
          options.onAgentClick?.(userData.id, agents.get(userData.id))
        } else if (userData.type === 'zone') {
          options.onZoneClick?.(userData.name, userData.label)
        }
      }
    } else {
      selectedAgent.value = null
    }
  }

  function handleHover(event) {
    getMousePosition(event)
    const intersections = getIntersections()

    if (intersections.length > 0) {
      let hit = intersections[0].object
      while (hit && !hit.userData?.type) {
        hit = hit.parent
      }
      if (hit && (hit.userData?.type === 'agent' || hit.userData?.type === 'zone')) {
        hoveredObject.value = hit.userData
        renderer.domElement.style.cursor = 'pointer'
        return
      }
    }
    hoveredObject.value = null
    renderer.domElement.style.cursor = 'default'
  }

  // ── Long-press drag handlers (3D) ──

  function findZoneHit(intersections) {
    for (const inter of intersections) {
      let obj = inter.object
      while (obj && !obj.userData?.type) obj = obj.parent
      if (obj?.userData?.type === 'zone') return obj.userData
    }
    return null
  }

  function handleMouseDown(event) {
    const clientX = event.touches ? event.touches[0].clientX : event.clientX
    const clientY = event.touches ? event.touches[0].clientY : event.clientY

    getMousePosition(event.touches ? event.touches[0] : event)
    const intersections = getIntersections()
    const hit = findZoneHit(intersections)
    if (!hit) return

    dragState3D = {
      zoneName: hit.name,
      startMouse: { x: clientX, y: clientY },
      isDragging: false,
      timer: setTimeout(() => {
        if (dragState3D) {
          dragState3D.isDragging = true
          renderer.domElement.style.cursor = 'grabbing'
        }
      }, 500)
    }
  }

  function handleMouseMoveWithDrag(event) {
    const clientX = event.touches ? event.touches[0].clientX : event.clientX
    const clientY = event.touches ? event.touches[0].clientY : event.clientY

    if (dragState3D?.isDragging) {
      if (event.touches) event.preventDefault()

      // Raycast to ground plane (y=0) for new position
      getMousePosition(event.touches ? event.touches[0] : event)
      raycaster.setFromCamera(mouse, camera)
      const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0)
      const intersectPoint = new THREE.Vector3()
      raycaster.ray.intersectPlane(groundPlane, intersectPoint)

      if (intersectPoint) {
        // Clamp to ground bounds (+-28 to stay visible)
        const clampedX = Math.max(-28, Math.min(28, intersectPoint.x))
        const clampedZ = Math.max(-28, Math.min(28, intersectPoint.z))

        const zone = zones[dragState3D.zoneName]
        if (zone?.mesh) {
          zone.mesh.position.set(clampedX, 0, clampedZ)
          ZONES_3D[dragState3D.zoneName].position.x = clampedX
          ZONES_3D[dragState3D.zoneName].position.z = clampedZ
        }
      }
      return
    }

    // Cancel long press if moved too far
    if (dragState3D && !dragState3D.isDragging) {
      const dist = Math.hypot(
        clientX - dragState3D.startMouse.x,
        clientY - dragState3D.startMouse.y
      )
      if (dist > 5) {
        clearTimeout(dragState3D.timer)
        dragState3D = null
      }
    }

    // Normal hover behavior
    handleHover(event)
  }

  function handleMouseUp(event) {
    if (!dragState3D) return
    clearTimeout(dragState3D.timer)

    if (dragState3D.isDragging) {
      // Save layout
      const layout = {}
      for (const [name, config] of Object.entries(ZONES_3D)) {
        layout[name] = { x: config.position.x, z: config.position.z }
      }
      saveLayout(layout)
      rebuildGround()
      renderer.domElement.style.cursor = 'default'
      dragState3D = null
      return
    }

    dragState3D = null
    handleNormalClick(event)
  }

  // Touch wrappers
  function handleTouchStart(event) { handleMouseDown(event) }
  function handleTouchMove(event) { handleMouseMoveWithDrag(event) }
  function handleTouchEnd(event) { handleMouseUp(event) }

  function animate() {
    if (!isInitialized.value) return

    const deltaTime = clock.getDelta()

    // Update all agents
    for (const agent of agents.values()) {
      agent.update(deltaTime)
    }

    // Update particle system
    if (particleSystem) {
      particleSystem.update(deltaTime)
    }

    // Update speech bubbles
    for (let i = speechBubbles.length - 1; i >= 0; i--) {
      const bubble = speechBubbles[i]
      const agent = agents.get(bubble.agentId)
      const agentPos = agent ? agent.mesh.position : null

      if (!bubble.update(deltaTime, agentPos)) {
        bubble.dispose()
        speechBubbles.splice(i, 1)
      }
    }

    renderer.render(scene, camera)
    animationFrameId = requestAnimationFrame(animate)
  }

  function onResize() {
    if (!containerRef.value || !camera || !renderer) return

    const width = containerRef.value.clientWidth
    const height = containerRef.value.clientHeight
    const aspect = width / height
    const frustumSize = 40

    camera.left = -frustumSize * aspect / 2
    camera.right = frustumSize * aspect / 2
    camera.top = frustumSize / 2
    camera.bottom = -frustumSize / 2
    camera.updateProjectionMatrix()

    renderer.setSize(width, height)
  }

  function dispose() {
    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId)
    }

    // Remove event listeners
    if (renderer?.domElement) {
      renderer.domElement.removeEventListener('mousedown', handleMouseDown)
      renderer.domElement.removeEventListener('mousemove', handleMouseMoveWithDrag)
      renderer.domElement.removeEventListener('mouseup', handleMouseUp)
      renderer.domElement.removeEventListener('mouseleave', handleMouseUp)
      renderer.domElement.removeEventListener('touchstart', handleTouchStart)
      renderer.domElement.removeEventListener('touchmove', handleTouchMove)
      renderer.domElement.removeEventListener('touchend', handleTouchEnd)
    }

    // Dispose agents
    for (const agent of agents.values()) {
      agent.dispose()
    }
    agents.clear()

    // Dispose particles
    if (particleSystem) {
      particleSystem.dispose()
    }

    // Dispose speech bubbles
    for (const bubble of speechBubbles) {
      bubble.dispose()
    }
    speechBubbles = []

    if (renderer) {
      renderer.dispose()
      if (containerRef.value && renderer.domElement) {
        containerRef.value.removeChild(renderer.domElement)
      }
    }

    isInitialized.value = false
  }

  onMounted(() => {
    if (init()) {
      animate()
      window.addEventListener('resize', onResize)
    }
  })

  onUnmounted(() => {
    window.removeEventListener('resize', onResize)
    dispose()
  })

  return {
    isInitialized,
    activeZone,
    selectedAgent,
    hoveredObject,
    webglError,
    agents,
    ensureAgent,
    handleToolStart,
    handleToolComplete,
    handleToolError,
    setActiveZone,
    showBubble,
    showApprovalBubble,
    showInputBubble,
    dismissBubble,
    dispose,
    hasCustomLayout,
    resetLayout: () => {
      resetLayout()
      // Restore default positions
      for (const [name, pos] of Object.entries(defaultPositions)) {
        ZONES_3D[name].position.x = pos.x
        ZONES_3D[name].position.z = pos.z
        if (zones[name]?.mesh) {
          zones[name].mesh.position.set(pos.x, 0, pos.z)
        }
      }
      rebuildGround()
    },
    ZONES_3D,
    AGENT_COLORS
  }
}
