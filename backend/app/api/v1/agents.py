"""
Agent Endpoints

Background agent management and Socratic council.
"""

import logging
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.agent import Agent
from app.auth.deps import get_current_user_optional
from app.services.claude import ClaudeService
from app.services.billing import BillingService
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter()

# Use Haiku 4.5 for agents (fast and efficient)
AGENT_MODEL = "claude-haiku-4-5-20251001"

# Initialize Claude service
_claude_service = None

def get_claude_service() -> ClaudeService:
    global _claude_service
    if _claude_service is None:
        _claude_service = ClaudeService()
    return _claude_service

# Agent type prompts
AGENT_TYPE_PROMPTS = {
    "general": "You are a general-purpose AI assistant. Complete the given task thoroughly and provide a clear, actionable result.",
    "researcher": "You are a research specialist. Analyze the topic deeply, gather insights, and provide comprehensive findings with sources where applicable.",
    "coder": "You are a coding expert. Write clean, efficient code. Explain your implementation decisions. Include error handling and best practices.",
    "analyst": "You are a data analyst. Break down the problem systematically, identify patterns, and provide data-driven insights and recommendations.",
    "writer": "You are a skilled writer. Create engaging, well-structured content that is clear, compelling, and appropriate for the intended audience.",
}


# Schemas
class AgentSpawnRequest(BaseModel):
    task: str
    agent_type: str = "general"  # 'general', 'researcher', 'coder', 'analyst', 'writer'


class AgentResponse(BaseModel):
    id: UUID
    agent_type: str
    task: str
    status: str
    result: Optional[str]
    error: Optional[str]
    created_at: str
    completed_at: Optional[str]

    class Config:
        from_attributes = True


class CouncilRequest(BaseModel):
    question: str
    num_agents: int = 3
    agent_types: list[str] = ["general", "researcher", "coder"]
    options: Optional[list[str]] = None


class CouncilResponse(BaseModel):
    question: str
    votes: dict[str, int]
    reasoning: dict[str, str]
    consensus: Optional[str]
    agents: list[AgentResponse]


