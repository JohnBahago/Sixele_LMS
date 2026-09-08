from datetime import datetime, timezone
from app.database.mongodb import db
from app.services.audit import audit_log
from app.services.notifications import notify_event

async def _setting(key, default):
    doc = await db.system_settings.find_one({"key": key})
    return doc.get("value", default) if doc else default

async def get_threshold(default=75.0):
    doc = await db.system_settings.find_one({"key": "attendance.minimum_percentage"})
    try: value = float(doc.get("value")) if doc else default
    except (TypeError, ValueError): value = default
    return max(0.0, min(100.0, value))

async def learner_compliance(cohort_id, learner_id, threshold=None):
    threshold = await get_threshold() if threshold is None else float(threshold)
    sessions = await db.live_sessions.find({"cohort_id": cohort_id, "status": {"$ne": "cancelled"}}).to_list(length=10000)
    if not sessions:
        return {"threshold_percent": threshold, "status": "not_started", "attendance_rate": 0.0, "attended_sessions": 0, "total_sessions": 0}
    ids = [s["_id"] for s in sessions]
    records = await db.attendance.find({"cohort_id": cohort_id, "learner_id": learner_id, "session_id": {"$in": ids}}).to_list(length=10000)
    attended = sum(1 for r in records if r.get("status") in {"present", "late"})
    rate = round(attended / len(sessions) * 100, 2)
    return {"threshold_percent": threshold, "status": "compliant" if rate >= threshold else "at_risk", "attendance_rate": rate, "attended_sessions": attended, "total_sessions": len(sessions)}

async def evaluate_attendance_alerts(limit=5000):
    enabled = await _setting("attendance.alerts_enabled", True)
    if not enabled:
        return {"processed": 0, "notified_learners": 0, "notified_instructors": 0, "skipped": True}
    threshold = await get_threshold()
    margin = max(0.0, min(100.0, float(await _setting("attendance.warning_margin", 5))))
    notify_instructors = await _setting("attendance.notify_instructors", True)
    members = await db.cohort_members.find({"status": "active"}).to_list(length=limit)
    learner_notified = instructor_notified = processed = 0
    now = datetime.now(timezone.utc)
    for member in members:
        cid, lid = member.get("cohort_id"), member.get("learner_id")
        if not cid or not lid: continue
        result = await learner_compliance(cid, lid, threshold)
        processed += 1
        key = {"cohort_id": cid, "learner_id": lid}
        previous = await db.attendance_compliance_alerts.find_one(key)
        previous_status = previous.get("status") if previous else None
        status = result["status"]
        early_warning = status == "compliant" and result["attendance_rate"] < threshold + margin
        state = "at_risk" if status == "at_risk" else ("warning" if early_warning else status)
        if previous and previous.get("state") == state:
            await db.attendance_compliance_alerts.update_one(key, {"$set": {"attendance_rate": result["attendance_rate"], "updated_at": now}})
            continue
        cohort = await db.cohorts.find_one({"_id": cid})
        cohort_name = (cohort or {}).get("name", "your training cohort")
        learner = await db.users.find_one({"_id": lid})
        if not learner: continue
        if state == "at_risk":
            title = "Attendance compliance warning"
            message = f"Your attendance in {cohort_name} is {result['attendance_rate']:.2f}%, below the required {threshold:.2f}%. Please attend upcoming sessions to remain compliant."
            await notify_event(event="attendance_risk", recipient_ids=[str(lid)], title=title, message=message, notification_type="attendance", course_id=str((cohort or {}).get("course_id")) if cohort and cohort.get("course_id") else None, action_url=f"/learner/cohorts/{cid}")
            learner_notified += 1
        elif state == "warning":
            title = "Attendance approaching compliance threshold"
            message = f"Your attendance in {cohort_name} is {result['attendance_rate']:.2f}%. The required minimum is {threshold:.2f}%."
            await notify_event(event="attendance_warning", recipient_ids=[str(lid)], title=title, message=message, notification_type="attendance", course_id=str((cohort or {}).get("course_id")) if cohort and cohort.get("course_id") else None, action_url=f"/learner/cohorts/{cid}")
            learner_notified += 1
        elif previous_status in {"at_risk", "warning"} and status == "compliant":
            await notify_event(event="attendance_recovered", recipient_ids=[str(lid)], title="Attendance compliance restored", message=f"Your attendance in {cohort_name} is now {result['attendance_rate']:.2f}%, meeting the required {threshold:.2f}%.", notification_type="attendance", course_id=str((cohort or {}).get("course_id")) if cohort and cohort.get("course_id") else None, action_url=f"/learner/cohorts/{cid}")
            learner_notified += 1
        if notify_instructors and cohort:
            instructor_ids = [str(x) for x in cohort.get("instructor_ids", [])]
            if instructor_ids and state in {"at_risk", "compliant"} and previous_status != status:
                name = learner.get("full_name", learner.get("email", "Learner"))
                if state == "at_risk":
                    msg = f"{name}'s attendance in {cohort_name} is {result['attendance_rate']:.2f}%, below the required {threshold:.2f}%."
                    title = "Learner attendance at risk"
                else:
                    msg = f"{name}'s attendance in {cohort_name} is now {result['attendance_rate']:.2f}%, meeting the required threshold."
                    title = "Learner attendance recovered"
                docs = await notify_event(event="attendance_instructor_alert", recipient_ids=instructor_ids, title=title, message=msg, notification_type="attendance", course_id=str(cohort.get("course_id")) if cohort.get("course_id") else None, action_url=f"/instructor/cohorts/{cid}")
                instructor_notified += len(docs)
        await db.attendance_compliance_alerts.update_one(key, {"$set": {"cohort_id": cid, "learner_id": lid, "status": status, "state": state, "attendance_rate": result["attendance_rate"], "threshold_percent": threshold, "updated_at": now}}, upsert=True)
    await audit_log(actor_id=None, action="attendance.compliance.alerts.run", resource="attendance_compliance", details={"processed": processed, "notified_learners": learner_notified, "notified_instructors": instructor_notified})
    return {"processed": processed, "notified_learners": learner_notified, "notified_instructors": instructor_notified, "threshold_percent": threshold}
