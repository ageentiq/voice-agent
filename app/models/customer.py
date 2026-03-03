from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class LeadQuality(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    NOT_INTERESTED = "not_interested"


class PurchaseGoal(str, Enum):
    RESIDENTIAL = "residential"
    INVESTMENT = "investment"
    UNKNOWN = "unknown"


class PurchaseMethod(str, Enum):
    CASH = "cash"
    BANK_FINANCING = "bank_financing"
    UNKNOWN = "unknown"


class CustomerAnalysis(BaseModel):
    """Result of the analysis tool - lead qualification."""

    call_id: str
    customer_phone: str
    customer_name: str

    # Mandatory info from prompt
    purchase_goal: Optional[PurchaseGoal] = None  # سكني أم استثماري
    purchase_method: Optional[PurchaseMethod] = None  # كاش أو تمويل بنكي
    rooms_or_area: Optional[str] = None  # عدد الغرف أو المساحة
    budget_range: Optional[str] = None  # الميزانية أو النطاق السعري
    preferences: list[str] = []  # تفضيلات (قرب خدمات، واجهة، إلخ)

    # Analysis results
    lead_quality: LeadQuality = LeadQuality.COLD
    interest_level: int = Field(default=5, ge=1, le=10)  # 1-10
    summary: str = ""  # Brief summary in Arabic
    next_action: str = ""  # Recommended next step
    conversation_end_reason: str = ""  # Why conversation ended

    # If customer interested in another project
    other_project_name: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)


class CustomerRecord(BaseModel):
    """Customer record stored in MongoDB."""

    phone: str
    name: str
    analyses: list[CustomerAnalysis] = []
    total_calls: int = 0
    last_call_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
