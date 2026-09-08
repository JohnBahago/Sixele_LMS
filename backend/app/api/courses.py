from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.courses import (
    CourseCreate, CourseUpdate, CourseResponse, CourseStatus, CompletionRule,
    ModuleCreate, ModuleUpdate, ModuleResponse,
    LessonCreate, LessonUpdate, LessonResponse,
    ResourceCreate, ResourceResponse,
)
from app.services.authorization import require_permission, require_course_permission, course_visibility_filter
from app.services.audit import audit_log
from app.services.course_builder import validate_course_for_publishing

router = APIRouter(prefix="/courses", tags=["Courses"])

def oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

def course_response(doc: dict) -> CourseResponse:
    return CourseResponse(
        id=str(doc["_id"]), title=doc["title"], short_description=doc.get("short_description", ""),
        description=doc.get("description", ""), category=doc.get("category", ""), level=doc.get("level", "beginner"),
        duration_minutes=doc.get("duration_minutes"), objectives=doc.get("objectives", []),
        visibility=doc.get("visibility", "private"), status=doc.get("status", "draft"),
        completion_rule=CompletionRule(**doc.get("completion_rule", {})),
        instructor_ids=[str(x) for x in doc.get("instructor_ids", [])], created_by=str(doc["created_by"]),
        created_at=doc["created_at"], updated_at=doc["updated_at"],
    )

def module_response(doc: dict) -> ModuleResponse:
    return ModuleResponse(id=str(doc["_id"]), course_id=str(doc["course_id"]), title=doc["title"], description=doc.get("description", ""), order=doc.get("order", 0), created_at=doc["created_at"], updated_at=doc["updated_at"])

def lesson_response(doc: dict) -> LessonResponse:
    return LessonResponse(id=str(doc["_id"]), course_id=str(doc["course_id"]), module_id=str(doc["module_id"]), title=doc["title"], description=doc.get("description", ""), lesson_type=doc.get("lesson_type", "reading"), content=doc.get("content", ""), duration_minutes=doc.get("duration_minutes"), order=doc.get("order", 0), is_required=doc.get("is_required", True), video_url=doc.get("video_url"), release_at=doc.get("release_at"), prerequisite_lesson_ids=[str(x) for x in doc.get("prerequisite_lesson_ids", [])], created_at=doc["created_at"], updated_at=doc["updated_at"])

@router.get("", response_model=list[CourseResponse])
async def list_courses(status_filter: CourseStatus | None = Query(None, alias="status"), search: str | None = None, user=Depends(get_current_user)):
    await require_permission(user, "courses.view")
    query = await course_visibility_filter(user, "courses.view")
    if status_filter:
        query["status"] = status_filter.value
    if search:
        query["$or"] = [{"title": {"$regex": search, "$options": "i"}}, {"description": {"$regex": search, "$options": "i"}}]
    docs = await db.courses.find(query).sort("updated_at", -1).to_list(length=200)
    return [course_response(x) for x in docs]

@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(body: CourseCreate, user=Depends(get_current_user)):
    await require_permission(user, "courses.create")
    now = datetime.now(timezone.utc)
    doc = body.model_dump()
    doc.update({"status": "draft", "instructor_ids": [], "created_by": user["_id"], "created_at": now, "updated_at": now})
    result = await db.courses.insert_one(doc)
    doc["_id"] = result.inserted_id
    await audit_log(actor_id=str(user["_id"]), action="course.create", resource="course", resource_id=str(result.inserted_id), details={"title": body.title})
    return course_response(doc)

@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(course_id: str, user=Depends(get_current_user)):
    await require_permission(user, "courses.view")
    doc = await db.courses.find_one({"_id": oid(course_id)})
    if not doc: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "courses.view", doc)
    return course_response(doc)

@router.patch("/{course_id}", response_model=CourseResponse)
async def update_course(course_id: str, body: CourseUpdate, user=Depends(get_current_user)):
    await require_permission(user, "courses.edit")
    _id = oid(course_id); doc = await db.courses.find_one({"_id": _id})
    if not doc: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "courses.edit", doc)
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "completion_rule" in updates: updates["completion_rule"] = body.completion_rule.model_dump()
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.courses.update_one({"_id": _id}, {"$set": updates})
    doc.update(updates)
    await audit_log(actor_id=str(user["_id"]), action="course.update", resource="course", resource_id=course_id)
    return course_response(doc)

