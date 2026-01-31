import * as THREE from 'three'

const NEURAL_COLORS = [
  new THREE.Color('#4FC3F7'),  // Cyan (VAJRA)
  new THREE.Color('#FFD700'),  // Gold (AZOTH)
  new THREE.Color('#E8B4FF'),  // Lilac (ELYSIAN)
]

export class NeuralAmbientSystem {
  constructor(scene) {
    if (!scene) return

    this.scene = scene
    this.group = new THREE.Group()
    this.group.name = 'ambientSystem'
    this.scene.add(this.group)

    // Internal state
    this.elapsed = 0
    this.pulseTimer = 0
    this.pulseInterval = 0.5 + Math.random() * 1.5
    this.waveTimer = 0
    this.waveInterval = 5 + Math.random() * 5
    this.hasRealMemories = false

    this.ghostNodes = []
    this.synapticPulses = []
    this.radialWaves = []
    this.particles = null
    this.particleVelocities = []

    this._initGhostNodes()
    this._initAmbientParticles()
  }

  // ---------------------------------------------------------------
  // 1. Ghost Nodes (40 dim spheres sharing one geometry)
  // ---------------------------------------------------------------
  _initGhostNodes() {
    const sharedGeometry = new THREE.SphereGeometry(0.3, 8, 8)
    this._ghostGeometry = sharedGeometry

    for (let i = 0; i < 40; i++) {
      const baseOpacity = 0.08 + Math.random() * 0.12
      const color = NEURAL_COLORS[Math.floor(Math.random() * NEURAL_COLORS.length)]

      const material = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: baseOpacity,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      })

      const mesh = new THREE.Mesh(sharedGeometry, material)

      // Random position in spherical shell radius 10-70, Y offset -10
      const radius = 10 + Math.random() * 60
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      mesh.position.set(
        radius * Math.sin(phi) * Math.cos(theta),
        radius * Math.sin(phi) * Math.sin(theta) - 10,
        radius * Math.cos(phi)
      )

      mesh.userData = {
        baseOpacity,
        phaseOffset: Math.random() * Math.PI * 2,
        pulseSpeed: 0.5 + Math.random() * 1.5,
      }

