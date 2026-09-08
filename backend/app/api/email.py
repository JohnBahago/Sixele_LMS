from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.email import EmailOutboxResponse, EmailProcessResponse, EmailTemplateResponse
from app.services.authorization import require_permission
from app.services.email import DEFAULT_TEMPLATES, process_email_outbox

router = APIRouter(prefix="/email", tags=["Email Infrastructure"])

def _response(d):
    return EmailOutboxResponse(id=str(d["_id"]), recipient_id=str(d["recipient_id"]), email=d["email"], name=d.get("name"), subject=d["subject"], event=d.get("event", "notification"), status=d.get("status", "queued"), attempts=d.get("attempts", 0), last_error=d.get("last_error"), created_at=d["created_at"], updated_at=d.get("updated_at", d["created_at"]), sent_at=d.get("sent_at"))

@router.get("/outbox", response_model=list[EmailOutboxResponse])
async def list_outbox(status: str | None = None, limit: int = Query(50, ge=1, le=200), user=Depends(get_current_user)):
    await require_permission(user, "notifications.manage")
    query = {"status": status} if status else {}
    docs = await db.email_outbox.find(query).sort("created_at", -1).limit(limit).to_list(length=limit)
    return [_response(x) for x in docs]

@router.post("/process", response_model=EmailProcessResponse)
async def process_outbox(limit: int = Query(25, ge=1, le=100), user=Depends(get_current_user)):
    await require_permission(user, "notifications.manage")
    return await process_email_outbox(limit=limit)

@router.get("/templates", response_model=list[EmailTemplateResponse])
async def list_templates(user=Depends(get_current_user)):
    await require_permission(user, "notifications.manage")
    return [EmailTemplateResponse(key=k, subject=v["subject"], body=v["body"]) for k, v in DEFAULT_TEMPLATES.items()]
