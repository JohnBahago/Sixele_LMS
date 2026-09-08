from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.cohorts import *
from app.services.authorization import require_permission, require_course_permission
from app.services.audit import audit_log
from app.services.notifications import notify_event

router = APIRouter(prefix="/cohorts", tags=["Cohorts & Live Training"])

def oid(value: str):
    if not ObjectId.is_valid(value): raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

async def get_cohort(cohort_id: str):
    c = await db.cohorts.find_one({"_id": oid(cohort_id)})
    if not c: raise HTTPException(404, "Cohort not found")
    return c

async def get_course(course_id):
    c = await db.courses.find_one({"_id": oid(str(course_id))})
    if not c: raise HTTPException(404, "Course not found")
    return c

async def response(doc):
    course = await db.courses.find_one({"_id": doc["course_id"]})
    return CohortResponse(id=str(doc["_id"]), course_id=str(doc["course_id"]), course_title=(course or {}).get("title", ""), name=doc["name"], code=doc["code"], description=doc.get("description", ""), start_date=doc.get("start_date"), end_date=doc.get("end_date"), capacity=doc.get("capacity"), learner_count=await db.cohort_members.count_documents({"cohort_id":doc["_id"],"status":"active"}), instructor_ids=[str(x) for x in doc.get("instructor_ids",[])], status=doc.get("status","draft"), created_at=doc["created_at"], updated_at=doc["updated_at"])

@router.post("", response_model=CohortResponse, status_code=201)
async def create_cohort(body: CohortCreate, user=Depends(get_current_user)):
    await require_permission(user, "cohorts.create")
    course = await get_course(body.course_id)
    if body.start_date and body.end_date and body.end_date < body.start_date: raise HTTPException(400, "End date cannot be before start date")
    if await db.cohorts.find_one({"course_id":course["_id"],"code":body.code}): raise HTTPException(409, "Cohort code already exists for this course")
    now=datetime.now(timezone.utc)
    doc=body.model_dump(); doc.update({"course_id":course["_id"],"instructor_ids":[],"created_at":now,"updated_at":now})
    r=await db.cohorts.insert_one(doc); doc["_id"]=r.inserted_id
    await audit_log(actor_id=str(user["_id"]),action="cohort.create",resource="cohort",resource_id=str(r.inserted_id),details={"course_id":body.course_id,"name":body.name})
    return await response(doc)

@router.get("", response_model=list[CohortResponse])
async def list_cohorts(course_id:str|None=None,status_filter:str|None=Query(None,alias="status"),user=Depends(get_current_user)):
    await require_permission(user,"cohorts.view")
    q={}
    if course_id: q["course_id"]=oid(course_id)
    if status_filter: q["status"]=status_filter
    docs=await db.cohorts.find(q).sort("start_date",1).to_list(length=1000)
    return [await response(x) for x in docs]

@router.get("/{cohort_id}", response_model=CohortResponse)
async def get_cohort_endpoint(cohort_id:str,user=Depends(get_current_user)):
    await require_permission(user,"cohorts.view"); return await response(await get_cohort(cohort_id))

@router.patch("/{cohort_id}", response_model=CohortResponse)
async def update_cohort(cohort_id:str,body:CohortUpdate,user=Depends(get_current_user)):
    await require_permission(user,"cohorts.edit"); c=await get_cohort(cohort_id)
    updates={k:v for k,v in body.model_dump(exclude_unset=True).items() if v is not None}
    start=updates.get("start_date",c.get("start_date")); end=updates.get("end_date",c.get("end_date"))
    if start and end and end < start: raise HTTPException(400,"End date cannot be before start date")
    if "code" in updates and await db.cohorts.find_one({"_id":{"$ne":c["_id"]},"course_id":c["course_id"],"code":updates["code"]}): raise HTTPException(409,"Cohort code already exists for this course")
    updates["updated_at"]=datetime.now(timezone.utc)
    await db.cohorts.update_one({"_id":c["_id"]},{"$set":updates}); c.update(updates)
    await audit_log(actor_id=str(user["_id"]),action="cohort.update",resource="cohort",resource_id=cohort_id,details={"fields":list(updates.keys())})
    return await response(c)

