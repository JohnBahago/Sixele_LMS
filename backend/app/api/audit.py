import csv
import io
from datetime import datetime
from fastapi import APIRouter, Depends, Query, Response
from app.database.mongodb import db
from app.api.auth import get_current_user
from app.services.authorization import require_permission

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])

async def _query_logs(limit: int, action: str | None, resource: str | None, actor_id: str | None, start: datetime | None, end: datetime | None):
    query = {}
    if action: query["action"] = action
    if resource: query["resource"] = resource
    if actor_id: query["actor_id"] = actor_id
    if start or end:
        query["created_at"] = {}
        if start: query["created_at"]["$gte"] = start
        if end: query["created_at"]["$lte"] = end
    return [item async for item in db.audit_logs.find(query).sort("created_at", -1).limit(limit)]

def _serialize(item):
    return {"id": str(item["_id"]), "actor_id": item.get("actor_id"), "action": item.get("action"), "resource": item.get("resource"), "resource_id": item.get("resource_id"), "details": item.get("details", {}), "request_id": item.get("request_id"), "client_ip": item.get("client_ip"), "user_agent": item.get("user_agent"), "created_at": item.get("created_at").isoformat() if item.get("created_at") else None}

@router.get("")
async def list_audit_logs(limit: int = Query(50, ge=1, le=500), action: str | None = None, resource: str | None = None, actor_id: str | None = None, start: datetime | None = None, end: datetime | None = None, user=Depends(get_current_user)):
    await require_permission(user, "audit.view")
    return [_serialize(x) for x in await _query_logs(limit, action, resource, actor_id, start, end)]

@router.get("/export")
async def export_audit_logs(limit: int = Query(5000, ge=1, le=10000), action: str | None = None, resource: str | None = None, actor_id: str | None = None, start: datetime | None = None, end: datetime | None = None, user=Depends(get_current_user)):
    await require_permission(user, "audit.export")
    rows = [_serialize(x) for x in await _query_logs(limit, action, resource, actor_id, start, end)]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["id","actor_id","action","resource","resource_id","request_id","client_ip","user_agent","created_at"])
    writer.writeheader()
    for row in rows: writer.writerow({k: row.get(k) for k in writer.fieldnames})
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=audit-logs.csv"})