@router.post("/{course_id}/publish", response_model=CourseResponse)
async def publish_course(course_id: str, user=Depends(get_current_user)):
    await require_permission(user, "courses.publish")
    _id = oid(course_id); doc = await db.courses.find_one({"_id": _id})
    if not doc: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "courses.publish", doc)
    validation = await validate_course_for_publishing(doc)
    if not validation["valid"]:
        raise HTTPException(422, {"message": "Course cannot be published", "validation": validation})
    now = datetime.now(timezone.utc)
    await db.courses.update_one({"_id": _id}, {"$set": {"status": "published", "published_at": now, "published_by": user["_id"], "updated_at": now}})
    doc.update({"status": "published", "published_at": now, "published_by": user["_id"], "updated_at": now})
    await audit_log(actor_id=str(user["_id"]), action="course.publish", resource="course", resource_id=course_id, details={"validation": validation["counts"]})
    return course_response(doc)

@router.post("/{course_id}/archive", response_model=CourseResponse)
async def archive_course(course_id: str, user=Depends(get_current_user)):
    await require_permission(user, "courses.archive")
    _id = oid(course_id); doc = await db.courses.find_one({"_id": _id})
    if not doc: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "courses.archive", doc)
    now = datetime.now(timezone.utc)
    await db.courses.update_one({"_id": _id}, {"$set": {"status": "archived", "updated_at": now}})
    doc.update({"status": "archived", "updated_at": now})
    await audit_log(actor_id=str(user["_id"]), action="course.archive", resource="course", resource_id=course_id)
    return course_response(doc)

@router.delete("/{course_id}", status_code=204)
async def delete_course(course_id: str, user=Depends(get_current_user)):
    await require_permission(user, "courses.delete")
    _id = oid(course_id)
    if not await db.courses.find_one({"_id": _id}): raise HTTPException(404, "Course not found")
    await db.courses.delete_one({"_id": _id}); await db.modules.delete_many({"course_id": _id}); await db.lessons.delete_many({"course_id": _id}); await db.resources.delete_many({"course_id": _id})
    await audit_log(actor_id=str(user["_id"]), action="course.delete", resource="course", resource_id=course_id)

@router.get("/{course_id}/modules", response_model=list[ModuleResponse])
async def list_modules(course_id: str, user=Depends(get_current_user)):
    await require_permission(user, "modules.view")
    _id = oid(course_id)
    course = await db.courses.find_one({"_id": _id})
    if not course: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "modules.view", course)
    docs = await db.modules.find({"course_id": _id}).sort("order", 1).to_list(length=500)
    return [module_response(x) for x in docs]

@router.post("/{course_id}/modules", response_model=ModuleResponse, status_code=201)
async def create_module(course_id: str, body: ModuleCreate, user=Depends(get_current_user)):
    await require_permission(user, "modules.create")
    _id = oid(course_id)
    course = await db.courses.find_one({"_id": _id})
    if not course: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "modules.create", course)
    now = datetime.now(timezone.utc); doc = {"course_id": _id, **body.model_dump(), "created_at": now, "updated_at": now}
    result = await db.modules.insert_one(doc); doc["_id"] = result.inserted_id
    await audit_log(actor_id=str(user["_id"]), action="module.create", resource="module", resource_id=str(result.inserted_id), details={"course_id": course_id})
    return module_response(doc)

@router.patch("/{course_id}/modules/{module_id}", response_model=ModuleResponse)
async def update_module(course_id: str, module_id: str, body: ModuleUpdate, user=Depends(get_current_user)):
    await require_permission(user, "modules.edit")
    c_id, m_id = oid(course_id), oid(module_id); course = await db.courses.find_one({"_id": c_id}); doc = await db.modules.find_one({"_id": m_id, "course_id": c_id})
    if not course: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "modules.edit", course)
    if not doc: raise HTTPException(404, "Module not found")
    updates = {k: v for k,v in body.model_dump(exclude_unset=True).items() if v is not None}; updates["updated_at"] = datetime.now(timezone.utc)
    await db.modules.update_one({"_id": m_id}, {"$set": updates}); doc.update(updates)
    return module_response(doc)

@router.delete("/{course_id}/modules/{module_id}", status_code=204)
async def delete_module(course_id: str, module_id: str, user=Depends(get_current_user)):
    await require_permission(user, "modules.delete")
    c_id, m_id = oid(course_id), oid(module_id)
    course = await db.courses.find_one({"_id": c_id})
    if not course: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "modules.delete", course)
    if not await db.modules.find_one({"_id": m_id, "course_id": c_id}): raise HTTPException(404, "Module not found")
    await db.modules.delete_one({"_id": m_id}); await db.lessons.delete_many({"module_id": m_id}); await db.resources.delete_many({"module_id": m_id})