@router.post("/{cohort_id}/members", response_model=dict)
async def add_members(cohort_id:str,body:CohortMembersRequest,user=Depends(get_current_user)):
    await require_permission(user,"cohorts.manage"); c=await get_cohort(cohort_id)
    ids=list(dict.fromkeys(body.learner_ids)); learners=await db.users.find({"_id":{"$in":[oid(x) for x in ids]},"is_active":True,"is_super_admin":{"$ne":True}}).to_list(length=len(ids))
    if len(learners)!=len(ids): raise HTTPException(400,"All learners must be active valid users")
    if c.get("capacity") is not None:
        existing=await db.cohort_members.count_documents({"cohort_id":c["_id"],"status":"active"}); new=0
        for x in ids:
            if not await db.cohort_members.find_one({"cohort_id":c["_id"],"learner_id":oid(x),"status":"active"}):
                new += 1
        if existing+new>c["capacity"]: raise HTTPException(409,"Cohort capacity exceeded")
    now=datetime.now(timezone.utc); added=[]
    for x in ids:
        lid=oid(x); existing=await db.cohort_members.find_one({"cohort_id":c["_id"],"learner_id":lid})
        if existing:
            if existing.get("status")=="active": continue
            await db.cohort_members.update_one({"_id":existing["_id"]},{"$set":{"status":"active","joined_at":now,"updated_at":now}}); added.append(x)
        else:
            await db.cohort_members.insert_one({"cohort_id":c["_id"],"learner_id":lid,"status":"active","joined_at":now,"updated_at":now}); added.append(x)
        await notify_event(event="cohort_membership",recipient_ids=[x],title="Added to training cohort",message=f"You have been added to the cohort {c['name']}.",notification_type="course",course_id=str(c["course_id"]),action_url=f"/learner/cohorts/{cohort_id}",actor_id=str(user["_id"]))
    await audit_log(actor_id=str(user["_id"]),action="cohort.members.add",resource="cohort",resource_id=cohort_id,details={"learner_ids":added})
    return {"added":added,"count":len(added)}

@router.delete("/{cohort_id}/members/{learner_id}")
async def remove_member(cohort_id:str,learner_id:str,user=Depends(get_current_user)):
    await require_permission(user,"cohorts.manage"); c=await get_cohort(cohort_id)
    result=await db.cohort_members.update_one({"cohort_id":c["_id"],"learner_id":oid(learner_id),"status":"active"},{"$set":{"status":"removed","updated_at":datetime.now(timezone.utc)}})
    if not result.modified_count: raise HTTPException(404,"Active cohort member not found")
    await audit_log(actor_id=str(user["_id"]),action="cohort.member.remove",resource="cohort",resource_id=cohort_id,details={"learner_id":learner_id})
    return {"message":"Learner removed from cohort"}

@router.put("/{cohort_id}/instructors", response_model=CohortResponse)
async def replace_instructors(cohort_id:str,body:CohortInstructorsRequest,user=Depends(get_current_user)):
    await require_permission(user,"cohorts.manage"); c=await get_cohort(cohort_id)
    ids=list(dict.fromkeys(body.instructor_ids)); targets=await db.users.find({"_id":{"$in":[oid(x) for x in ids]},"is_active":True,"is_super_admin":{"$ne":True}}).to_list(length=len(ids))
    if len(targets)!=len(ids): raise HTTPException(400,"All instructors must be active valid users")
    now=datetime.now(timezone.utc); await db.cohorts.update_one({"_id":c["_id"]},{"$set":{"instructor_ids":ids,"updated_at":now}}); c["instructor_ids"]=ids;c["updated_at"]=now
    await audit_log(actor_id=str(user["_id"]),action="cohort.instructors.replace",resource="cohort",resource_id=cohort_id,details={"instructor_ids":ids})
    return await response(c)

