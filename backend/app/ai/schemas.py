"""What the model must return (master prompt §8.2). Facts and judgments are kept apart.

Every fact carries `evidence`: an exact quote from the customer's message. The grounding step
drops any fact whose quote is not really in the message. Unknown fields are rejected, enums are
enforced and every string is length-capped, so model output is data, never instructions.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Quote = Field(default=None, max_length=300)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ServiceMention(Strict):
    name: str = Field(max_length=120, description="A service name from the catalog, or 'other'")
    evidence: str = Field(max_length=300)


class BudgetFact(Strict):
    min_amount: float | None = Field(default=None, ge=0)
    max_amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    evidence: str | None = Quote
    confidence: float = Field(default=0.5, ge=0, le=1)


class TimelineFact(Strict):
    text: str | None = Field(default=None, max_length=120)
    urgency: Literal["immediate", "soon", "flexible", "unspecified"] = "unspecified"
    evidence: str | None = Quote
    confidence: float = Field(default=0.5, ge=0, le=1)


class TextFact(Strict):
    value: str | None = Field(default=None, max_length=200)
    evidence: str | None = Quote
    confidence: float = Field(default=0.5, ge=0, le=1)


class EvidenceItem(Strict):
    text: str = Field(max_length=200)
    evidence: str = Field(max_length=300)


class Extraction(Strict):
    service_interest: list[ServiceMention] = Field(default_factory=list, max_length=5)
    budget: BudgetFact = Field(default_factory=BudgetFact)
    timeline: TimelineFact = Field(default_factory=TimelineFact)
    company: TextFact = Field(default_factory=TextFact)
    industry: TextFact = Field(default_factory=TextFact)
    requirements: list[EvidenceItem] = Field(default_factory=list, max_length=10)
    language: str = Field(default="en", max_length=12)


class Assessment(Strict):
    intent: Literal[
        "hiring",
        "researching",
        "price_check",
        "support_request",
        "partnership",
        "job_seeker",
        "spam",
        "unknown",
    ] = "unknown"
    buying_signals: list[EvidenceItem] = Field(default_factory=list, max_length=8)
    red_flags: list[str] = Field(default_factory=list, max_length=8)
    missing_info: list[str] = Field(default_factory=list, max_length=10)
    summary: str = Field(default="", max_length=400)
    recommended_next_action: str = Field(default="", max_length=200)


class AnalysisOutput(Strict):
    extraction: Extraction = Field(default_factory=Extraction)
    assessment: Assessment = Field(default_factory=Assessment)
