from datetime import datetime, timezone
from bson import ObjectId

from app.database.mongodb import db
from app.api.enrollments import calculate_progress
from app.services.audit import audit_log
from app.services.notifications import notify_event


async def _setting(key: str, default):
    doc = await db.system_settings.find_one({"key": key})
    return doc.get("value", default) if doc else default


async def evaluate_enrollment(enrollment_id: ObjectId | str, *, actor_id: str | None = None, auto_issue: bool | None = None) -> dict:
    """Recalculate progress, detect completion, notify once, and optionally issue a certificate."""
    if isinstance(enrollment_id, str):
        if not ObjectId.is_valid(enrollment_id):
            raise ValueError("Invalid enrollment ID")
        enrollment_id = ObjectId(enrollment_id)

    enrollment = await db.enrollments.find_one({"_id": enrollment_id})
    if not enrollment:
        raise ValueError("Enrollment not found")
    if enrollment.get("status") == "cancelled":
        return {"enrollment_id": str(enrollment_id), "completed": False, "cancelled": True, "certificate_issued": False}

    was_completed = enrollment.get("status") == "completed" or bool(enrollment.get("completed_at"))
    progress = await calculate_progress(dict(enrollment))
    completed = bool(progress.completed)
    newly_completed = completed and not was_completed
    certificate_issued = False
    certificate = None

    if newly_completed:
        await audit_log(
            actor_id=actor_id,
            action="course.completed",
            resource="enrollment",
            resource_id=str(enrollment_id),
            details={"course_id": str(enrollment["course_id"]), "learner_id": str(enrollment["learner_id"]), "progress_percent": progress.progress_percent},
        )
        await notify_event(
            event="completion",
            recipient_ids=[str(enrollment["learner_id"])],
            title="Course completed",
            message="Congratulations! You have completed all required course components.",
            notification_type="completion",
            course_id=str(enrollment["course_id"]),
            action_url=f"/learner/courses/{enrollment['course_id']}",
            actor_id=actor_id,
        )

    if auto_issue is None:
        auto_issue = bool(await _setting("certificates.auto_issue_on_completion", True))

    if completed and auto_issue:
        # Lazy import avoids the certificates <-> enrollment progress dependency becoming circular.
        from app.api.certificates import issue_certificate_for_enrollment
        certificate = await issue_certificate_for_enrollment(enrollment, actor_id=actor_id, automatic=True)
        certificate_issued = certificate is not None

    return {
        "enrollment_id": str(enrollment_id),
        "course_id": str(enrollment["course_id"]),
        "learner_id": str(enrollment["learner_id"]),
        "progress_percent": progress.progress_percent,
        "completed": completed,
        "newly_completed": newly_completed,
        "certificate_issued": certificate_issued,
        "certificate_number": certificate.get("certificate_number") if certificate else None,
    }


async def reconcile_active_enrollments(limit: int = 250) -> dict:
    """Re-evaluate active enrollments for scheduled completion/certificate automation."""
    processed = completed = certificates = errors = 0
    cursor = db.enrollments.find({"status": "active"}).sort("updated_at", 1).limit(max(1, min(limit, 1000)))
    async for enrollment in cursor:
        processed += 1
        try:
            result = await evaluate_enrollment(enrollment["_id"], actor_id=None, auto_issue=True)
            completed += int(result.get("newly_completed", False))
            certificates += int(result.get("certificate_issued", False))
        except Exception:
            errors += 1
    return {"processed": processed, "completed": completed, "certificates_issued": certificates, "errors": errors}
