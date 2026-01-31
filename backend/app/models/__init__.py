"""
ApexAurum Cloud - SQLAlchemy Models

Import order matters for SQLAlchemy relationship resolution.
Models referenced in relationships must be imported before the
models that reference them.
"""

# Import models that are referenced by others FIRST
# from app.models.vector import UserVector  # Temp disabled
from app.models.error_log import ErrorLog
from app.models.file import File, Folder
from app.models.conversation import Conversation, Message
from app.models.agent import Agent
from app.models.village import VillageKnowledge
from app.models.memory import Memory
from app.models.music import MusicTask
from app.models.agent_memory import AgentMemory
from app.models.billing import Subscription, CreditBalance, CreditTransaction, WebhookEvent, Coupon, CouponRedemption
from app.models.council import DeliberationSession, SessionAgent, DeliberationRound, SessionMessage
from app.models.jam import JamSession, JamParticipant, JamTrack, JamMessage
from app.models.feedback import BugReport
from app.models.nursery import NurseryDataset, NurseryTrainingJob, NurseryModelRecord, NurseryApprentice
from app.models.usage import UsageCounter
from app.models.feature_credit import FeatureCreditBalance
from app.models.system import SystemSettings
from app.models.device import Device

# User references all of the above, so import LAST
from app.models.user import User

__all__ = [
    "ErrorLog",
    "User",
    "Conversation",
    "Message",
    "Agent",
    "VillageKnowledge",
    "Memory",
    "MusicTask",
    "AgentMemory",
    "File",
    "Folder",
    "Subscription",
    "CreditBalance",
    "CreditTransaction",
    "WebhookEvent",
    "Coupon",
    "CouponRedemption",
    "DeliberationSession",
    "SessionAgent",
    "DeliberationRound",
    "SessionMessage",
    "JamSession",
    "JamParticipant",
    "JamTrack",
    "JamMessage",
    "BugReport",
    "NurseryDataset",
    "NurseryTrainingJob",
    "NurseryModelRecord",
    "NurseryApprentice",
    "UsageCounter",
    "FeatureCreditBalance",
    "SystemSettings",
    "Device",
    # "UserVector",  # Temp disabled
]
