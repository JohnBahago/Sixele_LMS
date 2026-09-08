import asyncio
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape
from app.core.config import settings
from app.database.mongodb import db

DEFAULT_TEMPLATES = {
    "notification": {
        "subject": "{{title}}",
        "body": "{{message}}\n\n{{action_url}}",
    },
    "welcome": {
        "subject": "Welcome to {{lms_name}}",
        "body": "Welcome to {{lms_name}}. Your account is ready.",
    },
}

async def _setting(key, default):
    doc = await db.system_settings.find_one({"key": key})
    return doc.get("value", default) if doc else default


def render_template(text: str, values: dict) -> str:
    result = text
    for key, value in values.items():
        result = result.replace("{{" + key + "}}", str(value or ""))
    return result

async def queue_email(*, recipient_id: str, email: str, name: str | None, subject: str,
                      body: str, notification_id: str | None = None, event: str = "notification"):
    now = datetime.now(timezone.utc)
    doc = {
        "recipient_id": str(recipient_id), "email": email.lower().strip(), "name": name,
        "subject": subject.strip(), "body": body.strip(), "event": event,
        "notification_id": notification_id, "status": "queued", "attempts": 0,
        "last_error": None, "next_attempt_at": now, "created_at": now, "updated_at": now,
    }
    result = await db.email_outbox.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc

async def enqueue_notification_emails(*, notification_docs: list[dict], event: str = "notification"):
    enabled = await _setting("notifications.email_enabled", False)
    if not enabled or not notification_docs:
        return []
    ids = list({str(x["recipient_id"]) for x in notification_docs})
    users = await db.users.find({"_id": {"$in": [__import__('bson').ObjectId(x) for x in ids if __import__('bson').ObjectId.is_valid(x)]}}).to_list(length=len(ids))
    users_by_id = {str(u["_id"]): u for u in users}
    out = []
    for n in notification_docs:
        user = users_by_id.get(str(n["recipient_id"]))
        if not user or not user.get("email"):
            continue
        pref = await db.notification_preferences.find_one({"user_id": str(n["recipient_id"])})
        if pref and not pref.get("email_enabled", True):
            continue
        values = {
            "title": n.get("title", "Sixele LMS Notification"), "message": n.get("message", ""),
            "action_url": n.get("action_url") or "", "lms_name": await _setting("lms.name", "Sixele LMS"),
            "name": user.get("full_name", "Learner"),
        }
        template = DEFAULT_TEMPLATES["notification"]
        subject = render_template(template["subject"], values)
        body = render_template(template["body"], values)
        out.append(await queue_email(recipient_id=str(user["_id"]), email=user["email"], name=user.get("full_name"), subject=subject, body=body, notification_id=str(n["_id"]), event=event))
    return out


def _send_sync(*, to_email: str, subject: str, body: str):
    host = settings.smtp_host
    port = settings.smtp_port
    username = settings.smtp_username
    password = settings.smtp_password
    sender = settings.smtp_from_email or username
    if not host or not sender:
        raise RuntimeError("SMTP is not configured")
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    if settings.smtp_use_tls:
        with smtplib.SMTP(host, port, timeout=settings.smtp_timeout_seconds) as server:
            server.starttls()
            if username:
                server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=settings.smtp_timeout_seconds) as server:
            if username:
                server.login(username, password)
            server.send_message(msg)

async def process_email_outbox(*, limit: int = 25, max_attempts: int = 5):
    now = datetime.now(timezone.utc)
    docs = await db.email_outbox.find({"status": {"$in": ["queued", "retry"]}, "next_attempt_at": {"$lte": now}, "attempts": {"$lt": max_attempts}}).sort("created_at", 1).limit(limit).to_list(length=limit)
    results = {"processed": 0, "sent": 0, "failed": 0}
    for doc in docs:
        results["processed"] += 1
        attempts = int(doc.get("attempts", 0)) + 1
        await db.email_outbox.update_one({"_id": doc["_id"]}, {"$set": {"status": "sending", "attempts": attempts, "updated_at": now}})
        try:
            await asyncio.to_thread(_send_sync, to_email=doc["email"], subject=doc["subject"], body=doc["body"])
            await db.email_outbox.update_one({"_id": doc["_id"]}, {"$set": {"status": "sent", "sent_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc), "last_error": None}})
            results["sent"] += 1
        except Exception as exc:
            terminal = attempts >= max_attempts
            next_at = datetime.now(timezone.utc) + timedelta(minutes=min(60, 2 ** min(attempts, 6)))
            await db.email_outbox.update_one({"_id": doc["_id"]}, {"$set": {"status": "failed" if terminal else "retry", "last_error": str(exc)[:1000], "next_attempt_at": next_at, "updated_at": datetime.now(timezone.utc)}})
            results["failed"] += 1
    return results
