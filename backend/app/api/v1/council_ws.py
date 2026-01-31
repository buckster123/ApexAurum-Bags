"""
Council WebSocket - Per-Token Streaming

Real-time token-by-token streaming for council deliberations.
All agents stream in parallel -- their text appears simultaneously.

"The Council speaks, word by word"
"""

import asyncio
import json
import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth.jwt import verify_token
from app.database import async_session
from app.models.user import User
from app.models.council import (
    DeliberationSession, SessionAgent, DeliberationRound, SessionMessage
)
from app.services.claude import ClaudeService
from app.api.v1.council import (
    execute_agent_turn_streaming,
    build_round_context,
    check_convergence,
    store_council_memories,
    COUNCIL_MODEL,
)
from app.api.v1.chat import load_native_prompt, get_agent_prompt_with_memory
from app.services.neural_memory import NeuralMemoryService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Council WebSocket"])

# Singleton ClaudeService for council WS
_claude_service = None


def get_claude_service() -> ClaudeService:
    global _claude_service
    if _claude_service is None:
        _claude_service = ClaudeService()
    return _claude_service


async def authenticate_ws(websocket: WebSocket) -> User | None:
    """Authenticate WebSocket connection via query param token."""
    token = websocket.query_params.get("token")
    if not token:
        return None

    payload = verify_token(token, token_type="access")
    if not payload:
        return None

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        return None

    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


async def send_event(websocket: WebSocket, event: dict):
    """Send JSON event to WebSocket, silently handle disconnection."""
    try:
        await websocket.send_text(json.dumps(event))
    except Exception:
        pass


