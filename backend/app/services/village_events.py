"""
Village Event Broadcasting Service

Manages WebSocket connections and broadcasts tool events to connected Village GUI clients.
Enables real-time visualization of agent activity in the 2D village interface.

"Where invisible actions become visible movements"
"""

import asyncio
import json
import logging
import time
from typing import Set, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Types of events broadcast to Village GUI."""
    TOOL_START = "tool_start"
    TOOL_COMPLETE = "tool_complete"
    TOOL_ERROR = "tool_error"
    AGENT_THINKING = "agent_thinking"
    AGENT_IDLE = "agent_idle"
    AGENT_MOVE = "agent_move"
    CONNECTION = "connection"
    APPROVAL_NEEDED = "approval_needed"
    INPUT_NEEDED = "input_needed"
    MUSIC_COMPLETE = "music_complete"


# Zone mapping - which tools belong to which village zone
# Updated for ApexAurum-Cloud's 46 tools across 11 tiers
TOOL_ZONE_MAP = {
    # ═══════════════════════════════════════════════════════════════
    # DJ BOOTH - Music & Audio tools (Tier 9)
    # ═══════════════════════════════════════════════════════════════
    "music_generate": "dj_booth",
    "music_status": "dj_booth",
    "music_list": "dj_booth",
    "music_favorite": "dj_booth",

    # ═══════════════════════════════════════════════════════════════
    # MEMORY GARDEN - Vector & Memory tools (Tier 8, 11)
    # ═══════════════════════════════════════════════════════════════
    "vector_add": "memory_garden",
    "vector_search": "memory_garden",
    "vector_delete": "memory_garden",
    "vector_list_collections": "memory_garden",
    "vector_stats": "memory_garden",
    # Neo-Cortex (Tier 11)
    "cortex_remember": "memory_garden",
    "cortex_recall": "memory_garden",
    "cortex_village": "memory_garden",
    "cortex_stats": "memory_garden",
    "cortex_export": "memory_garden",
    "cortex_import": "memory_garden",
    # Scratch Memory (Tier 5)
    "scratch_write": "memory_garden",
    "scratch_read": "memory_garden",
    "scratch_append": "memory_garden",
    "scratch_delete": "memory_garden",

    # ═══════════════════════════════════════════════════════════════
    # FILE SHED - Vault & File tools (Tier 3)
    # ═══════════════════════════════════════════════════════════════
    "vault_upload": "file_shed",
    "vault_download": "file_shed",
    "vault_list": "file_shed",
    "vault_delete": "file_shed",
    "vault_search": "file_shed",

    # ═══════════════════════════════════════════════════════════════
    # WORKSHOP - Code Execution tools (Tier 6)
    # ═══════════════════════════════════════════════════════════════
    "execute_python": "workshop",
    "eval_expression": "workshop",

    # ═══════════════════════════════════════════════════════════════
    # BRIDGE PORTAL - Agent & Village Protocol tools (Tier 7)
    # ═══════════════════════════════════════════════════════════════
    "agent_spawn": "bridge_portal",
    "agent_status": "bridge_portal",
    "agent_result": "bridge_portal",

    # ═══════════════════════════════════════════════════════════════
    # LIBRARY - Knowledge Base tools (Tier 4)
    # ═══════════════════════════════════════════════════════════════
    "kb_search": "library",
    "kb_answer": "library",
    "kb_topics": "library",
    "kb_quick_lookup": "library",

    # ═══════════════════════════════════════════════════════════════
    # WATCHTOWER - Web & Browser tools (Tier 2, 10)
    # ═══════════════════════════════════════════════════════════════
    "web_fetch": "watchtower",
    "web_search": "watchtower",
    # Steel Browser (Tier 10)
    "browser_navigate": "watchtower",
    "browser_screenshot": "watchtower",
    "browser_click": "watchtower",
    "browser_type": "watchtower",
    "browser_extract": "watchtower",
    "browser_close": "watchtower",

    # ═══════════════════════════════════════════════════════════════
    # VILLAGE SQUARE - Default for utilities (Tier 1)
    # ═══════════════════════════════════════════════════════════════
    "get_current_time": "village_square",
    "calculate": "village_square",
    "random_number": "village_square",
    "word_count": "village_square",
    "generate_uuid": "village_square",
    "json_format": "village_square",

    # ═══════════════════════════════════════════════════════════════
    # NURSERY - Model Training tools (Tier 15)
    # ═══════════════════════════════════════════════════════════════
    "nursery_generate_data": "nursery",
    "nursery_extract_data": "nursery",
    "nursery_list_datasets": "nursery",
    "nursery_estimate_cost": "nursery",
    "nursery_train": "nursery",
    "nursery_job_status": "nursery",
    "nursery_list_jobs": "nursery",
    "nursery_list_models": "nursery",
    "nursery_register_model": "nursery",
    "nursery_discover_models": "nursery",
}


@dataclass
class VillageEvent:
    """Event to be broadcast to Village GUI."""
    type: EventType
    agent_id: str
    tool: Optional[str] = None
    zone: str = "village_square"
    arguments: Optional[Dict] = None
    result_preview: Optional[str] = None
    success: Optional[bool] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    message: Optional[str] = None  # For approval/input events
    timestamp: int = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = int(time.time() * 1000)

    def to_json(self) -> str:
        """Convert to JSON string for WebSocket."""
        data = {k: v for k, v in asdict(self).items() if v is not None}
        data["type"] = self.type.value  # Convert enum to string
        return json.dumps(data)


class VillageEventBroadcaster:
    """
    Singleton service for broadcasting events to Village GUI WebSocket clients.

    Usage:
        broadcaster = get_village_broadcaster()
        await broadcaster.broadcast_tool_start("AZOTH", "music_generate", {"prompt": "..."})
    """

    _instance: Optional['VillageEventBroadcaster'] = None

    def __init__(self):
        self.connections: Set = set()
        self._current_agent: str = "CLAUDE"
        self._tool_start_times: Dict[str, float] = {}

    @classmethod
    def get_instance(cls) -> 'VillageEventBroadcaster':
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_current_agent(self, agent_id: str):
        """Set the current active agent for events."""
        self._current_agent = agent_id
        logger.debug(f"Village: Current agent set to {agent_id}")

    def get_zone_for_tool(self, tool_name: str) -> str:
        """Get the zone a tool belongs to."""
        return TOOL_ZONE_MAP.get(tool_name, "village_square")

    @property
    def connection_count(self) -> int:
        """Number of connected Village GUI clients."""
        return len(self.connections)

    async def connect(self, websocket):
        """Register a new WebSocket connection."""
        self.connections.add(websocket)
        logger.info(f"Village GUI connected. Total: {len(self.connections)}")

        # Send welcome event
        event = VillageEvent(
            type=EventType.CONNECTION,
            agent_id="SYSTEM",
            zone="village_square",
            message="Welcome to the Village"
        )
        try:
            await websocket.send_text(event.to_json())
        except Exception as e:
            logger.warning(f"Failed to send welcome: {e}")

    def disconnect(self, websocket):
        """Remove a WebSocket connection."""
        self.connections.discard(websocket)
        logger.info(f"Village GUI disconnected. Total: {len(self.connections)}")

    async def broadcast(self, event: VillageEvent):
        """Broadcast event to all connected clients."""
        if not self.connections:
            return

        message = event.to_json()
        disconnected = set()

        for connection in self.connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send to connection: {e}")
                disconnected.add(connection)

        # Clean up disconnected
        self.connections -= disconnected

    async def broadcast_tool_start(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_id: Optional[str] = None
    ):
        """Broadcast tool execution start - agent walks to zone."""
        agent = agent_id or self._current_agent
        zone = self.get_zone_for_tool(tool_name)

        # Track start time for duration calculation
        key = f"{agent}:{tool_name}"
        self._tool_start_times[key] = time.time()

        # Sanitize arguments (remove sensitive data)
        safe_args = self._sanitize_arguments(arguments)

        event = VillageEvent(
            type=EventType.TOOL_START,
            agent_id=agent,
            tool=tool_name,
            zone=zone,
            arguments=safe_args
        )
        await self.broadcast(event)
        logger.debug(f"Village: {agent} -> {tool_name} @ {zone}")

    async def broadcast_tool_complete(
        self,
        tool_name: str,
        result: Any,
        success: bool = True,
        agent_id: Optional[str] = None
    ):
        """Broadcast tool execution complete - agent returns to square."""
        agent = agent_id or self._current_agent
        zone = self.get_zone_for_tool(tool_name)

        # Calculate duration
        key = f"{agent}:{tool_name}"
        start_time = self._tool_start_times.pop(key, None)
        duration_ms = int((time.time() - start_time) * 1000) if start_time else None

        # Create result preview (truncated, sanitized)
        result_preview = self._create_result_preview(result)

        event = VillageEvent(
            type=EventType.TOOL_COMPLETE,
            agent_id=agent,
            tool=tool_name,
            zone=zone,
            result_preview=result_preview,
            success=success,
            duration_ms=duration_ms
        )
        await self.broadcast(event)
        logger.debug(f"Village: {agent} <- {tool_name} ({duration_ms}ms)")

    async def broadcast_tool_error(
        self,
        tool_name: str,
        error: str,
        agent_id: Optional[str] = None
    ):
        """Broadcast tool execution error."""
        agent = agent_id or self._current_agent
        zone = self.get_zone_for_tool(tool_name)

        # Clean up start time
        key = f"{agent}:{tool_name}"
        self._tool_start_times.pop(key, None)

        event = VillageEvent(
            type=EventType.TOOL_ERROR,
            agent_id=agent,
            tool=tool_name,
            zone=zone,
            error=error[:200],
            success=False
        )
        await self.broadcast(event)

    async def broadcast_approval_needed(
        self,
        agent_id: str,
        message: str,
        tool_name: Optional[str] = None
    ):
        """Broadcast that agent needs user approval - shows clickable bubble."""
        event = VillageEvent(
            type=EventType.APPROVAL_NEEDED,
            agent_id=agent_id,
            tool=tool_name,
            zone=self.get_zone_for_tool(tool_name) if tool_name else "village_square",
            message=message
        )
        await self.broadcast(event)

    async def broadcast_input_needed(
        self,
        agent_id: str,
        message: str,
        tool_name: Optional[str] = None
    ):
        """Broadcast that agent needs user input - shows input popup when clicked."""
        event = VillageEvent(
            type=EventType.INPUT_NEEDED,
            agent_id=agent_id,
            tool=tool_name,
            zone=self.get_zone_for_tool(tool_name) if tool_name else "village_square",
            message=message
        )
        await self.broadcast(event)

    # ═══════════════════════════════════════════════════════════════
    # Synchronous versions for non-async contexts
    # ═══════════════════════════════════════════════════════════════

    def _get_or_create_loop(self):
        """Get running loop or create task."""
        try:
            loop = asyncio.get_running_loop()
            return loop, True
        except RuntimeError:
            return None, False

    def broadcast_sync(self, event: VillageEvent):
        """Synchronous broadcast - schedules in running loop."""
        loop, is_running = self._get_or_create_loop()
        if is_running and loop:
            asyncio.create_task(self.broadcast(event))
        # If no loop running, skip (will be picked up by async context)

    def tool_start_sync(self, tool_name: str, arguments: Dict, agent_id: Optional[str] = None):
        """Synchronous tool start broadcast."""
        agent = agent_id or self._current_agent
        zone = self.get_zone_for_tool(tool_name)
        key = f"{agent}:{tool_name}"
        self._tool_start_times[key] = time.time()

        safe_args = self._sanitize_arguments(arguments)

        event = VillageEvent(
            type=EventType.TOOL_START,
            agent_id=agent,
            tool=tool_name,
            zone=zone,
            arguments=safe_args
        )
        self.broadcast_sync(event)

    def tool_complete_sync(
        self,
        tool_name: str,
        result: Any,
        success: bool = True,
        agent_id: Optional[str] = None
    ):
        """Synchronous tool complete broadcast."""
        agent = agent_id or self._current_agent
        zone = self.get_zone_for_tool(tool_name)

        key = f"{agent}:{tool_name}"
        start_time = self._tool_start_times.pop(key, None)
        duration_ms = int((time.time() - start_time) * 1000) if start_time else None

        result_preview = self._create_result_preview(result)

        event = VillageEvent(
            type=EventType.TOOL_COMPLETE,
            agent_id=agent,
            tool=tool_name,
            zone=zone,
            result_preview=result_preview,
            success=success,
            duration_ms=duration_ms
        )
        self.broadcast_sync(event)

    # ═══════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════

    def _sanitize_arguments(self, arguments: Dict) -> Dict:
        """Remove sensitive data from arguments before broadcasting."""
        if not arguments:
            return {}

        safe = {}
        sensitive_keys = {'password', 'token', 'secret', 'key', 'auth', 'credential'}

        for k, v in arguments.items():
            if any(s in k.lower() for s in sensitive_keys):
                safe[k] = "[REDACTED]"
            elif isinstance(v, str) and len(v) > 200:
                safe[k] = v[:200] + "..."
            else:
                safe[k] = v

        return safe

    def _create_result_preview(self, result: Any) -> str:
        """Create a safe preview of the result."""
        try:
            if result is None:
                return "None"
            result_str = str(result)
            if len(result_str) > 150:
                return result_str[:150] + "..."
            return result_str
        except Exception:
            return "[Result preview unavailable]"


# Module-level singleton accessor
def get_village_broadcaster() -> VillageEventBroadcaster:
    """Get the global Village event broadcaster instance."""
    return VillageEventBroadcaster.get_instance()
