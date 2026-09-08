from fastapi import APIRouter, Depends
from app.api.auth import get_current_user
from app.schemas.notification_events import NotificationEventTest
from app.services.authorization import require_permission
from app.services.notifications import notify_event

router = APIRouter(prefix="/notification-events", tags=["Notification Events"])

@router.post("/test")
async def test_notification_event(body: NotificationEventTest, user=Depends(get_current_user)):
    await require_permission(user, "notifications.create")
    docs = await notify_event(event=body.event, recipient_ids=body.recipient_ids,
                              title=body.title, message=body.message,
                              notification_type=body.event, course_id=body.course_id,
                              action_url=body.action_url, actor_id=str(user["_id"]))
    return {"created": len(docs), "notification_ids": [str(d["_id"]) for d in docs]}
