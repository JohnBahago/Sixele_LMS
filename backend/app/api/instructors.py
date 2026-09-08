from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.instructors import AssignInstructorsRequest, CourseInstructorResponse, CourseAccessResponse
from app.services.authorization import require_permission, require_course_permission
from app.services.audit import audit_log

router = APIRouter(prefix="/courses", tags=["Instructors"])

def oid(value: str):
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

async def get_course(course_id: str):
    course = await db.courses.find_one({"_id": oid(course_id)})
    if not course:
        raise HTTPException(404, "Course not found")
    return course

@router.get("/{course_id}/instructors", response_model=list[CourseInstructorResponse])
async def list_instructors(course_id: str, user=Depends(get_current_user)):
    course = await get_course(course_id)
    await require_course_permission(user, "instructors.view", course)
    ids = [ObjectId(str(x)) for x in course.get("instructor_ids", []) if ObjectId.is_valid(str(x))]
    docs = await db.users.find({"_id": {"$in": ids}}).sort("full_name", 1).to_list(length=200)
    return [CourseInstructorResponse(user_id=str(x["_id"]), full_name=x["full_name"], email=x["email"], is_active=x.get("is_active", True), role_ids=[str(r) for r in x.get("role_ids", [])], assigned_at=course.get("instructor_assignments", {}).get(str(x["_id"]))) for x in docs]

@router.put("/{course_id}/instructors", response_model=list[CourseInstructorResponse])
async def replace_instructors(course_id: str, body: AssignInstructorsRequest, user=Depends(get_current_user)):
    course = await get_course(course_id)
    await require_permission(user, "instructors.assign")
    requested = list(dict.fromkeys(body.user_ids))
    if any(not ObjectId.is_valid(x) for x in requested):
        raise HTTPException(400, "One or more instructor user ids are invalid")
    ids = [ObjectId(x) for x in requested]
    targets = await db.users.find({"_id": {"$in": ids}, "is_active": True, "is_super_admin": {"$ne": True}}).to_list(length=200)
    if len(targets) != len(ids):
        raise HTTPException(400, "All assigned instructors must be active, non-Super-Admin users")
    for target in targets:
        if not await __import__("app.services.authorization", fromlist=["has_permission"]).has_permission(target, "courses.view"):
            raise HTTPException(400, f"User {target['email']} does not have courses.view permission")
    now = datetime.now(timezone.utc)
    assignments = {str(x): now for x in ids}
    await db.courses.update_one({"_id": course["_id"]}, {"$set": {"instructor_ids": requested, "instructor_assignments": assignments, "updated_at": now}})
    await audit_log(actor_id=str(user["_id"]), action="course.instructors.replace", resource="course", resource_id=course_id, details={"user_ids": requested})
    return await list_instructors(course_id, user)

@router.post("/{course_id}/instructors/{user_id}", response_model=CourseAccessResponse, status_code=status.HTTP_201_CREATED)
async def assign_instructor(course_id: str, user_id: str, user=Depends(get_current_user)):
    course = await get_course(course_id)
    await require_permission(user, "instructors.assign")
    target = await db.users.find_one({"_id": oid(user_id)})
    if not target:
        raise HTTPException(404, "Instructor user not found")
    if not target.get("is_active", True) or target.get("is_super_admin"):
        raise HTTPException(400, "Instructor must be an active non-Super-Admin user")
    from app.services.authorization import has_permission
    if not await has_permission(target, "courses.view"):
        raise HTTPException(400, "Assigned user must have courses.view permission")
    ids = [str(x) for x in course.get("instructor_ids", [])]
    if user_id not in ids:
        ids.append(user_id)
    assignments = {str(k): v for k, v in course.get("instructor_assignments", {}).items()}
    assignments[user_id] = datetime.now(timezone.utc)
    now = datetime.now(timezone.utc)
    await db.courses.update_one({"_id": course["_id"]}, {"$set": {"instructor_ids": ids, "instructor_assignments": assignments, "updated_at": now}})
    await audit_log(actor_id=str(user["_id"]), action="course.instructor.assign", resource="course", resource_id=course_id, details={"user_id": user_id})
    return CourseAccessResponse(course_id=course_id, user_id=user_id, assigned=True, access_scope="assigned_course")

@router.delete("/{course_id}/instructors/{user_id}")
async def remove_instructor(course_id: str, user_id: str, user=Depends(get_current_user)):
    course = await get_course(course_id)
    await require_permission(user, "instructors.assign")
    ids = [str(x) for x in course.get("instructor_ids", []) if str(x) != user_id]
    assignments = {str(k): v for k, v in course.get("instructor_assignments", {}).items() if str(k) != user_id}
    now = datetime.now(timezone.utc)
    await db.courses.update_one({"_id": course["_id"]}, {"$set": {"instructor_ids": ids, "instructor_assignments": assignments, "updated_at": now}})
    await audit_log(actor_id=str(user["_id"]), action="course.instructor.remove", resource="course", resource_id=course_id, details={"user_id": user_id})
    return {"message": "Instructor removed", "course_id": course_id, "user_id": user_id}