@router.post("/{cohort_id}/sessions",response_model=SessionResponse,status_code=201)
async def create_session(cohort_id:str,body:SessionCreate,user=Depends(get_current_user)):
    await require_permission(user,"sessions.create"); c=await get_cohort(cohort_id)
    if body.ends_at<=body.starts_at: raise HTTPException(400,"Session end must be after start")
    now=datetime.now(timezone.utc); doc=body.model_dump(); doc.update({"cohort_id":c["_id"],"created_at":now,"updated_at":now}); r=await db.live_sessions.insert_one(doc); doc["_id"]=r.inserted_id
    await audit_log(actor_id=str(user["_id"]),action="session.create",resource="live_session",resource_id=str(r.inserted_id),details={"cohort_id":cohort_id})
    return SessionResponse(id=str(r.inserted_id),cohort_id=cohort_id,**{k:doc[k] for k in ["title","starts_at","ends_at","location","meeting_url","notes","status","created_at","updated_at"]})

@router.get("/{cohort_id}/sessions",response_model=list[SessionResponse])
async def list_sessions(cohort_id:str,user=Depends(get_current_user)):
    await require_permission(user,"sessions.view"); c=await get_cohort(cohort_id); docs=await db.live_sessions.find({"cohort_id":c["_id"]}).sort("starts_at",1).to_list(length=1000)
    return [SessionResponse(id=str(x["_id"]),cohort_id=cohort_id,**{k:x.get(k) for k in ["title","starts_at","ends_at","location","meeting_url","notes","status","created_at","updated_at"]}) for x in docs]

@router.patch("/sessions/{session_id}",response_model=SessionResponse)
async def update_session(session_id:str,body:SessionUpdate,user=Depends(get_current_user)):
    await require_permission(user,"sessions.edit"); s=await db.live_sessions.find_one({"_id":oid(session_id)})
    if not s: raise HTTPException(404,"Session not found")
    updates={k:v for k,v in body.model_dump(exclude_unset=True).items() if v is not None}; start=updates.get("starts_at",s["starts_at"]); end=updates.get("ends_at",s["ends_at"])
    if end<=start: raise HTTPException(400,"Session end must be after start")
    updates["updated_at"]=datetime.now(timezone.utc); await db.live_sessions.update_one({"_id":s["_id"]},{"$set":updates}); s.update(updates)
    cohort = await get_cohort(str(s["cohort_id"]))
    changed_time = start != s.get("starts_at") or end != s.get("ends_at")
    changed_status = updates.get("status") is not None and updates.get("status") != s.get("status")
    if changed_time or changed_status:
        members = await db.cohort_members.find({"cohort_id":s["cohort_id"],"status":"active"}).to_list(length=5000)
        recipients = [str(m["learner_id"]) for m in members]
        if changed_status and updates.get("status") == "cancelled":
            title="Training session cancelled"; message=f"The session '{s.get('title','Training session')}' in {cohort.get('name','your cohort')} has been cancelled."
        elif changed_time:
            title="Training session rescheduled"; message=f"The session '{s.get('title','Training session')}' in {cohort.get('name','your cohort')} has been rescheduled to {start.isoformat()}."
        else:
            title="Training session updated"; message=f"The session '{s.get('title','Training session')}' in {cohort.get('name','your cohort')} has been updated."
        if recipients:
            await notify_event(event="session_update",recipient_ids=recipients,title=title,message=message,notification_type="attendance",course_id=str(cohort.get("course_id")) if cohort.get("course_id") else None,action_url=f"/learner/cohorts/{s['cohort_id']}",actor_id=str(user["_id"]))
    await audit_log(actor_id=str(user["_id"]),action="session.update",resource="live_session",resource_id=session_id,details={"fields":list(updates.keys())})
    return SessionResponse(id=str(s["_id"]),cohort_id=str(s["cohort_id"]),**{k:s.get(k) for k in ["title","starts_at","ends_at","location","meeting_url","notes","status","created_at","updated_at"]})

