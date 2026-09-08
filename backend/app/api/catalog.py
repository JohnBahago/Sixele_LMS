from fastapi import APIRouter, Depends, HTTPException, Query
from bson import ObjectId
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.catalog import CatalogCourseResponse, BulkEnrollmentRequest, EnrollmentAdminResponse, EnrollmentBulkResult
from app.services.authorization import require_permission, require_course_permission
from app.services.audit import audit_log
from app.schemas.enrollments import EnrollmentResponse
from datetime import datetime, timezone

router = APIRouter(tags=["Catalog & Enrollment Administration"])

def oid(value: str):
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

async def catalog_doc(doc):
    count = await db.enrollments.count_documents({"course_id": doc["_id"], "status": {"$in": ["active", "completed"]}})
    return CatalogCourseResponse(id=str(doc["_id"]), title=doc["title"], short_description=doc.get("short_description", ""), description=doc.get("description", ""), category=doc.get("category", ""), level=doc.get("level", "beginner"), duration_minutes=doc.get("duration_minutes"), objectives=doc.get("objectives", []), visibility=doc.get("visibility", "catalog"), status=doc.get("status", "published"), instructor_ids=[str(x) for x in doc.get("instructor_ids", [])], enrolled_count=count, created_at=doc["created_at"])

@router.get("/catalog/courses", response_model=list[CatalogCourseResponse])
async def public_catalog(search: str | None = Query(None), category: str | None = Query(None), level: str | None = Query(None), user=Depends(get_current_user)):
    q = {"status": "published", "visibility": "catalog"}
    if category: q["category"] = category
    if level: q["level"] = level
    if search:
        q["$or"] = [{"title": {"$regex": search, "$options": "i"}}, {"short_description": {"$regex": search, "$options": "i"}}, {"description": {"$regex": search, "$options": "i"}}]
    docs = await db.courses.find(q).sort("created_at", -1).to_list(length=500)
    return [await catalog_doc(x) for x in docs]

@router.get("/catalog/courses/{course_id}", response_model=CatalogCourseResponse)
async def catalog_course(course_id: str, user=Depends(get_current_user)):
    doc = await db.courses.find_one({"_id": oid(course_id), "status": "published", "visibility": {"$in": ["catalog", "unlisted"]}})
    if not doc: raise HTTPException(404, "Published catalog course not found")
    return await catalog_doc(doc)

@router.get("/admin/enrollments", response_model=list[EnrollmentAdminResponse])
async def admin_enrollments(course_id: str | None = None, learner_id: str | None = None, status: str | None = None, search: str | None = None, user=Depends(get_current_user)):
    await require_permission(user, "enrollments.view")
    q = {}
    if course_id: q["course_id"] = oid(course_id)
    if learner_id: q["learner_id"] = oid(learner_id)
    if status: q["status"] = status
    docs = await db.enrollments.find(q).sort("enrolled_at", -1).to_list(length=1000)
    if not docs: return []
    learner_ids = list({x["learner_id"] for x in docs})
    course_ids = list({x["course_id"] for x in docs})
    users = await db.users.find({"_id": {"$in": learner_ids}}).to_list(length=1000)
    courses = await db.courses.find({"_id": {"$in": course_ids}}).to_list(length=1000)
    um = {x["_id"]: x for x in users}; cm = {x["_id"]: x for x in courses}
    out=[]
    for x in docs:
        u, c = um.get(x["learner_id"]), cm.get(x["course_id"])
        if not u or not c: continue
        if search and search.lower() not in " ".join([u.get("full_name", ""), u.get("email", ""), c.get("title", "")]).lower(): continue
        if not user.get("is_super_admin"):
            try: await require_course_permission(user, "enrollments.view", c)
            except HTTPException: continue
        out.append(EnrollmentAdminResponse(id=str(x["_id"]), learner_id=str(x["learner_id"]), learner_name=u.get("full_name", ""), learner_email=u.get("email", ""), course_id=str(x["course_id"]), course_title=c.get("title", ""), status=x.get("status", "active"), progress_percent=x.get("progress_percent", 0), enrolled_at=x["enrolled_at"], completed_at=x.get("completed_at"), updated_at=x["updated_at"]))
    return out

@router.post("/admin/enrollments/bulk", response_model=EnrollmentBulkResult)
async def bulk_enroll(body: BulkEnrollmentRequest, user=Depends(get_current_user)):
    await require_permission(user, "enrollments.manage")
    course = await db.courses.find_one({"_id": oid(body.course_id), "status": "published"})
    if not course: raise HTTPException(404, "Published course not found")
    if not user.get("is_super_admin"):
        await require_course_permission(user, "enrollments.manage", course)
    learner_ids = list(dict.fromkeys(body.learner_ids))
    result = EnrollmentBulkResult()
    now = datetime.now(timezone.utc)
    for raw in learner_ids:
        if not ObjectId.is_valid(raw): result.errors.append({"learner_id": raw, "error": "Invalid learner ID"}); continue
        lid = ObjectId(raw)
        learner = await db.users.find_one({"_id": lid, "is_active": True, "is_super_admin": {"$ne": True}})
        if not learner: result.errors.append({"learner_id": raw, "error": "Active learner not found"}); continue
        existing = await db.enrollments.find_one({"learner_id": lid, "course_id": course["_id"]})
        if existing and existing.get("status") != "cancelled": result.skipped.append(raw); continue
        if existing:
            await db.enrollments.update_one({"_id": existing["_id"]}, {"$set": {"status":"active", "progress_percent":0, "completed_at":None, "updated_at":now}})
            result.reactivated.append(raw); eid=str(existing["_id"]); action="enrollment.reactivate"
        else:
            doc={"learner_id":lid,"course_id":course["_id"],"status":"active","progress_percent":0,"enrolled_at":now,"completed_at":None,"updated_at":now}
            ins=await db.enrollments.insert_one(doc); eid=str(ins.inserted_id); result.created.append(raw); action="enrollment.create"
        await audit_log(actor_id=str(user["_id"]), action=action, resource="enrollment", resource_id=eid, details={"learner_id":raw,"course_id":body.course_id,"bulk":True})
    return result

@router.post("/admin/enrollments/{enrollment_id}/cancel", response_model=EnrollmentResponse)
async def cancel_enrollment(enrollment_id: str, user=Depends(get_current_user)):
    await require_permission(user, "enrollments.cancel")
    eid=oid(enrollment_id); e=await db.enrollments.find_one({"_id":eid})
    if not e: raise HTTPException(404,"Enrollment not found")
    course=await db.courses.find_one({"_id":e["course_id"]})
    if not course: raise HTTPException(404,"Course not found")
    if not user.get("is_super_admin"): await require_course_permission(user,"enrollments.cancel",course)
    now=datetime.now(timezone.utc)
    await db.enrollments.update_one({"_id":eid},{"$set":{"status":"cancelled","updated_at":now}})
    await audit_log(actor_id=str(user["_id"]),action="enrollment.cancel",resource="enrollment",resource_id=enrollment_id,details={"learner_id":str(e["learner_id"]),"course_id":str(e["course_id"])})
    e.update({"status":"cancelled","updated_at":now})
    return EnrollmentResponse(id=enrollment_id,course_id=str(e["course_id"]),learner_id=str(e["learner_id"]),status="cancelled",progress_percent=e.get("progress_percent",0),enrolled_at=e["enrolled_at"],completed_at=e.get("completed_at"),updated_at=now)
