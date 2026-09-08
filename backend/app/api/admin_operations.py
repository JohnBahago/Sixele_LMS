from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.admin_operations import BulkUserStatusRequest, CourseStatusRequest, AdminQueueResponse, AdminOverviewResponse
from app.services.authorization import require_permission
from app.services.audit import audit_log

router = APIRouter(prefix="/admin/operations", tags=["Admin Operations"])

COURSE_STATUSES = {"draft", "setup", "review", "published", "archived"}

async def _ids(values: list[str]) -> list[ObjectId]:
    bad = [x for x in values if not ObjectId.is_valid(x)]
    if bad:
        raise HTTPException(400, f"Invalid ID: {bad[0]}")
    return [ObjectId(x) for x in values]

@router.get("/overview", response_model=AdminOverviewResponse)
async def overview(user=Depends(get_current_user)):
    await require_permission(user, "reports.view")
    return AdminOverviewResponse(
        users={
            "total": await db.users.count_documents({}),
            "active": await db.users.count_documents({"is_active": True}),
            "inactive": await db.users.count_documents({"is_active": False}),
            "super_admins": await db.users.count_documents({"is_super_admin": True}),
        },
        roles={
            "total": await db.roles.count_documents({}),
            "active": await db.roles.count_documents({"is_active": True}),
            "custom": await db.roles.count_documents({"is_system": {"$ne": True}}),
        },
        courses={
            "total": await db.courses.count_documents({}),
            "draft": await db.courses.count_documents({"status": "draft"}),
            "review": await db.courses.count_documents({"status": "review"}),
            "published": await db.courses.count_documents({"status": "published"}),
            "archived": await db.courses.count_documents({"status": "archived"}),
        },
        enrollments={
            "total": await db.enrollments.count_documents({}),
            "active": await db.enrollments.count_documents({"status": "active"}),
            "completed": await db.enrollments.count_documents({"status": "completed"}),
            "cancelled": await db.enrollments.count_documents({"status": "cancelled"}),
        },
        activities={"total": await db.activities.count_documents({}), "published": await db.activities.count_documents({"status": "published"})},
        assignments={"total": await db.assignments.count_documents({}), "published": await db.assignments.count_documents({"status": "published"}), "final_projects": await db.assignments.count_documents({"assignment_type": "final_project"})},
        assessments={"total": await db.quizzes.count_documents({}), "published": await db.quizzes.count_documents({"status": "published"})},
        submissions={"total": await db.submissions.count_documents({}), "pending": await db.submissions.count_documents({"status": {"$in": ["submitted", "under_review"]}}), "assignment_pending": await db.assignment_submissions.count_documents({"status": {"$in": ["submitted", "under_review"]}})},
        certificates={"issued": await db.certificates.count_documents({"status": "issued"}), "revoked": await db.certificates.count_documents({"status": "revoked"})},
        notifications={"total": await db.notifications.count_documents({}), "unread": await db.notifications.count_documents({"read": False})},
    )

@router.get("/queue", response_model=AdminQueueResponse)
async def queue(user=Depends(get_current_user)):
    await require_permission(user, "submissions.view")
    submissions = await db.submissions.count_documents({"status": {"$in": ["submitted", "under_review"]}})
    assignment_submissions = await db.assignment_submissions.count_documents({"status": {"$in": ["submitted", "under_review"]}})
    assessments = await db.quiz_attempts.count_documents({"status": "needs_manual_grading"})
    pending_enrollments = await db.enrollments.count_documents({"status": "pending"})
    total = submissions + assignment_submissions + assessments + pending_enrollments
    return AdminQueueResponse(submissions=submissions + assignment_submissions, assessments=assessments, pending_enrollments=pending_enrollments, total=total)

@router.post("/users/bulk-status")
async def bulk_user_status(body: BulkUserStatusRequest, user=Depends(get_current_user)):
    await require_permission(user, "users.manage")
    ids = await _ids(body.user_ids)
    protected = await db.users.count_documents({"_id": {"$in": ids}, "is_super_admin": True})
    if protected:
        raise HTTPException(403, "Super Admin accounts cannot be changed by this bulk operation")
    result = await db.users.update_many({"_id": {"$in": ids}}, {"$set": {"is_active": body.is_active, "updated_at": datetime.now(timezone.utc)}})
    await audit_log(actor_id=str(user["_id"]), action="user.bulk_status", resource="users", details={"user_ids": body.user_ids, "is_active": body.is_active, "modified": result.modified_count})
    return {"message": "User statuses updated", "requested": len(ids), "modified": result.modified_count, "is_active": body.is_active}

@router.patch("/courses/{course_id}/status")
async def course_status(course_id: str, body: CourseStatusRequest, user=Depends(get_current_user)):
    await require_permission(user, "courses.publish" if body.status == "published" else "courses.edit")
    if not ObjectId.is_valid(course_id):
        raise HTTPException(400, "Invalid course id")
    if body.status not in COURSE_STATUSES:
        raise HTTPException(400, f"Invalid course status. Allowed: {', '.join(sorted(COURSE_STATUSES))}")
    course = await db.courses.find_one({"_id": ObjectId(course_id)})
    if not course:
        raise HTTPException(404, "Course not found")
    old = course.get("status", "draft")
    now = datetime.now(timezone.utc)
    await db.courses.update_one({"_id": course["_id"]}, {"$set": {"status": body.status, "updated_at": now}})
    await audit_log(actor_id=str(user["_id"]), action="course.status_change", resource="course", resource_id=course_id, details={"from": old, "to": body.status})
    return {"course_id": course_id, "previous_status": old, "status": body.status}

@router.get("/courses/{course_id}/health")
async def course_health(course_id: str, user=Depends(get_current_user)):
    await require_permission(user, "courses.view")
    if not ObjectId.is_valid(course_id):
        raise HTTPException(400, "Invalid course id")
    cid = ObjectId(course_id)
    course = await db.courses.find_one({"_id": cid})
    if not course:
        raise HTTPException(404, "Course not found")
    modules = await db.modules.count_documents({"course_id": cid})
    lessons = await db.lessons.count_documents({"course_id": cid})
    required_lessons = await db.lessons.count_documents({"course_id": cid, "is_required": True})
    activities = await db.activities.count_documents({"course_id": cid})
    assessments = await db.quizzes.count_documents({"course_id": cid})
    assignments = await db.assignments.count_documents({"course_id": cid})
    instructors = len(course.get("instructor_ids", []))
    warnings = []
    if modules == 0: warnings.append("Course has no modules")
    if lessons == 0: warnings.append("Course has no lessons")
    if course.get("status") == "published" and instructors == 0: warnings.append("Published course has no instructor assigned")
    if course.get("completion_rule", {}).get("require_final_project") and assignments == 0: warnings.append("Final project is required but no assignment exists")
    return {"course_id": course_id, "title": course.get("title", ""), "status": course.get("status", "draft"), "counts": {"modules": modules, "lessons": lessons, "required_lessons": required_lessons, "activities": activities, "assessments": assessments, "assignments": assignments, "instructors": instructors}, "healthy": not warnings, "warnings": warnings}
