from datetime import datetime
from pydantic import BaseModel, Field

class EmailOutboxResponse(BaseModel):
    id: str
    recipient_id: str
    email: str
    name: str | None = None
    subject: str
    event: str
    status: str
    attempts: int
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime
    sent_at: datetime | None = None

class EmailProcessResponse(BaseModel):
    processed: int
    sent: int
    failed: int

class EmailTemplateResponse(BaseModel):
    key: str
    subject: str
    body: str