@router.websocket("/council/{session_id}")
async def council_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for per-token council streaming.

    Connect: ws://host/ws/council/{session_id}?token=JWT

    Client → Server commands:
    - start_deliberation: {type, num_rounds}
    - pause: {type}
    - resume: {type}
    - stop: {type}
    - butt_in: {type, message}
    - ping: {type}

    Server → Client events:
    - round_start, agent_token, agent_tool_start, agent_tool_complete,
      agent_complete, round_complete, consensus, end, error
    """
    await websocket.accept()

    # Authenticate
    user = await authenticate_ws(websocket)
    if not user:
        await send_event(websocket, {"type": "error", "message": "Authentication failed"})
        await websocket.close(code=4001, reason="Authentication failed")
        return

    # Validate session_id
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        await send_event(websocket, {"type": "error", "message": "Invalid session ID"})
        await websocket.close(code=4002, reason="Invalid session ID")
        return

    await send_event(websocket, {
        "type": "connected",
        "session_id": session_id,
        "user": user.email,
    })

    # Track running deliberation task
    deliberation_task = None

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type")
            except json.JSONDecodeError:
                continue

            if msg_type == "ping":
                await send_event(websocket, {"type": "pong"})

            elif msg_type == "start_deliberation":
                num_rounds = message.get("num_rounds", 5)
                if deliberation_task and not deliberation_task.done():
                    await send_event(websocket, {"type": "error", "message": "Deliberation already running"})
                    continue
                deliberation_task = asyncio.create_task(
                    run_streaming_deliberation(
                        websocket, session_uuid, user, num_rounds
                    )
                )

            elif msg_type == "pause":
                async with async_session() as db:
                    result = await db.execute(
                        select(DeliberationSession)
                        .where(DeliberationSession.id == session_uuid)
                        .where(DeliberationSession.user_id == user.id)
                    )
                    session = result.scalar_one_or_none()
                    if session and session.state == "running":
                        session.state = "paused"
                        await db.commit()
                        await send_event(websocket, {"type": "paused"})

            elif msg_type == "resume":
                num_rounds = message.get("num_rounds", 5)
                async with async_session() as db:
                    result = await db.execute(
                        select(DeliberationSession)
                        .where(DeliberationSession.id == session_uuid)
                        .where(DeliberationSession.user_id == user.id)
                    )
                    session = result.scalar_one_or_none()
                    if session and session.state == "paused":
                        session.state = "running"
                        await db.commit()
                        if deliberation_task is None or deliberation_task.done():
                            deliberation_task = asyncio.create_task(
                                run_streaming_deliberation(
                                    websocket, session_uuid, user, num_rounds
                                )
                            )
                        await send_event(websocket, {"type": "resumed"})

            elif msg_type == "stop":
                async with async_session() as db:
                    result = await db.execute(
                        select(DeliberationSession)
                        .where(DeliberationSession.id == session_uuid)
                        .where(DeliberationSession.user_id == user.id)
                    )
                    session = result.scalar_one_or_none()
                    if session and session.state in ("running", "paused"):
                        session.state = "complete"
                        session.termination_reason = "user_stopped"
                        session.completed_at = datetime.utcnow()
                        await db.commit()
                        await send_event(websocket, {"type": "stopped"})

            elif msg_type == "butt_in":
                butt_in_msg = message.get("message", "")
                if butt_in_msg:
                    async with async_session() as db:
                        result = await db.execute(
                            select(DeliberationSession)
                            .where(DeliberationSession.id == session_uuid)
                            .where(DeliberationSession.user_id == user.id)
                        )
                        session = result.scalar_one_or_none()
                        if session:
                            session.pending_human_message = butt_in_msg
                            await db.commit()
                            await send_event(websocket, {
                                "type": "butt_in_queued",
                                "message": butt_in_msg,
                            })

    except WebSocketDisconnect:
        logger.info(f"Council WS disconnected: session={session_id}")
    except Exception as e:
        logger.error(f"Council WS error: {e}")
    finally:
        if deliberation_task and not deliberation_task.done():
            deliberation_task.cancel()


async def run_streaming_deliberation(
    websocket: WebSocket,
    session_id: UUID,
    user: User,
    num_rounds: int,
):
    """
    Run the deliberation loop with per-token streaming.

    All agents run in parallel. Token events are sent to the WebSocket
    as they arrive from each agent's stream.
    """
    claude = get_claude_service()

    async with async_session() as db:
        # Load session with relationships
        result = await db.execute(
            select(DeliberationSession)
            .where(DeliberationSession.id == session_id)
            .where(DeliberationSession.user_id == user.id)
            .options(
                selectinload(DeliberationSession.agents),
                selectinload(DeliberationSession.rounds).selectinload(DeliberationRound.messages),
            )
        )
        session = result.scalar_one_or_none()

        if not session:
            await send_event(websocket, {"type": "error", "message": "Session not found"})
            return

        if session.state == "complete":
            await send_event(websocket, {"type": "error", "message": "Session already complete"})
            return

        # Start
        session.mode = "auto"
        session.state = "running"
        await db.commit()

        await send_event(websocket, {
            "type": "start",
            "session_id": str(session.id),
            "num_rounds": num_rounds,
            "starting_round": session.current_round + 1,
        })

        rounds_executed = 0
        total_session_input = 0
        total_session_output = 0

        try:
            while rounds_executed < num_rounds and session.current_round < session.max_rounds:
                # Check for pause/stop
                await db.refresh(session)
                if session.state == "paused":
                    await send_event(websocket, {"type": "paused", "round_number": session.current_round})
                    break
                if session.state == "complete":
                    await send_event(websocket, {"type": "stopped", "round_number": session.current_round})
                    break

                round_number = session.current_round + 1

                # Check for human butt-in
                human_message = session.pending_human_message
                if human_message:
                    await send_event(websocket, {
                        "type": "human_message_injected",
                        "content": human_message,
                    })
                    session.pending_human_message = None

                # Create round record
                round_record = DeliberationRound(
                    session_id=session.id,
                    round_number=round_number,
                    human_message=human_message,
                    started_at=datetime.utcnow(),
                )
                db.add(round_record)
                await db.flush()

                await send_event(websocket, {"type": "round_start", "round_number": round_number})

                # Build context
                context = build_round_context(session, round_number, human_message)
                active_agents = [a for a in session.agents if a.is_active]

                # Pre-load agent prompts and village memories sequentially
                # (DB session can't handle concurrent operations)
                agent_prompts = {}
                agent_village_memories = {}
                for agent in active_agents:
                    try:
                        prompt = await get_agent_prompt_with_memory(
                            agent_id=agent.agent_id,
                            user=user,
                            use_pac=False,
                            db=db,
                        )
                        agent_prompts[agent.agent_id] = prompt
                    except Exception as e:
                        logger.warning(f"Failed to load prompt for {agent.agent_id}: {e}")
                        agent_prompts[agent.agent_id] = load_native_prompt(agent.agent_id, use_pac=False)

                    try:
                        neural = NeuralMemoryService(db)
                        village_memories = await neural.get_village_memories(
                            user_id=user.id,
                            topic=session.topic,
                            limit=5,
                            collection="council",
                        )
                        if village_memories:
                            agent_village_memories[agent.agent_id] = neural.format_village_memories_for_prompt(
                                village_memories, max_chars=1500,
                            )
                        else:
                            agent_village_memories[agent.agent_id] = ""
                    except Exception as e:
                        logger.warning(f"Failed to get village memories for {agent.agent_id}: {e}")
                        await db.rollback()  # Unpoison transaction after SQL failure
                        agent_village_memories[agent.agent_id] = ""

                # Token callback -- sends each token to the WebSocket
                async def make_on_token(ws):
                    async def on_token(agent_id: str, token: str):
                        await send_event(ws, {
                            "type": "agent_token",
                            "agent_id": agent_id,
                            "token": token,
                        })
                    return on_token

                # Tool callback
                async def make_on_tool(ws):
                    async def on_tool(agent_id: str, event: dict):
                        await send_event(ws, {
                            "type": f"agent_{event['type']}",
                            "agent_id": agent_id,
                            **{k: v for k, v in event.items() if k != "type"},
                        })
                    return on_tool

                on_token = await make_on_token(websocket)
                on_tool = await make_on_tool(websocket)

                # Run all agents in parallel (prompts pre-loaded, no DB contention)
                tasks = []
                for agent in active_agents:
                    tasks.append(
                        execute_agent_turn_streaming(
                            claude, session, round_record, agent, context, db,
                            on_token=on_token, on_tool=on_tool, user=user,
                            base_prompt=agent_prompts.get(agent.agent_id),
                            village_memory_block=agent_village_memories.get(agent.agent_id, ""),
                        )
                    )

                agent_results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results
                total_round_input = 0
                total_round_output = 0
                round_messages = []

                for i, agent_result in enumerate(agent_results):
                    agent = active_agents[i]
                    if isinstance(agent_result, Exception):
                        logger.error(f"Agent {agent.agent_id} failed: {agent_result}")
                        content = f"[Error: {str(agent_result)}]"
                        input_tokens = 0
                        output_tokens = 0
                        tool_calls = None
                    else:
                        content = agent_result["content"]
                        input_tokens = agent_result["input_tokens"]
                        output_tokens = agent_result["output_tokens"]
                        tool_calls = agent_result.get("tool_calls")

                    # Save message
                    msg = SessionMessage(
                        session_id=session.id,
                        round_id=round_record.id,
                        role="agent",
                        agent_id=agent.agent_id,
                        content=content,
                        tool_calls=tool_calls,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    )
                    db.add(msg)
                    round_messages.append(msg)

                    agent.input_tokens += input_tokens
                    agent.output_tokens += output_tokens
                    total_round_input += input_tokens
                    total_round_output += output_tokens

                    # Signal agent complete (tokens already streamed)
                    await send_event(websocket, {
                        "type": "agent_complete",
                        "agent_id": agent.agent_id,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                    })

                # Update session stats
                session.current_round = round_number
                session.total_input_tokens += total_round_input
                session.total_output_tokens += total_round_output
                total_session_input += total_round_input
                total_session_output += total_round_output

                round_cost = (total_round_input * 0.25 + total_round_output * 1.25) / 1_000_000
                session.total_cost_usd += round_cost

                round_record.completed_at = datetime.utcnow()

                # Convergence check
                convergence_score = check_convergence(round_messages)
                round_record.convergence_score = convergence_score
                session.convergence_score = convergence_score

                try:
                    await db.commit()
                except Exception as commit_err:
                    logger.error(f"Council WS round {round_number} commit failed: {commit_err}")
                    await db.rollback()
                    # Refresh session after rollback to avoid MissingGreenlet on expired attrs
                    await db.refresh(session)
                    await send_event(websocket, {
                        "type": "error",
                        "message": f"Failed to save round {round_number} data",
                    })
                    rounds_executed += 1
                    continue

                await send_event(websocket, {
                    "type": "round_complete",
                    "round_number": round_number,
                    "convergence_score": convergence_score,
                    "cost_usd": round_cost,
                    "total_cost_usd": session.total_cost_usd,
                })

                # Consensus detection
                if convergence_score >= 0.8:
                    session.state = "complete"
                    session.termination_reason = "consensus"
                    await db.commit()
                    await send_event(websocket, {
                        "type": "consensus",
                        "score": convergence_score,
                        "round_number": round_number,
                    })
                    break

                # Store neural memories
                try:
                    stored = await store_council_memories(
                        db=db, user_id=user.id, session_id=session.id,
                        messages=round_messages, topic=session.topic,
                    )
                    if stored > 0:
                        logger.debug(f"Stored {stored} council memories for round {round_number}")
                except Exception as e:
                    logger.warning(f"Failed to store council memories: {e}")

                rounds_executed += 1

                # Reload session for next round
                await db.refresh(session)
                result = await db.execute(
                    select(DeliberationSession)
                    .options(
                        selectinload(DeliberationSession.agents),
                        selectinload(DeliberationSession.rounds).selectinload(DeliberationRound.messages),
                    )
                    .where(DeliberationSession.id == session_id)
                )
                session = result.scalar_one()

            # Final state
            if session.state != "paused":
                if session.current_round >= session.max_rounds:
                    session.state = "complete"
                    session.termination_reason = "max_rounds"
                elif rounds_executed >= num_rounds:
                    session.state = "running"

            await db.commit()

        except Exception as e:
            logger.error(f"Council WS deliberation error: {e}", exc_info=True)
            await send_event(websocket, {"type": "error", "message": str(e)})
            try:
                await db.rollback()
            except Exception:
                pass

        model = session.model or COUNCIL_MODEL
        await send_event(websocket, {
            "type": "end",
            "state": session.state,
            "total_rounds": session.current_round,
            "model": model,
            "input_tokens": total_session_input,
            "output_tokens": total_session_output,
        })
