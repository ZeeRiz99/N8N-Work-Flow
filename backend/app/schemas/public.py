"""Public lead form: the only data a stranger on the internet can send us."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


class PublicLeadIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=200)
    service: str | None = Field(default=None, max_length=80)
    budget: str | None = Field(default=None, max_length=80)
    timeline: str | None = Field(default=None, max_length=80)
    message: str = Field(min_length=1, max_length=4000)
    consent: bool
    # Honeypot: hidden on the form. People leave it empty; simple bots fill it in.
    nickname: str | None = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def email_shape(cls, v: str) -> str:
        if not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address.")
        return v

    @field_validator("consent")
    @classmethod
    def consent_given(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent is required to send the request.")
        return v


class PublicLeadOut(BaseModel):
    status: str = "received"
    reference: str  # inquiry id; lets the visitor quote it, reveals nothing else


class PublicFormConfig(BaseModel):
    organization_name: str
    form_key: str
    services: list[str]
    budget_options: list[str]
    timeline_options: list[str]
    response_time_line: str
