/**
 * useThreeScene - Three.js Scene Composable
 *
 * Manages a Three.js scene with camera, renderer, and controls.
 * "The canvas of the neural cosmos"
 */

import { ref, shallowRef, onMounted, onUnmounted, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'

/**
 * Check if WebGL is available in this browser/device
 */
export function isWebGLAvailable() {
  try {
    const canvas = document.createElement('canvas')
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
    )
  } catch (e) {
    return false
  }
}

/**
 * Check if WebGL2 is available
 */
export function isWebGL2Available() {
  try {
    const canvas = document.createElement('canvas')
    return !!(window.WebGL2RenderingContext && canvas.getContext('webgl2'))
  } catch (e) {
    return false
  }
}

export function useThreeScene(containerRef, options = {}) {
  const {
    backgroundColor = 0x0a0a0f,
    cameraPosition = [0, 50, 100],
    enableOrbit = true,
    autoRotate = false,
    autoRotateSpeed = 0.5,
  } = options

  // Three.js objects - use shallowRef to avoid Vue Proxy conflicts
  // Vue's deep reactivity wraps objects in Proxies, but Three.js has
  // non-configurable properties (modelViewMatrix, etc.) that break under proxy
  const scene = shallowRef(null)
  const camera = shallowRef(null)
  const renderer = shallowRef(null)
  const controls = shallowRef(null)

  // State
  const isInitialized = ref(false)
  const animationFrameId = ref(null)

  // External animation callbacks (for ambient systems, effects, etc.)
  const animationCallbacks = []
  let lastTime = 0

  function addAnimationCallback(fn) {
    animationCallbacks.push(fn)
    return () => {
      const idx = animationCallbacks.indexOf(fn)
      if (idx !== -1) animationCallbacks.splice(idx, 1)
    }
  }

  // Raycaster for mouse picking
  const raycaster = new THREE.Raycaster()
  const mouse = new THREE.Vector2()

  // Initialize the scene
  function init() {
    if (!containerRef.value) return false

    // Safety check for WebGL before trying to create renderer
    if (!isWebGLAvailable()) {
      console.warn('useThreeScene: WebGL not available, skipping initialization')
      return false
    }

    try {
      const width = containerRef.value.clientWidth
      const height = containerRef.value.clientHeight

      // Scene
      scene.value = new THREE.Scene()
      scene.value.background = new THREE.Color(backgroundColor)
      scene.value.fog = new THREE.FogExp2(backgroundColor, 0.008)

      // Camera
      camera.value = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000)
      camera.value.position.set(...cameraPosition)

      // Renderer
      renderer.value = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
      })
      renderer.value.setSize(width, height)
      renderer.value.setPixelRatio(Math.min(window.devicePixelRatio, 2))
      containerRef.value.appendChild(renderer.value.domElement)

      // Controls
      if (enableOrbit) {
        controls.value = new OrbitControls(camera.value, renderer.value.domElement)
        controls.value.enableDamping = true
        controls.value.dampingFactor = 0.05
        controls.value.autoRotate = autoRotate
        controls.value.autoRotateSpeed = autoRotateSpeed
        controls.value.minDistance = 20
        controls.value.maxDistance = 200
      }

      // Ambient light
      const ambientLight = new THREE.AmbientLight(0x404040, 0.5)
      scene.value.add(ambientLight)

      // Point light at center
      const pointLight = new THREE.PointLight(0xffffff, 1, 200)
      pointLight.position.set(0, 0, 0)
      scene.value.add(pointLight)

      // Add subtle grid helper
      const gridHelper = new THREE.GridHelper(200, 40, 0x1a1a2e, 0x1a1a2e)
      gridHelper.position.y = -30
      scene.value.add(gridHelper)

      isInitialized.value = true
      return true
    } catch (e) {
      console.error('useThreeScene: Failed to initialize WebGL:', e)
      return false
    }
  }

  // Animation loop
  function animate(time = 0) {
    if (!isInitialized.value) return

    animationFrameId.value = requestAnimationFrame(animate)

    // Calculate delta time in seconds (clamped to prevent explosion after tab switch)
    const deltaTime = lastTime ? Math.min((time - lastTime) / 1000, 0.1) : 0.016
    lastTime = time

    // Run external animation callbacks
    for (const cb of animationCallbacks) {
      cb(deltaTime)
    }

    if (controls.value) {
      controls.value.update()
    }

    if (renderer.value && scene.value && camera.value) {
      renderer.value.render(scene.value, camera.value)
    }
  }

  // Handle resize
  function onResize() {
    if (!containerRef.value || !camera.value || !renderer.value) return

    const width = containerRef.value.clientWidth
    const height = containerRef.value.clientHeight

    camera.value.aspect = width / height
    camera.value.updateProjectionMatrix()
    renderer.value.setSize(width, height)
  }

  // Get object at mouse position
  function getObjectAtMouse(event, objects) {
    if (!containerRef.value || !camera.value) return null

    const rect = containerRef.value.getBoundingClientRect()
    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1

    raycaster.setFromCamera(mouse, camera.value)
    const intersects = raycaster.intersectObjects(objects, true)

    return intersects.length > 0 ? intersects[0] : null
  }

  // Focus camera on position
  function focusOn(position, duration = 1000) {
    if (!camera.value || !controls.value) return

    const targetPosition = new THREE.Vector3(...position)
    const startPosition = camera.value.position.clone()

    // Calculate new camera position (offset from target)
    const direction = startPosition.clone().sub(targetPosition).normalize()
    const distance = 40
    const endPosition = targetPosition.clone().add(direction.multiplyScalar(distance))

    const startTime = Date.now()

    function animateFocus() {
      const elapsed = Date.now() - startTime
      const progress = Math.min(elapsed / duration, 1)
      const eased = easeOutCubic(progress)

      camera.value.position.lerpVectors(startPosition, endPosition, eased)
      controls.value.target.lerp(targetPosition, eased)
      controls.value.update()

      if (progress < 1) {
        requestAnimationFrame(animateFocus)
      }
    }

    animateFocus()
  }

  // Easing function
  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3)
  }

  // Set auto rotate
  function setAutoRotate(enabled) {
    if (controls.value) {
      controls.value.autoRotate = enabled
    }
  }

  // Clean up
  function dispose() {
    animationCallbacks.length = 0
    lastTime = 0

    if (animationFrameId.value) {
      cancelAnimationFrame(animationFrameId.value)
    }

    if (renderer.value) {
      renderer.value.dispose()
      if (containerRef.value && renderer.value.domElement) {
        containerRef.value.removeChild(renderer.value.domElement)
      }
    }

    if (controls.value) {
      controls.value.dispose()
    }

    if (scene.value) {
      scene.value.traverse((object) => {
        if (object.geometry) object.geometry.dispose()
        if (object.material) {
          if (Array.isArray(object.material)) {
            object.material.forEach(m => m.dispose())
          } else {
            object.material.dispose()
          }
        }
      })
    }

    isInitialized.value = false
  }

  // Lifecycle
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
    scene,
    camera,
    renderer,
    controls,
    isInitialized,
    init,
    dispose,
    onResize,
    getObjectAtMouse,
    focusOn,
    setAutoRotate,
    addAnimationCallback,
  }
}

