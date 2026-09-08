from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

class CertificateStatus(str, Enum):
    issued = "issued"
    revoked = "revoked"

class CertificateTemplateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str = ""
    title: str = Field(default="Certificate of Completion", min_length=2, max_length=200)
    issuer_name: str = Field(min_length=2, max_length=200)
    body_text: str = "This certificate is awarded for successful completion of the course."
    signature_name: str = ""
    signature_title: str = ""
    is_active: bool = True

class CertificateTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    title: str | None = Field(default=None, min_length=2, max_length=200)
    issuer_name: str | None = Field(default=None, min_length=2, max_length=200)
    body_text: str | None = None
    signature_name: str | None = None
    signature_title: str | None = None
    is_active: bool | None = None

class CertificateTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    title: str
    issuer_name: str
    body_text: str
    signature_name: str
    signature_title: str
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime

class CertificateIssueRequest(BaseModel):
    enrollment_id: str
    template_id: str | None = None
    force_override: bool = False
    override_reason: str | None = Field(default=None, max_length=1000)

class CertificateResponse(BaseModel):
    id: str
    certificate_number: str
    enrollment_id: str
    learner_id: str
    course_id: str
    learner_name: str
    course_title: str
    template_id: str | None
    status: str
    issued_at: datetime
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    revocation_reason: str | None = None
    completion_score: float | None = None
    verification_url: str
    override_used: bool = False
    override_reason: str | None = None
    pdf_url: str | None = None
    pdf_generated: bool = False

class CertificateVerificationResponse(BaseModel):
    valid: bool
    certificate_number: str
    status: str | None = None
    learner_name: str | None = None
    course_title: str | None = None
    issued_at: datetime | None = None
    completion_score: float | None = None
    issuer_name: str | None = None
    message: str