@router.post("/{cohort_id}/sessions/{session_id}/attendance",response_model=list[AttendanceResponse])
async def mark_attendance(cohort_id:str,session_id:str,body:AttendanceBulkRequest,user=Depends(get_current_user)):
    await require_permission(user,"attendance.manage"); c=await get_cohort(cohort_id); s=await db.live_sessions.find_one({"_id":oid(session_id),"cohort_id":c["_id"]})
    if not s: raise HTTPException(404,"Session not found for this cohort")
    if s.get("attendance_locked") and not user.get("is_super_admin"): raise HTTPException(409,"Attendance is locked for this session")
    member_ids={str(x["learner_id"]) for x in await db.cohort_members.find({"cohort_id":c["_id"],"status":"active"}).to_list(length=5000)}; now=datetime.now(timezone.utc); out=[]
    valid={"present","absent","late","excused"}
    for rec in body.records:
        if rec.learner_id not in member_ids: raise HTTPException(400,f"Learner {rec.learner_id} is not an active cohort member")
        if rec.status not in valid: raise HTTPException(400,"Invalid attendance status")
        doc={"session_id":s["_id"],"cohort_id":c["_id"],"learner_id":oid(rec.learner_id),"status":rec.status,"note":rec.note,"marked_at":now,"marked_by":user["_id"]}
        await db.attendance.update_one({"session_id":s["_id"],"learner_id":oid(rec.learner_id)},{"$set":doc},upsert=True); saved=await db.attendance.find_one({"session_id":s["_id"],"learner_id":oid(rec.learner_id)}); out.append(AttendanceResponse(id=str(saved["_id"]),session_id=session_id,cohort_id=cohort_id,learner_id=rec.learner_id,status=rec.status,note=rec.note,marked_at=now,marked_by=str(user["_id"])))
    await audit_log(actor_id=str(user["_id"]),action="attendance.mark",resource="live_session",resource_id=session_id,details={"count":len(out)})
    return out

@router.get("/{cohort_id}/dashboard",response_model=CohortDashboardResponse)
async def dashboard(cohort_id:str,user=Depends(get_current_user)):
    await require_permission(user,"cohorts.view"); c=await get_cohort(cohort_id); cr=await response(c)
    members=await db.cohort_members.find({"cohort_id":c["_id"],"status":"active"}).to_list(length=5000); learner_ids=[x["learner_id"] for x in members]
    enrollments=await db.enrollments.find({"course_id":c["course_id"],"learner_id":{"$in":learner_ids}}).to_list(length=5000)
    active=sum(1 for e in enrollments if e.get("status")=="active"); completed=sum(1 for e in enrollments if e.get("status")=="completed"); avg=round(sum(float(e.get("progress_percent",0)) for e in enrollments)/len(enrollments),2) if enrollments else 0
    now=datetime.now(timezone.utc); upcoming=await db.live_sessions.count_documents({"cohort_id":c["_id"],"starts_at":{"$gte":now},"status":"scheduled"})
    sessions=await db.live_sessions.find({"cohort_id":c["_id"]}).to_list(length=1000); session_ids=[x["_id"] for x in sessions]; att=await db.attendance.find({"cohort_id":c["_id"],"session_id":{"$in":session_ids}}).to_list(length=10000); rate=round(sum(1 for a in att if a.get("status") in {"present","late"})/len(att)*100,2) if att else 0
    return CohortDashboardResponse(cohort=cr,active_learners=active,completed_learners=completed,average_progress=avg,upcoming_sessions=upcoming,attendance_rate=rate)
