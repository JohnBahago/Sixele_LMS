from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.course_versions import CourseVersionResponse, CreateRevisionRequest, RollbackRequest, CourseVersionCompareResponse
from app.services.authorization import require_course_permission
from app.services.audit import audit_log
from app.services.course_builder import validate_course_for_publishing
from app.services.course_versions import open_revision, publish_revision, get_version, version_response, restore_snapshot, create_snapshot_version

router = APIRouter(prefix="/course-versions", tags=["Course Versions"])

def oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value): raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

@router.get("/{course_id}", response_model=list[CourseVersionResponse])
async def list_versions(course_id: str, user=Depends(get_current_user)):
    cid=oid(course_id); course=await db.courses.find_one({"_id":cid})
    if not course: raise HTTPException(404,"Course not found")
    await require_course_permission(user,"courses.view",course)
    docs=await db.course_versions.find({"course_id":cid}).sort("version_number",-1).to_list(length=200)
    return [version_response(d) for d in docs]

@router.get("/{course_id}/{version_number}", response_model=CourseVersionResponse)
async def get_version_endpoint(course_id:str, version_number:int, user=Depends(get_current_user)):
    cid=oid(course_id); course=await db.courses.find_one({"_id":cid})
    if not course: raise HTTPException(404,"Course not found")
    await require_course_permission(user,"courses.view",course)
    return version_response(await get_version(cid,version_number))

@router.post("/{course_id}/revisions", response_model=CourseVersionResponse, status_code=201)
async def create_revision(course_id:str, body:CreateRevisionRequest, user=Depends(get_current_user)):
    cid=oid(course_id); course=await db.courses.find_one({"_id":cid})
    if not course: raise HTTPException(404,"Course not found")
    await require_course_permission(user,"courses.edit",course)
    updated=await open_revision(course,user["_id"],body.change_note)
    version=int(updated.get("version_number") or 1)
    doc=await create_snapshot_version(updated,version,user["_id"],"draft",body.change_note,version-1)
    await audit_log(actor_id=str(user["_id"]),action="course.revision.create",resource="course",resource_id=course_id,details={"version":version,"source_version":version-1,"change_note":body.change_note})
    return version_response(doc)

@router.post("/{course_id}/publish", response_model=CourseVersionResponse)
async def publish_revision_endpoint(course_id:str,user=Depends(get_current_user)):
    cid=oid(course_id); course=await db.courses.find_one({"_id":cid})
    if not course: raise HTTPException(404,"Course not found")
    await require_course_permission(user,"courses.publish",course)
    if course.get("status") == "published": raise HTTPException(409,"Course is already published. Open a new revision first.")
    validation=await validate_course_for_publishing(course)
    if not validation["valid"]: raise HTTPException(422,{"message":"Course cannot be published","validation":validation})
    doc=await publish_revision(course,user["_id"],course.get("revision_note", ""))
    from datetime import datetime, timezone
    now=datetime.now(timezone.utc)
    await db.courses.update_one({"_id":cid},{"$set":{"status":"published","published_version":course.get("version_number",1),"published_at":now,"published_by":user["_id"],"updated_at":now}})
    await audit_log(actor_id=str(user["_id"]),action="course.revision.publish",resource="course",resource_id=course_id,details={"version":course.get("version_number",1),"validation":validation["counts"]})
    return version_response(await db.course_versions.find_one({"_id":doc["_id"]}))

@router.post("/{course_id}/{version_number}/rollback", response_model=CourseVersionResponse)
async def rollback(course_id:str, version_number:int, body:RollbackRequest, user=Depends(get_current_user)):
    cid=oid(course_id); course=await db.courses.find_one({"_id":cid})
    if not course: raise HTTPException(404,"Course not found")
    await require_course_permission(user,"courses.edit",course)
    if course.get("status") == "published": raise HTTPException(409,"Published course is immutable. Open a revision before rollback.")
    target=await get_version(cid,version_number)
    restored=await restore_snapshot(course,target)
    new_version=int(restored.get("version_number") or version_number+1)
    doc=await create_snapshot_version(restored,new_version,user["_id"],"draft",body.change_note,version_number)
    await audit_log(actor_id=str(user["_id"]),action="course.revision.rollback",resource="course",resource_id=course_id,details={"from_version":version_number,"new_version":new_version,"change_note":body.change_note})
    return version_response(doc)

@router.get("/{course_id}/compare/{from_version}/{to_version}", response_model=CourseVersionCompareResponse)
async def compare(course_id:str,from_version:int,to_version:int,user=Depends(get_current_user)):
    cid=oid(course_id); course=await db.courses.find_one({"_id":cid})
    if not course: raise HTTPException(404,"Course not found")
    await require_course_permission(user,"courses.view",course)
    a,b=await get_version(cid,from_version),await get_version(cid,to_version)
    sa,sb=a["snapshot"],b["snapshot"]
    changes={}
    for field in ["title","short_description","description","category","level","duration_minutes","objectives","visibility","completion_rule","instructor_ids"]:
        av=sa["course"].get(field); bv=sb["course"].get(field)
        if av!=bv: changes[field]={"from":av,"to":bv}
    for name in sa.get("collections",{}):
        if len(sa.get("collections",{}).get(name,[])) != len(sb.get("collections",{}).get(name,[])):
            changes[name]={"from_count":len(sa.get("collections",{}).get(name,[])),"to_count":len(sb.get("collections",{}).get(name,[]))}
    return {"course_id":course_id,"from_version":from_version,"to_version":to_version,"changes":changes}
