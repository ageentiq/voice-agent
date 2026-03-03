from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CallStatus(str, Enum):
    QUEUED = "queued"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    CANCELED = "canceled"


class CallDirection(str, Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class TranscriptEntry(BaseModel):
    role: str  # "customer" or "agent"
    text: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CallSession(BaseModel):
    call_id: str
    twilio_call_sid: Optional[str] = None
    customer_phone: str
    customer_name: str
    direction: CallDirection = CallDirection.OUTBOUND
    status: CallStatus = CallStatus.QUEUED
    transcript: list[TranscriptEntry] = []
    conversation_history: list[dict] = []  # Claude message history
    collected_info: dict = {}  # Info gathered during call
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict = {}  # Extra context passed by n8n/trigger


class InitiateCallRequest(BaseModel):
    customer_phone: str
    customer_name: str
    context: dict = {}  # Additional context (e.g., project info, previous interactions)


class BatchCallRequest(BaseModel):
    customers: list[InitiateCallRequest]


class CallStatusResponse(BaseModel):
    call_id: str
    status: CallStatus
    customer_phone: str
    customer_name: str
    duration_seconds: Optional[float] = None
    created_at: datetime