# Endpoints
@router.post("/spawn", response_model=AgentResponse)
async def spawn_agent(
    request: AgentSpawnRequest,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Spawn a new agent and execute the task.

    Agent types:
    - general: General-purpose assistant
    - researcher: Deep research and analysis
    - coder: Code generation and review
    - analyst: Data analysis and insights
    - writer: Content creation and editing
    """
    # Generate an ID for tracking (even if not saving to DB)
    agent_id = uuid4()
    created_at = datetime.utcnow()

    # Get system prompt for agent type
    system_prompt = AGENT_TYPE_PROMPTS.get(request.agent_type, AGENT_TYPE_PROMPTS["general"])

    try:
        claude = get_claude_service()

        # Execute the task
        response = await claude.chat(
            messages=[{"role": "user", "content": request.task}],
            model=AGENT_MODEL,
            system=system_prompt,
        )

        # Extract result
        result_content = ""
        for block in response.get("content", []):
            if block.get("text"):
                result_content += block["text"]

        # Record billing usage if user authenticated and Stripe configured
        if user and settings.stripe_secret_key:
            try:
                billing_service = BillingService(db)
                usage = response.get("usage", {})
                await billing_service.record_message_usage(
                    user_id=user.id,
                    provider="anthropic",
                    model=AGENT_MODEL,
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                )
                logger.debug(f"Recorded spawn usage: {usage.get('input_tokens', 0)}in/{usage.get('output_tokens', 0)}out")
            except Exception as e:
                logger.error(f"Failed to record spawn billing: {e}")

        # Save to DB if authenticated
        if user:
            agent = Agent(
                id=agent_id,
                user_id=user.id,
                agent_type=request.agent_type,
                task=request.task,
                status="complete",
                result=result_content,
                completed_at=datetime.utcnow(),
            )
            db.add(agent)
            await db.commit()

        return AgentResponse(
            id=agent_id,
            agent_type=request.agent_type,
            task=request.task,
            status="complete",
            result=result_content,
            error=None,
            created_at=created_at.isoformat(),
            completed_at=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"Agent execution failed: {e}")

        return AgentResponse(
            id=agent_id,
            agent_type=request.agent_type,
            task=request.task,
            status="failed",
            result=None,
            error=str(e),
            created_at=created_at.isoformat(),
            completed_at=datetime.utcnow().isoformat(),
        )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: UUID,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Get agent status and result."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found (login required to view saved agents)"
        )

    result = await db.execute(
        select(Agent)
        .where(Agent.id == agent_id)
        .where(Agent.user_id == user.id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

    return AgentResponse(
        id=agent.id,
        agent_type=agent.agent_type,
        task=agent.task,
        status=agent.status,
        result=agent.result,
        error=agent.error,
        created_at=agent.created_at.isoformat(),
        completed_at=agent.completed_at.isoformat() if agent.completed_at else None,
    )


@router.get("/", response_model=list[AgentResponse])
async def list_agents(
    limit: int = 20,
    status_filter: Optional[str] = None,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """List user's agents. Returns empty if not authenticated."""
    if not user:
        return []

    query = select(Agent).where(Agent.user_id == user.id)

    if status_filter:
        query = query.where(Agent.status == status_filter)

    query = query.order_by(Agent.created_at.desc()).limit(limit)

    result = await db.execute(query)
    agents = result.scalars().all()

    return [
        AgentResponse(
            id=a.id,
            agent_type=a.agent_type,
            task=a.task,
            status=a.status,
            result=a.result,
            error=a.error,
            created_at=a.created_at.isoformat(),
            completed_at=a.completed_at.isoformat() if a.completed_at else None,
        )
        for a in agents
    ]


@router.post("/council", response_model=CouncilResponse)
async def socratic_council(
    request: CouncilRequest,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Run a Socratic council with multiple agents.

    Each agent independently considers the question and votes.
    Returns consensus if majority agreement.
    """
    import asyncio

    claude = get_claude_service()

    # Track total usage across all council members
    total_input_tokens = 0
    total_output_tokens = 0

    # Council member personas
    council_personas = [
        ("Pragmatist", "You are a practical, results-oriented thinker. Focus on what works in reality."),
        ("Idealist", "You are an idealistic visionary. Focus on what's right and what could be."),
        ("Skeptic", "You are a critical thinker. Question assumptions and look for flaws."),
        ("Synthesizer", "You are an integrative thinker. Find common ground and bridge perspectives."),
        ("Innovator", "You are a creative problem solver. Think outside the box and propose novel solutions."),
    ]

    # Prepare options text if provided
    options_text = ""
    if request.options:
        options_text = "\n\nOptions to choose from:\n" + "\n".join(f"- {opt}" for opt in request.options)

    async def get_council_vote(persona_name: str, persona_prompt: str) -> dict:
        """Get a single council member's vote and reasoning."""
        nonlocal total_input_tokens, total_output_tokens

        system = f"""You are {persona_name}, a member of a deliberative council. {persona_prompt}

You must provide a clear vote and brief reasoning. Format your response EXACTLY as:
VOTE: [Your choice - be specific]
REASONING: [2-3 sentences explaining why]"""

        try:
            response = await claude.chat(
                messages=[{"role": "user", "content": f"Question for the council: {request.question}{options_text}"}],
                model=AGENT_MODEL,
                system=system,
            )

            # Track usage
            usage = response.get("usage", {})
            total_input_tokens += usage.get("input_tokens", 0)
            total_output_tokens += usage.get("output_tokens", 0)

            content = ""
            for block in response.get("content", []):
                if block.get("text"):
                    content += block["text"]

            # Parse vote and reasoning
            vote = "Abstain"
            reasoning = content

            if "VOTE:" in content:
                parts = content.split("VOTE:", 1)[1]
                if "REASONING:" in parts:
                    vote = parts.split("REASONING:")[0].strip()
                    reasoning = parts.split("REASONING:")[1].strip()
                else:
                    vote = parts.strip()

            return {"persona": persona_name, "vote": vote, "reasoning": reasoning}

        except Exception as e:
            return {"persona": persona_name, "vote": "Error", "reasoning": str(e)}

    # Run council members in parallel
    num_members = min(request.num_agents, len(council_personas))
    selected_personas = council_personas[:num_members]

    tasks = [get_council_vote(name, prompt) for name, prompt in selected_personas]
    results = await asyncio.gather(*tasks)

    # Record billing usage for all council calls combined
    if user and settings.stripe_secret_key and (total_input_tokens > 0 or total_output_tokens > 0):
        try:
            billing_service = BillingService(db)
            await billing_service.record_message_usage(
                user_id=user.id,
                provider="anthropic",
                model=AGENT_MODEL,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
            )
            await db.commit()
            logger.debug(f"Recorded council usage ({num_members} members): {total_input_tokens}in/{total_output_tokens}out")
        except Exception as e:
            logger.error(f"Failed to record council billing: {e}")

    # Tally votes
    votes = {}
    reasoning = {}
    for r in results:
        vote = r["vote"]
        votes[vote] = votes.get(vote, 0) + 1
        reasoning[r["persona"]] = f"{r['vote']} - {r['reasoning']}"

    # Determine consensus (majority)
    consensus = None
    if votes:
        max_votes = max(votes.values())
        if max_votes > num_members / 2:
            consensus = [k for k, v in votes.items() if v == max_votes][0]

    return CouncilResponse(
        question=request.question,
        votes=votes,
        reasoning=reasoning,
        consensus=consensus,
        agents=[],
    )
