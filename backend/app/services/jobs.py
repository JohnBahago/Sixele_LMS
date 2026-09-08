import asyncio
import os
import socket
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from bson import ObjectId

from app.database.mongodb import db
from app.services.email import process_email_outbox
from app.services.completion import reconcile_active_enrollments
from app.services.attendance_compliance import evaluate_attendance_alerts

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
LEASE_SECONDS = 55

JOB_DEFINITIONS = {
    "email_outbox": {"interval_seconds": 30, "description": "Process queued and retryable emails."},
    "notification_cleanup": {"interval_seconds": 86400, "description": "Remove old read notifications according to retention settings."},
    "completion_reconciliation": {"interval_seconds": 60, "description": "Recalculate active learner progress and automate course completion certificates."},
    "attendance_compliance_alerts": {"interval_seconds": 900, "description": "Evaluate learner attendance compliance and send risk/recovery alerts."},
}


def _now():
    return datetime.now(timezone.utc)


async def _record_start(job_name: str, started_at: datetime):
    await db.scheduled_jobs.update_one(
        {"job_name": job_name},
        {"$set": {"job_name": job_name, "status": "running", "started_at": started_at, "worker_id": WORKER_ID, "updated_at": started_at}},
        upsert=True,
    )


async def _record_success(job_name: str, started_at: datetime, result: dict):
    now = _now()
    await db.scheduled_jobs.update_one(
        {"job_name": job_name},
        {"$set": {"status": "success", "started_at": started_at, "finished_at": now, "last_run_at": now, "last_result": result, "last_error": None, "worker_id": WORKER_ID, "updated_at": now}},
        upsert=True,
    )


async def _record_failure(job_name: str, started_at: datetime, error: Exception):
    now = _now()
    await db.scheduled_jobs.update_one(
        {"job_name": job_name},
        {"$set": {"status": "failed", "started_at": started_at, "finished_at": now, "last_run_at": now, "last_error": str(error)[:2000], "worker_id": WORKER_ID, "updated_at": now}},
        upsert=True,
    )


async def _run_email_outbox() -> dict:
    batch_size = int(await _setting("jobs.email_batch_size", 25))
    max_attempts = int(await _setting("email.max_attempts", 5))
    return await process_email_outbox(limit=max(1, min(batch_size, 100)), max_attempts=max(1, min(max_attempts, 20)))


async def _run_notification_cleanup() -> dict:
    retention_days = int(await _setting("notifications.retention_days", 180))
    if retention_days <= 0:
        return {"deleted": 0, "skipped": True, "reason": "retention disabled"}
    cutoff = _now() - timedelta(days=retention_days)
    result = await db.notifications.delete_many({"is_read": True, "created_at": {"$lt": cutoff}})
    return {"deleted": result.deleted_count, "cutoff": cutoff.isoformat()}


async def _run_completion_reconciliation() -> dict:
    batch_size = int(await _setting("jobs.completion_batch_size", 250))
    return await reconcile_active_enrollments(limit=max(1, min(batch_size, 1000)))

async def _run_attendance_compliance_alerts() -> dict:
    batch_size = int(await _setting("jobs.attendance_alert_batch_size", 5000))
    return await evaluate_attendance_alerts(limit=max(1, min(batch_size, 10000)))


async def _setting(key: str, default):
    doc = await db.system_settings.find_one({"key": key})
    return doc.get("value", default) if doc else default


HANDLERS: dict[str, Callable[[], Awaitable[dict]]] = {
    "email_outbox": _run_email_outbox,
    "notification_cleanup": _run_notification_cleanup,
    "completion_reconciliation": _run_completion_reconciliation,
    "attendance_compliance_alerts": _run_attendance_compliance_alerts,
}


async def _acquire_lease(job_name: str) -> bool:
    now = _now()
    lease_until = now + timedelta(seconds=LEASE_SECONDS)
    result = await db.job_leases.update_one(
        {"job_name": job_name, "$or": [{"lease_until": {"$lte": now}}, {"lease_until": {"$exists": False}}, {"worker_id": WORKER_ID}]},
        {"$set": {"job_name": job_name, "worker_id": WORKER_ID, "lease_until": lease_until, "updated_at": now}},
        upsert=True,
    )
    return result.modified_count > 0 or result.upserted_id is not None


async def run_job(job_name: str, *, force: bool = False) -> dict:
    if job_name not in HANDLERS:
        raise ValueError(f"Unknown scheduled job: {job_name}")
    if not force and not await _acquire_lease(job_name):
        return {"job_name": job_name, "skipped": True, "reason": "another worker holds the lease"}

    started = _now()
    await _record_start(job_name, started)
    try:
        result = await HANDLERS[job_name]()
        await _record_success(job_name, started, result)
        return {"job_name": job_name, "skipped": False, "result": result}
    except Exception as exc:
        await _record_failure(job_name, started, exc)
        raise
    finally:
        await db.job_leases.update_one({"job_name": job_name, "worker_id": WORKER_ID}, {"$set": {"lease_until": _now(), "updated_at": _now()}})


async def list_job_statuses() -> list[dict]:
    docs = await db.scheduled_jobs.find({}).sort("job_name", 1).to_list(length=100)
    by_name = {d["job_name"]: d for d in docs}
    out = []
    for name, definition in JOB_DEFINITIONS.items():
        doc = by_name.get(name, {})
        out.append({
            "job_name": name,
            "description": definition["description"],
            "interval_seconds": definition["interval_seconds"],
            "status": doc.get("status", "never_run"),
            "last_run_at": doc.get("last_run_at"),
            "started_at": doc.get("started_at"),
            "finished_at": doc.get("finished_at"),
            "last_error": doc.get("last_error"),
            "last_result": doc.get("last_result"),
            "worker_id": doc.get("worker_id"),
        })
    return out


class JobScheduler:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self):
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="sixele-job-scheduler")

    async def stop(self):
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
        self._task = None

    async def _loop(self):
        while not self._stop.is_set():
            try:
                statuses = await list_job_statuses()
                now = _now()
                for status in statuses:
                    last = status.get("last_run_at")
                    interval = status["interval_seconds"]
                    if not last or (now - last).total_seconds() >= interval:
                        try:
                            await run_job(status["job_name"])
                        except Exception:
                            # The failure is persisted; keep the scheduler alive.
                            pass
            except Exception:
                # Scheduler must never bring down the FastAPI process.
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=10)
            except asyncio.TimeoutError:
                continue
