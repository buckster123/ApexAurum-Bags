/**
 * useVillage - Village GUI Composable
 *
 * Manages WebSocket connection, agents, zones, and Canvas rendering
 * for the Village visualization.
 *
 * "Where agents walk and tools come alive"
 */

import { ref, reactive, onMounted, onUnmounted } from 'vue'

// ═══════════════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════

export const CANVAS_WIDTH = 800
export const CANVAS_HEIGHT = 600

export const ZONES = {
  village_square: {
    x: 400, y: 300,
    width: 120, height: 120,
    color: '#2d3436',
    label: 'Village Square'
  },
  dj_booth: {
    x: 100, y: 300,
    width: 100, height: 80,
    color: '#6c5ce7',
    label: 'DJ Booth'
  },
  memory_garden: {
    x: 400, y: 80,
    width: 140, height: 80,
    color: '#00b894',
    label: 'Memory Garden'
  },
  file_shed: {
    x: 700, y: 300,
    width: 100, height: 80,
    color: '#fdcb6e',
    label: 'File Shed'
  },
  workshop: {
    x: 400, y: 520,
    width: 120, height: 80,
    color: '#e17055',
    label: 'Workshop'
  },
  bridge_portal: {
    x: 700, y: 80,
    width: 100, height: 80,
    color: '#a29bfe',
    label: 'Bridge Portal'
  },
  library: {
    x: 100, y: 80,
    width: 100, height: 80,
    color: '#74b9ff',
    label: 'Library'
  },
  watchtower: {
    x: 100, y: 520,
    width: 100, height: 80,
    color: '#fd79a8',
    label: 'Watchtower'
  }
}

export const AGENT_COLORS = {
  AZOTH: '#FFD700',
  CLAUDE: '#00aaff',
  VAJRA: '#4FC3F7',
  ELYSIAN: '#ff69b4',
  KETHER: '#9370db',
  default: '#888888'
}

// ═══════════════════════════════════════════════════════════════════════════
// AGENT CLASS
// ═══════════════════════════════════════════════════════════════════════════

class Agent {
  constructor(id, name, color = '#00aaff') {
    this.id = id
    this.name = name
    this.color = color
    this.radius = 20

    // Position (start at village square)
    this.x = ZONES.village_square.x
    this.y = ZONES.village_square.y
    this.targetX = this.x
    this.targetY = this.y

    // State
    this.state = 'idle' // idle, moving, working
    this.currentZone = 'village_square'
    this.currentTool = null
    this.message = null // For speech bubbles

    // Animation
    this.moveSpeed = 5
    this.pulsePhase = 0
  }

  moveTo(zoneName) {
    const zone = ZONES[zoneName]
    if (!zone) {
      console.warn(`Unknown zone: ${zoneName}`)
      return
    }
    this.targetX = zone.x
    this.targetY = zone.y
    this.currentZone = zoneName
    this.state = 'moving'
  }

  startTool(toolName) {
    this.currentTool = toolName
    this.state = 'working'
  }

  finishTool() {
    this.currentTool = null
    this.message = null
    this.targetX = ZONES.village_square.x
    this.targetY = ZONES.village_square.y
    this.currentZone = 'village_square'
    this.state = 'moving'
  }

  setMessage(msg) {
    this.message = msg
  }

  update() {
    const dx = this.targetX - this.x
    const dy = this.targetY - this.y
    const distance = Math.sqrt(dx * dx + dy * dy)

    if (distance > this.moveSpeed) {
      this.x += (dx / distance) * this.moveSpeed
      this.y += (dy / distance) * this.moveSpeed
    } else {
      this.x = this.targetX
      this.y = this.targetY
      if (this.state === 'moving') {
        this.state = this.currentTool ? 'working' : 'idle'
      }
    }

    this.pulsePhase += 0.1
  }

  draw(ctx) {
    ctx.save()

    // Pulse effect when working
    let radius = this.radius
    if (this.state === 'working') {
      radius += Math.sin(this.pulsePhase) * 3
    }

    // Glow effect
    if (this.state === 'working' || this.state === 'moving') {
      ctx.beginPath()
      ctx.arc(this.x, this.y, radius + 10, 0, Math.PI * 2)
      ctx.fillStyle = this.color + '33'
      ctx.fill()
    }

    // Main circle
    ctx.beginPath()
    ctx.arc(this.x, this.y, radius, 0, Math.PI * 2)
    ctx.fillStyle = this.color
    ctx.fill()

    // Border
    ctx.strokeStyle = '#ffffff'
    ctx.lineWidth = 2
    ctx.stroke()

    // Name label
    ctx.fillStyle = '#ffffff'
    ctx.font = '12px monospace'
    ctx.textAlign = 'center'
    ctx.fillText(this.name, this.x, this.y + radius + 15)

    // Tool label when working
    if (this.currentTool) {
      ctx.fillStyle = '#ffcc00'
      ctx.font = '10px monospace'
      ctx.fillText(this.currentTool, this.x, this.y - radius - 5)
    }

    // Speech bubble with message
    if (this.message) {
      this.drawSpeechBubble(ctx)
    }

    ctx.restore()
  }

