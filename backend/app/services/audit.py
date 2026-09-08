from datetime import datetime, timezone
from typing import Any
from app.database.mongodb import db

async def audit_log(*, actor_id: str | None, action: str, resource: str, resource_id: str | None = None,
                    details: dict[str, Any] | None = None, request=None):
    client_ip = None
    user_agent = None
    request_id = None
    if request is not None:
        client_ip = request.client.host if request.client else None
        if request.headers.get("x-forwarded-for"):
            client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        user_agent = request.headers.get("user-agent")
        request_id = getattr(request.state, "request_id", None)
    await db.audit_logs.insert_one({
        "actor_id": actor_id,
        "action": action,
        "resource": resource,
        "resource_id": resource_id,
        "details": details or {},
        "request_id": request_id,
        "client_ip": client_ip,
        "user_agent": user_agent,
        "created_at": datetime.now(timezone.utc),
    })