/**
 * Create a glowing memory node
 */
export function createMemoryNode(memory, agentColors, layerConfig) {
  const agent = memory.agent_id || 'CLAUDE'
  const layer = memory.layer || 'working'

  const colorInfo = agentColors[agent] || agentColors.CLAUDE
  const layerInfo = layerConfig[layer] || layerConfig.working

  // Base size from attention weight
  const baseSize = 0.5 + (memory.attention_weight || 1.0) * 1.5

  // Create geometry
  const geometry = new THREE.SphereGeometry(baseSize, 16, 16)

  // Create material with glow effect
  const material = new THREE.MeshStandardMaterial({
    color: new THREE.Color(colorInfo.hex),
    emissive: new THREE.Color(colorInfo.glow),
    emissiveIntensity: layerInfo.brightness * 0.5,
    metalness: 0.3,
    roughness: 0.4,
    transparent: true,
    opacity: layerInfo.brightness,
  })

  const mesh = new THREE.Mesh(geometry, material)

  // Position based on layer
  const [minR, maxR] = layerInfo.radius
  const r = minR + Math.random() * (maxR - minR)
  const theta = Math.random() * Math.PI * 2
  const phi = Math.acos(2 * Math.random() - 1)

  mesh.position.set(
    r * Math.sin(phi) * Math.cos(theta),
    r * Math.sin(phi) * Math.sin(theta) - 10, // Offset down slightly
    r * Math.cos(phi)
  )

  // Store memory data
  mesh.userData = { memory, type: 'memory-node' }

  return mesh
}

/**
 * Create connection line between nodes
 */
export function createConnectionLine(startPos, endPos, type = 'responding_to') {
  const colors = {
    responding_to: 0x4fc3f7, // Blue
    thread: 0xffd700, // Gold
    related_agent: 0xe8b4ff, // Lilac
  }

  const material = new THREE.LineBasicMaterial({
    color: colors[type] || 0x888888,
    transparent: true,
    opacity: 0.3,
  })

  const points = [
    new THREE.Vector3(...startPos),
    new THREE.Vector3(...endPos),
  ]

  const geometry = new THREE.BufferGeometry().setFromPoints(points)
  const line = new THREE.Line(geometry, material)

  return line
}