  drawSpeechBubble(ctx) {
    const bubbleWidth = Math.min(150, this.message.length * 7 + 20)
    const bubbleHeight = 30
    const bubbleX = this.x - bubbleWidth / 2
    const bubbleY = this.y - this.radius - 45

    // Bubble background
    ctx.fillStyle = '#ffffff'
    ctx.beginPath()
    ctx.roundRect(bubbleX, bubbleY, bubbleWidth, bubbleHeight, 8)
    ctx.fill()

    // Bubble pointer
    ctx.beginPath()
    ctx.moveTo(this.x - 5, bubbleY + bubbleHeight)
    ctx.lineTo(this.x, bubbleY + bubbleHeight + 8)
    ctx.lineTo(this.x + 5, bubbleY + bubbleHeight)
    ctx.fill()

    // Message text
    ctx.fillStyle = '#1a1a2e'
    ctx.font = '11px monospace'
    ctx.textAlign = 'center'
    const truncated = this.message.length > 20 ? this.message.slice(0, 18) + '...' : this.message
    ctx.fillText(truncated, this.x, bubbleY + 19)
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// RENDERER
// ═══════════════════════════════════════════════════════════════════════════

class Renderer {
  constructor(canvas) {
    this.canvas = canvas
    this.ctx = canvas.getContext('2d')
    canvas.width = CANVAS_WIDTH
    canvas.height = CANVAS_HEIGHT
  }

  clear() {
    this.ctx.fillStyle = '#1a1a2e'
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height)
  }

  drawZones(activeZone = null) {
    // Draw connections first (behind zones)
    this.drawConnections()

    for (const [name, zone] of Object.entries(ZONES)) {
      this.drawZone(name, zone, name === activeZone)
    }
  }

  drawZone(name, zone, isActive = false) {
    const ctx = this.ctx
    const halfW = zone.width / 2
    const halfH = zone.height / 2

    ctx.save()

    // Glow when active
    if (isActive) {
      ctx.shadowColor = zone.color
      ctx.shadowBlur = 20
    }

    // Zone background
    ctx.fillStyle = zone.color + '66'
    ctx.strokeStyle = zone.color
    ctx.lineWidth = 2

    // Rounded rectangle
    ctx.beginPath()
    ctx.roundRect(zone.x - halfW, zone.y - halfH, zone.width, zone.height, 10)
    ctx.fill()
    ctx.stroke()

    // Label
    ctx.fillStyle = '#ffffff'
    ctx.font = '11px monospace'
    ctx.textAlign = 'center'
    ctx.fillText(zone.label, zone.x, zone.y + halfH + 15)

    ctx.restore()
  }

  drawConnections() {
    const ctx = this.ctx
    ctx.save()

    ctx.strokeStyle = '#ffffff22'
    ctx.lineWidth = 1

    const center = ZONES.village_square
    for (const [name, zone] of Object.entries(ZONES)) {
      if (name === 'village_square') continue

      ctx.beginPath()
      ctx.moveTo(center.x, center.y)
      ctx.lineTo(zone.x, zone.y)
      ctx.stroke()
    }

    ctx.restore()
  }

  drawStatus(status) {
    const ctx = this.ctx
    ctx.save()

    // Connection indicator
    const dotColor = status.connection === 'connected' ? '#00ff88' : '#ff4444'
    ctx.beginPath()
    ctx.arc(15, 15, 6, 0, Math.PI * 2)
    ctx.fillStyle = dotColor
    ctx.fill()

    ctx.fillStyle = '#ffffff'
    ctx.font = '12px monospace'
    ctx.textAlign = 'left'
    ctx.fillText(status.connection, 28, 19)
    ctx.fillText(`Events: ${status.eventCount}`, 10, 35)

    if (status.lastTool) {
      ctx.fillStyle = '#ffcc00'
      ctx.fillText(`Last: ${status.lastTool}`, 10, 50)
    }

    ctx.restore()
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// COMPOSABLE
// ═══════════════════════════════════════════════════════════════════════════

export function useVillage() {
  const canvasRef = ref(null)
  const status = reactive({
    connection: 'disconnected',
    eventCount: 0,
    lastTool: null
  })

  const agents = new Map()
  const eventLog = ref([])
  const activeZone = ref(null)

  let renderer = null
  let ws = null
  let animationId = null

  function ensureAgent(agentId) {
    if (!agents.has(agentId)) {
      const color = AGENT_COLORS[agentId] || AGENT_COLORS.default
      const agent = new Agent(agentId, agentId, color)
      agents.set(agentId, agent)
      console.log(`Created agent: ${agentId}`)
    }
    return agents.get(agentId)
  }

  let wsRetryDelay = 3000
  let wsAuthFailed = false
  let wsFailCount = 0
  const WS_MAX_RETRIES = 5

  function isTokenExpired(token) {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]))
      return payload.exp && payload.exp < Date.now() / 1000
    } catch { return false }
  }

  function connectWebSocket() {
    // Don't connect without auth token - backend requires it (closes with 1008)
    const token = localStorage.getItem('accessToken')
    if (!token || token === 'undefined' || token === 'null') {
      status.connection = 'no-auth'
      return
    }

    if (wsAuthFailed) return

    // Stop retrying with expired token - user needs to re-login
    if (isTokenExpired(token)) {
      console.log('Village WebSocket token expired, not retrying')
      wsAuthFailed = true
      status.connection = 'no-auth'
      return
    }

    // Stop after too many consecutive failures
    if (wsFailCount >= WS_MAX_RETRIES) {
      console.log(`Village WebSocket gave up after ${WS_MAX_RETRIES} failures`)
      wsAuthFailed = true
      status.connection = 'failed'
      return
    }

    let apiUrl = import.meta.env.VITE_API_URL || ''
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'

    // Ensure apiUrl has protocol prefix (same fix as api.js)
    if (apiUrl && !apiUrl.startsWith('http://') && !apiUrl.startsWith('https://')) {
      apiUrl = 'https://' + apiUrl
    }

    let wsUrl
    if (apiUrl) {
      wsUrl = apiUrl.replace(/^https?:/, wsProtocol) + '/ws/village'
    } else {
      wsUrl = `${wsProtocol}//${window.location.host}/ws/village`
    }

    wsUrl += `?token=${token}`

    console.log(`Connecting to ${wsUrl.split('?')[0]}`)
    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.log('Village WebSocket connected')
      status.connection = 'connected'
      wsRetryDelay = 3000
      wsFailCount = 0
    }

    ws.onclose = (event) => {
      status.connection = 'disconnected'

      // 1008 = Policy Violation (auth failure), 1006 = Abnormal (403 rejection)
      if (event.code === 1008) {
        console.log('Village WebSocket auth rejected, not retrying')
        wsAuthFailed = true
        status.connection = 'no-auth'
        return
      }

      wsFailCount++
      console.log(`Village WebSocket disconnected (code ${event.code}), attempt ${wsFailCount}/${WS_MAX_RETRIES}, retrying in ${wsRetryDelay / 1000}s`)
      setTimeout(() => connectWebSocket(), wsRetryDelay)
      wsRetryDelay = Math.min(wsRetryDelay * 1.5, 30000)
    }

    ws.onerror = () => {
      status.connection = 'error'
    }

    ws.onmessage = (event) => {
      handleEvent(JSON.parse(event.data))
    }
  }

  function handleEvent(event) {
    console.log('Village event:', event)
    status.eventCount++

    // Add to event log (keep last 50)
    eventLog.value.unshift({
      ...event,
      receivedAt: Date.now()
    })
    if (eventLog.value.length > 50) {
      eventLog.value.pop()
    }

    switch (event.type) {
      case 'tool_start':
        handleToolStart(event)
        break
      case 'tool_complete':
      case 'tool_error':
        handleToolComplete(event)
        break
      case 'approval_needed':
        handleApprovalNeeded(event)
        break
      case 'input_needed':
        handleInputNeeded(event)
        break
      case 'connection':
        console.log('Connection confirmed:', event.message)
        break
      case 'music_complete':
        // Dispatch DOM event for MusicPlayer notification (decoupled from Village)
        window.dispatchEvent(new CustomEvent('music-complete', { detail: event }))
        break
      default:
        console.log('Unknown event type:', event.type)
    }
  }

  function handleToolStart(event) {
    const agent = ensureAgent(event.agent_id)
    agent.moveTo(event.zone)
    agent.startTool(event.tool)
    activeZone.value = event.zone
    status.lastTool = event.tool
  }

  function handleToolComplete(event) {
    const agent = agents.get(event.agent_id)
    if (agent) {
      agent.finishTool()
    }
    setTimeout(() => {
      activeZone.value = null
    }, 500)
  }

  function handleApprovalNeeded(event) {
    const agent = ensureAgent(event.agent_id)
    agent.setMessage(event.message || 'Approval needed')
  }

  function handleInputNeeded(event) {
    const agent = ensureAgent(event.agent_id)
    agent.setMessage(event.message || 'Input needed')
  }

  function animate() {
    if (!renderer) return

    // Update all agents
    for (const agent of agents.values()) {
      agent.update()
    }

    // Render
    renderer.clear()
    renderer.drawZones(activeZone.value)

    // Draw all agents
    for (const agent of agents.values()) {
      agent.draw(renderer.ctx)
    }

    renderer.drawStatus(status)

    animationId = requestAnimationFrame(animate)
  }

  function initialize(canvas) {
    canvasRef.value = canvas
    renderer = new Renderer(canvas)

    // Create default agent
    ensureAgent('CLAUDE')

    // Connect WebSocket
    connectWebSocket()

    // Start animation
    animate()
  }

  function cleanup() {
    if (animationId) {
      cancelAnimationFrame(animationId)
    }
    if (ws) {
      ws.close()
    }
  }

  // Send message to backend
  function sendMessage(type, data = {}) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, ...data }))
    }
  }

  return {
    canvasRef,
    status,
    eventLog,
    activeZone,
    agents,
    initialize,
    cleanup,
    sendMessage,
    ensureAgent,
    ZONES,
    AGENT_COLORS
  }
}