@router.get("/{course_id}/modules/{module_id}/lessons", response_model=list[LessonResponse])
async def list_lessons(course_id: str, module_id: str, user=Depends(get_current_user)):
    await require_permission(user, "lessons.view")
    c_id, m_id = oid(course_id), oid(module_id)
    course = await db.courses.find_one({"_id": c_id})
    if not course: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "lessons.view", course)
    if not await db.modules.find_one({"_id": m_id, "course_id": c_id}): raise HTTPException(404, "Module not found")
    docs = await db.lessons.find({"module_id": m_id, "course_id": c_id}).sort("order", 1).to_list(length=500)
    return [lesson_response(x) for x in docs]

@router.post("/{course_id}/modules/{module_id}/lessons", response_model=LessonResponse, status_code=201)
async def create_lesson(course_id: str, module_id: str, body: LessonCreate, user=Depends(get_current_user)):
    await require_permission(user, "lessons.create")
    c_id, m_id = oid(course_id), oid(module_id)
    course = await db.courses.find_one({"_id": c_id})
    if not course: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "lessons.create", course)
    if not await db.modules.find_one({"_id": m_id, "course_id": c_id}): raise HTTPException(404, "Module not found")
    now = datetime.now(timezone.utc); data = body.model_dump(); data["lesson_type"] = body.lesson_type.value
    doc = {"course_id": c_id, "module_id": m_id, **data, "created_at": now, "updated_at": now}
    result = await db.lessons.insert_one(doc); doc["_id"] = result.inserted_id
    return lesson_response(doc)

@router.patch("/{course_id}/modules/{module_id}/lessons/{lesson_id}", response_model=LessonResponse)
async def update_lesson(course_id: str, module_id: str, lesson_id: str, body: LessonUpdate, user=Depends(get_current_user)):
    await require_permission(user, "lessons.edit")
    c_id, m_id, l_id = oid(course_id), oid(module_id), oid(lesson_id)
    course = await db.courses.find_one({"_id": c_id})
    if not course: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "lessons.edit", course)
    doc = await db.lessons.find_one({"_id": l_id, "course_id": c_id, "module_id": m_id})
    if not doc: raise HTTPException(404, "Lesson not found")
    updates = {k:v for k,v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "lesson_type" in updates: updates["lesson_type"] = body.lesson_type.value
    updates["updated_at"] = datetime.now(timezone.utc); await db.lessons.update_one({"_id": l_id}, {"$set": updates}); doc.update(updates)
    return lesson_response(doc)

@router.delete("/{course_id}/modules/{module_id}/lessons/{lesson_id}", status_code=204)
async def delete_lesson(course_id: str, module_id: str, lesson_id: str, user=Depends(get_current_user)):
    await require_permission(user, "lessons.delete")
    c_id, m_id, l_id = oid(course_id), oid(module_id), oid(lesson_id)
    course = await db.courses.find_one({"_id": c_id})
    if not course: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "lessons.delete", course)
    if not await db.lessons.find_one({"_id": l_id, "course_id": c_id, "module_id": m_id}): raise HTTPException(404, "Lesson not found")
    await db.lessons.delete_one({"_id": l_id}); await db.resources.delete_many({"lesson_id": l_id})

@router.post("/{course_id}/modules/{module_id}/resources", response_model=ResourceResponse, status_code=201)
async def create_resource(course_id: str, module_id: str, body: ResourceCreate, lesson_id: str | None = None, user=Depends(get_current_user)):
    await require_permission(user, "content.upload")
    c_id, m_id = oid(course_id), oid(module_id)
    course = await db.courses.find_one({"_id": c_id})
    if not course: raise HTTPException(404, "Course not found")
    await require_course_permission(user, "content.upload", course)
    if not await db.modules.find_one({"_id": m_id, "course_id": c_id}): raise HTTPException(404, "Module not found")
    l_id = oid(lesson_id) if lesson_id else None
    if l_id and not await db.lessons.find_one({"_id": l_id, "module_id": m_id, "course_id": c_id}): raise HTTPException(404, "Lesson not found")
    doc = {"course_id": c_id, "module_id": m_id, "lesson_id": l_id, **body.model_dump(), "created_at": datetime.now(timezone.utc)}
    result = await db.resources.insert_one(doc); doc["_id"] = result.inserted_id
    return ResourceResponse(id=str(doc["_id"]), course_id=course_id, module_id=module_id, lesson_id=lesson_id, name=doc["name"], resource_type=doc["resource_type"], url=doc.get("url"), file_url=doc.get("file_url"), description=doc.get("description", ""), created_at=doc["created_at"])
