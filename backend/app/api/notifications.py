from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo import ReturnDocument
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.notifications import NotificationCreate, NotificationListResponse, NotificationPreferenceResponse, NotificationPreferenceUpdate, NotificationResponse
from app.services.authorization import require_permission
from app.services.audit import audit_log
from app.services.notifications import create_notifications

router = APIRouter(prefix="/notifications", tags=["Notifications"])

def _response(doc: dict) -> NotificationResponse:
    return NotificationResponse(id=str(doc["_id"]), recipient_id=str(doc["recipient_id"]), title=doc["title"], message=doc["message"], notification_type=doc["notification_type"], course_id=doc.get("course_id"), action_url=doc.get("action_url"), is_read=doc.get("is_read", False), read_at=doc.get("read_at"), created_at=doc["created_at"])

@router.get("", response_model=NotificationListResponse)
async def list_notifications(user=Depends(get_current_user), unread_only: bool = False, limit: int = Query(50, ge=1, le=100), skip: int = Query(0, ge=0)):
    uid = str(user["_id"])
    query = {"recipient_id": uid}
    if unread_only: query["is_read"] = False
    total = await db.notifications.count_documents(query)
    unread = await db.notifications.count_documents({"recipient_id": uid, "is_read": False})
    docs = await db.notifications.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)
    return NotificationListResponse(items=[_response(x) for x in docs], unread_count=unread, total=total)

@router.post("", response_model=list[NotificationResponse], status_code=201)
async def create_notification(body: NotificationCreate, user=Depends(get_current_user)):
    await require_permission(user, "notifications.create")
    ids = []
    for uid in body.recipient_ids:
        if not ObjectId.is_valid(uid) or not await db.users.find_one({"_id": ObjectId(uid), "is_active": True}):
            raise HTTPException(400, f"Invalid or inactive recipient: {uid}")
        ids.append(uid)
    docs = await create_notifications(recipient_ids=ids, title=body.title, message=body.message, notification_type=body.notification_type.value, course_id=body.course_id, action_url=body.action_url, actor_id=str(user["_id"]))
    return [_response(d) for d in docs]

@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(notification_id: str, user=Depends(get_current_user)):
    if not ObjectId.is_valid(notification_id): raise HTTPException(404, "Notification not found")
    now = datetime.now(timezone.utc)
    doc = await db.notifications.find_one_and_update({"_id": ObjectId(notification_id), "recipient_id": str(user["_id"])}, {"$set": {"is_read": True, "read_at": now}}, return_document=ReturnDocument.AFTER)
    if not doc: raise HTTPException(404, "Notification not found")
    return _response(doc)

@router.post("/read-all")
async def mark_all_read(user=Depends(get_current_user)):
    result = await db.notifications.update_many({"recipient_id": str(user["_id"]), "is_read": False}, {"$set": {"is_read": True, "read_at": datetime.now(timezone.utc)}})
    return {"updated": result.modified_count}

@router.delete("/{notification_id}", status_code=204)
async def delete_notification(notification_id: str, user=Depends(get_current_user)):
    if not ObjectId.is_valid(notification_id): raise HTTPException(404, "Notification not found")
    result = await db.notifications.delete_one({"_id": ObjectId(notification_id), "recipient_id": str(user["_id"])})
    if result.deleted_count == 0: raise HTTPException(404, "Notification not found")

@router.get("/preferences", response_model=NotificationPreferenceResponse)
async def get_preferences(user=Depends(get_current_user)):
    uid = str(user["_id"])
    doc = await db.notification_preferences.find_one({"user_id": uid})
    if not doc:
        defaults = NotificationPreferenceUpdate().model_dump()
        doc = {"user_id": uid, **defaults, "updated_at": datetime.now(timezone.utc)}
        await db.notification_preferences.insert_one(doc)
    return NotificationPreferenceResponse(**{k: doc.get(k) for k in NotificationPreferenceResponse.model_fields})

@router.patch("/preferences", response_model=NotificationPreferenceResponse)
async def update_preferences(body: NotificationPreferenceUpdate, user=Depends(get_current_user)):
    uid = str(user["_id"]); now = datetime.now(timezone.utc)
    data = body.model_dump(); data["updated_at"] = now
    await db.notification_preferences.update_one({"user_id": uid}, {"$set": {**data, "user_id": uid}}, upsert=True)
    await audit_log(actor_id=uid, action="notification_preferences.updated", resource="notification_preferences", resource_id=uid)
    return NotificationPreferenceResponse(user_id=uid, **data)
