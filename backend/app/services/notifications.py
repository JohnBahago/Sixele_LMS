from datetime import datetime, timezone
from app.database.mongodb import db
from app.services.audit import audit_log
from app.services.email import enqueue_notification_emails

PREFERENCE_KEYS = {
    "system": "system", "enrollment": "enrollment", "submission": "submission",
    "grading": "grading", "revision": "revision", "assessment": "assessment",
    "completion": "completion", "course": "course", "attendance": "attendance",
}

async def create_notifications(*, recipient_ids: list[str], title: str, message: str,
                                notification_type: str = "system", course_id: str | None = None,
                                action_url: str | None = None, actor_id: str | None = None,
                                respect_preferences: bool = True):
    now = datetime.now(timezone.utc)
    recipients = list(dict.fromkeys(str(uid) for uid in recipient_ids))
    if respect_preferences and recipients:
        key = PREFERENCE_KEYS.get(notification_type, "system")
        prefs = await db.notification_preferences.find({"user_id": {"$in": recipients}}).to_list(length=len(recipients))
        pref_map = {str(p["user_id"]): p for p in prefs}
        recipients = [uid for uid in recipients if pref_map.get(uid, {}).get(key, True)]
    docs = [{
        "recipient_id": uid, "title": title.strip(), "message": message.strip(),
        "notification_type": notification_type, "course_id": course_id,
        "action_url": action_url, "is_read": False, "read_at": None, "created_at": now,
    } for uid in recipients]
    if docs:
        result = await db.notifications.insert_many(docs)
        for doc, inserted_id in zip(docs, result.inserted_ids):
            doc["_id"] = inserted_id
        await audit_log(actor_id=actor_id, action="notifications.created", resource="notification",
                        details={"count": len(result.inserted_ids), "type": notification_type})
    if docs:
        await enqueue_notification_emails(notification_docs=docs, event=notification_type)
    return docs

async def notify_event(*, event: str, recipient_ids: list[str], title: str, message: str,
                       notification_type: str, course_id: str | None = None,
                       action_url: str | None = None, actor_id: str | None = None):
    docs = await create_notifications(recipient_ids=recipient_ids, title=title, message=message,
                                      notification_type=notification_type, course_id=course_id,
                                      action_url=action_url, actor_id=actor_id, respect_preferences=True)
    if docs:
        await audit_log(actor_id=actor_id, action=f"notification.event.{event}", resource="notification",
                        details={"recipient_count": len(docs), "notification_type": notification_type})
    return docs