      this.group.add(mesh)
      this.ghostNodes.push(mesh)
    }
  }

  _updateGhostNodes() {
    const intensity = this.hasRealMemories ? 0.3 : 1.0

    for (let i = 0; i < this.ghostNodes.length; i++) {
      const node = this.ghostNodes[i]
      const { baseOpacity, phaseOffset, pulseSpeed } = node.userData
      node.material.opacity =
        baseOpacity *
        (0.5 + 0.5 * Math.sin(this.elapsed * pulseSpeed + phaseOffset)) *
        intensity
    }
  }

  // ---------------------------------------------------------------
  // 2. Synaptic Pulses (spawned periodically between ghost nodes)
  // ---------------------------------------------------------------
  _spawnSynapticPulse() {
    if (this.ghostNodes.length < 2) return

    // Pick 2 different random ghost nodes
    const idxA = Math.floor(Math.random() * this.ghostNodes.length)
    let idxB = Math.floor(Math.random() * (this.ghostNodes.length - 1))
    if (idxB >= idxA) idxB++

    const startPos = this.ghostNodes[idxA].position.clone()
    const endPos = this.ghostNodes[idxB].position.clone()
    const color = NEURAL_COLORS[Math.floor(Math.random() * NEURAL_COLORS.length)]

    // Faint line between the two positions
    const lineGeometry = new THREE.BufferGeometry().setFromPoints([startPos, endPos])
    const lineMaterial = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: 0.15,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
    const line = new THREE.Line(lineGeometry, lineMaterial)
    this.group.add(line)

    // Bright pulse sphere
    const pulseGeometry = new THREE.SphereGeometry(0.5, 8, 8)
    const pulseMaterial = new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: 0.8,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
    const pulse = new THREE.Mesh(pulseGeometry, pulseMaterial)
    pulse.position.copy(startPos)
    this.group.add(pulse)

    // 3 trailing spheres with decreasing size and opacity
    const trailSizes = [0.3, 0.22, 0.15]
    const trailOpacities = [0.5, 0.35, 0.20]
    const trail = []

    for (let i = 0; i < 3; i++) {
      const trailGeometry = new THREE.SphereGeometry(trailSizes[i], 8, 8)
      const trailMaterial = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: trailOpacities[i],
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      })
      const trailMesh = new THREE.Mesh(trailGeometry, trailMaterial)
      trailMesh.position.copy(startPos)
      this.group.add(trailMesh)
      trail.push({
        mesh: trailMesh,
        baseOpacity: trailOpacities[i],
      })
    }

    // Calculate travel duration based on distance
    const distance = startPos.distanceTo(endPos)
    const travelDuration = Math.max(0.5, distance / 60)

    this.synapticPulses.push({
      line,
      lineGeometry,
      lineMaterial,
      pulse,
      pulseGeometry,
      pulseMaterial,
      trail,
      startPos,
      endPos,
      age: 0,
      maxAge: 2.0,
      travelDuration,
      basePulseOpacity: 0.8,
    })
  }

  _updateSynapticPulses(dt) {
    for (let i = this.synapticPulses.length - 1; i >= 0; i--) {
      const p = this.synapticPulses[i]
      p.age += dt

      if (p.age >= p.maxAge) {
        // Remove and dispose
        this._disposeSynapticPulse(p)
        this.synapticPulses.splice(i, 1)
        continue
      }

      const progress = Math.min(p.age / p.travelDuration, 1.0)

      // Position the main pulse along the path
      p.pulse.position.lerpVectors(p.startPos, p.endPos, progress)

      // Position trail spheres with delay offsets
      const trailDelays = [0.08, 0.16, 0.24]
      for (let t = 0; t < p.trail.length; t++) {
        const trailProgress = Math.max(0, Math.min(progress - trailDelays[t], 1.0))
        p.trail[t].mesh.position.lerpVectors(p.startPos, p.endPos, trailProgress)
      }

      // After arrival: fade everything out
      if (progress >= 1.0) {
        const fadeProgress = (p.age - p.travelDuration) / (p.maxAge - p.travelDuration)
        const fadeFactor = Math.max(0, 1.0 - fadeProgress)

        p.pulseMaterial.opacity = p.basePulseOpacity * fadeFactor
        p.lineMaterial.opacity = 0.15 * fadeFactor

        for (let t = 0; t < p.trail.length; t++) {
          p.trail[t].mesh.material.opacity = p.trail[t].baseOpacity * fadeFactor
        }
      }
    }
  }

  _disposeSynapticPulse(p) {
    this.group.remove(p.line)
    this.group.remove(p.pulse)
    p.lineGeometry.dispose()
    p.lineMaterial.dispose()
    p.pulseGeometry.dispose()
    p.pulseMaterial.dispose()

    for (let t = 0; t < p.trail.length; t++) {
      this.group.remove(p.trail[t].mesh)
      p.trail[t].mesh.geometry.dispose()
      p.trail[t].mesh.material.dispose()
    }
  }

  // ---------------------------------------------------------------
  // 3. Radial Pulse Waves (expanding ring, spawned every 5-10s)
  // ---------------------------------------------------------------
  _spawnRadialWave() {
    const geometry = new THREE.RingGeometry(0.5, 1.0, 32)
    const color = NEURAL_COLORS[Math.floor(Math.random() * NEURAL_COLORS.length)]
    const material = new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: 0.4,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })

    const mesh = new THREE.Mesh(geometry, material)
    mesh.position.set(0, -10, 0)
    mesh.rotation.x = Math.random() * Math.PI * 2
    mesh.rotation.y = Math.random() * Math.PI * 2
    this.group.add(mesh)

    this.radialWaves.push({
      mesh,
      geometry,
      material,
      age: 0,
      maxAge: 3.0,
      maxScale: 80,
    })
  }

  _updateRadialWaves(dt) {
    for (let i = this.radialWaves.length - 1; i >= 0; i--) {
      const w = this.radialWaves[i]
      w.age += dt

      if (w.age >= w.maxAge) {
        this.group.remove(w.mesh)
        w.geometry.dispose()
        w.material.dispose()
        this.radialWaves.splice(i, 1)
        continue
      }

      const progress = w.age / w.maxAge
      const scale = progress * w.maxScale
      w.mesh.scale.set(scale, scale, scale)
      w.material.opacity = 0.4 * (1.0 - progress)
    }
  }

  // ---------------------------------------------------------------
  // 4. Ambient Particles (150 constant drifting points)
  // ---------------------------------------------------------------
  _initAmbientParticles() {
    const count = 150
    const positions = new Float32Array(count * 3)
    this.particleVelocities = []

    for (let i = 0; i < count; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 140       // x: -70 to 70
      positions[i * 3 + 1] = (Math.random() - 0.5) * 140 - 10  // y: -70 to 70, offset -10
      positions[i * 3 + 2] = (Math.random() - 0.5) * 140   // z: -70 to 70

      this.particleVelocities.push({
        x: (Math.random() - 0.5) * 0.04,  // -0.02 to 0.02
        y: (Math.random() - 0.5) * 0.04,
        z: (Math.random() - 0.5) * 0.04,
      })
    }

    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))

    const material = new THREE.PointsMaterial({
      color: 0x4FC3F7,
      size: 0.3,
      transparent: true,
      opacity: 0.15,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })

    this.particles = new THREE.Points(geometry, material)
    this._particleGeometry = geometry
    this._particleMaterial = material
    this.group.add(this.particles)
  }

  _updateAmbientParticles() {
    if (!this.particles) return

    const positions = this.particles.geometry.attributes.position.array
    const count = positions.length / 3

    for (let i = 0; i < count; i++) {
      const v = this.particleVelocities[i]
      let x = positions[i * 3] + v.x
      let y = positions[i * 3 + 1] + v.y
      let z = positions[i * 3 + 2] + v.z

      // Wrap around bounds
      if (x > 70) x = -70
      else if (x < -70) x = 70
      if (y > 60) y = -80          // account for -10 offset: 70 - 10 = 60, -70 - 10 = -80
      else if (y < -80) y = 60
      if (z > 70) z = -70
      else if (z < -70) z = 70

      positions[i * 3] = x
      positions[i * 3 + 1] = y
      positions[i * 3 + 2] = z
    }

    this.particles.geometry.attributes.position.needsUpdate = true
  }

  // ---------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------
  update(deltaTime) {
    if (!this.group) return

    // Clamp delta time to prevent spawn explosion after tab backgrounding
    const dt = deltaTime > 0.1 ? 0.016 : deltaTime
    this.elapsed += dt

    // Update ghost nodes
    this._updateGhostNodes()

    // Synaptic pulse spawning
    this.pulseTimer += dt
    if (this.pulseTimer >= this.pulseInterval) {
      this.pulseTimer = 0
      this.pulseInterval = 0.5 + Math.random() * 1.5
      this._spawnSynapticPulse()
    }
    this._updateSynapticPulses(dt)

    // Radial wave spawning
    this.waveTimer += dt
    if (this.waveTimer >= this.waveInterval) {
      this.waveTimer = 0
      this.waveInterval = 5 + Math.random() * 5
      this._spawnRadialWave()
    }
    this._updateRadialWaves(dt)

    // Ambient particles
    this._updateAmbientParticles()
  }

  setHasRealMemories(hasMemories) {
    this.hasRealMemories = !!hasMemories
  }

  dispose() {
    if (!this.group) return

    // Dispose ghost nodes
    if (this._ghostGeometry) {
      this._ghostGeometry.dispose()
    }
    for (const node of this.ghostNodes) {
      node.material.dispose()
      this.group.remove(node)
    }
    this.ghostNodes = []

    // Dispose synaptic pulses
    for (const p of this.synapticPulses) {
      this._disposeSynapticPulse(p)
    }
    this.synapticPulses = []

    // Dispose radial waves
    for (const w of this.radialWaves) {
      this.group.remove(w.mesh)
      w.geometry.dispose()
      w.material.dispose()
    }
    this.radialWaves = []

    // Dispose ambient particles
    if (this._particleGeometry) {
      this._particleGeometry.dispose()
    }
    if (this._particleMaterial) {
      this._particleMaterial.dispose()
    }
    if (this.particles) {
      this.group.remove(this.particles)
    }
    this.particles = null
    this.particleVelocities = []

    // Remove group from scene
    if (this.scene) {
      this.scene.remove(this.group)
    }
    this.group = null
    this.scene = null
  }
}
