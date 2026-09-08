from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.course_builder import CourseValidationResponse, CourseReviewRequest
from app.schemas.courses import CourseResponse, CompletionRule
from app.services.authorization import require_permission, require_course_permission
from app.services.audit import audit_log
from app.services.course_builder import validate_course_for_publishing

router = APIRouter(prefix="/course-builder", tags=["Course Builder"])

def oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

def course_response(doc: dict) -> CourseResponse:
    return CourseResponse(id=str(doc["_id"]), title=doc["title"], short_description=doc.get("short_description", ""), description=doc.get("description", ""), category=doc.get("category", ""), level=doc.get("level", "beginner"), duration_minutes=doc.get("duration_minutes"), objectives=doc.get("objectives", []), visibility=doc.get("visibility", "private"), status=doc.get("status", "draft"), completion_rule=CompletionRule(**doc.get("completion_rule", {})), instructor_ids=[str(x) for x in doc.get("instructor_ids", [])], created_by=str(doc["created_by"]), created_at=doc["created_at"], updated_at=doc["updated_at"])

@router.get("/{course_id}/validate", response_model=CourseValidationResponse)
async def validate(course_id: str, user=Depends(get_current_user)):
    await require_permission(user, "courses.view")
    course = await db.courses.find_one({"_id": oid(course_id)})
    if not course: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "courses.view", course)
    return await validate_course_for_publishing(course)

@router.post("/{course_id}/submit-review", response_model=CourseResponse)
async def submit_review(course_id: str, body: CourseReviewRequest, user=Depends(get_current_user)):
    await require_permission(user, "courses.edit")
    course = await db.courses.find_one({"_id": oid(course_id)})
    if not course: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "courses.edit", course)
    validation = await validate_course_for_publishing(course)
    if not validation["valid"]:
        raise HTTPException(422, {"message": "Course cannot be submitted for review", "validation": validation})
    now = datetime.now(timezone.utc)
    await db.courses.update_one({"_id": course["_id"]}, {"$set": {"status": "review", "review_note": body.note, "reviewed_submitted_at": now, "updated_at": now}})
    course.update({"status": "review", "review_note": body.note, "reviewed_submitted_at": now, "updated_at": now})
    await audit_log(actor_id=str(user["_id"]), action="course.submit_review", resource="course", resource_id=course_id, details={"note": body.note})
    return course_response(course)

@router.post("/{course_id}/publish", response_model=CourseResponse)
async def publish(course_id: str, user=Depends(get_current_user)):
    await require_permission(user, "courses.publish")
    course = await db.courses.find_one({"_id": oid(course_id)})
    if not course: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "courses.publish", course)
    validation = await validate_course_for_publishing(course)
    if not validation["valid"]:
        raise HTTPException(422, {"message": "Course cannot be published", "validation": validation})
    now = datetime.now(timezone.utc)
    await db.courses.update_one({"_id": course["_id"]}, {"$set": {"status": "published", "published_at": now, "published_by": user["_id"], "updated_at": now}})
    course.update({"status": "published", "published_at": now, "published_by": user["_id"], "updated_at": now})
    await audit_log(actor_id=str(user["_id"]), action="course.publish", resource="course", resource_id=course_id, details={"validation": validation["counts"]})
    return course_response(course)
