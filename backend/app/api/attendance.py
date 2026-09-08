from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.attendance import *
from app.services.authorization import require_permission
from app.services.audit import audit_log

router = APIRouter(prefix="/attendance", tags=["Attendance Management"])
VALID = {"present", "absent", "late", "excused"}


def oid(value: str):
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

async def get_session(session_id: str):
    s = await db.live_sessions.find_one({"_id": oid(session_id)})
    if not s: raise HTTPException(404, "Session not found")
    return s

async def build_session(s):
    members = await db.cohort_members.find({"cohort_id": s["cohort_id"], "status": "active"}).to_list(length=10000)
    ids = [m["learner_id"] for m in members]
    users = await db.users.find({"_id": {"$in": ids}}).to_list(length=len(ids)) if ids else []
    umap = {u["_id"]: u for u in users}
    records = await db.attendance.find({"session_id": s["_id"]}).to_list(length=10000)
    amap = {x["learner_id"]: x for x in records}
    rows=[]
    for lid in ids:
        a=amap.get(lid); u=umap.get(lid,{})
        rows.append(SessionAttendanceRecord(learner_id=str(lid), full_name=u.get("full_name", ""), email=u.get("email", ""), status=a.get("status") if a else None, note=a.get("note", "") if a else "", marked_at=a.get("marked_at") if a else None, marked_by=str(a["marked_by"]) if a and a.get("marked_by") else None))
    counts={k:sum(1 for r in records if r.get("status")==k) for k in VALID}
    return SessionAttendanceResponse(session_id=str(s["_id"]), cohort_id=str(s["cohort_id"]), session_title=s.get("title", ""), starts_at=s["starts_at"], ends_at=s["ends_at"], session_status=s.get("status", "scheduled"), attendance_locked=bool(s.get("attendance_locked", False)), total_learners=len(ids), marked_count=len(records), present_count=counts["present"], late_count=counts["late"], absent_count=counts["absent"], excused_count=counts["excused"], records=rows)

@router.get("/sessions/{session_id}", response_model=SessionAttendanceResponse)
async def session_attendance(session_id: str, user=Depends(get_current_user)):
    await require_permission(user, "attendance.view")
    return await build_session(await get_session(session_id))

@router.put("/sessions/{session_id}/learners/{learner_id}", response_model=SessionAttendanceRecord)
async def correct_attendance(session_id: str, learner_id: str, body: AttendanceCorrection, user=Depends(get_current_user)):
    await require_permission(user, "attendance.manage")
    s=await get_session(session_id)
    if s.get("attendance_locked") and not user.get("is_super_admin"):
        raise HTTPException(409, "Attendance is locked for this session")
    if body.status not in VALID: raise HTTPException(400, "Invalid attendance status")
    lid=oid(learner_id)
    member=await db.cohort_members.find_one({"cohort_id":s["cohort_id"],"learner_id":lid,"status":"active"})
    if not member: raise HTTPException(400, "Learner is not an active cohort member")
    now=datetime.now(timezone.utc)
    doc={"session_id":s["_id"],"cohort_id":s["cohort_id"],"learner_id":lid,"status":body.status,"note":body.note,"marked_at":now,"marked_by":user["_id"]}
    await db.attendance.update_one({"session_id":s["_id"],"learner_id":lid},{"$set":doc},upsert=True)
    await audit_log(actor_id=str(user["_id"]),action="attendance.correct",resource="live_session",resource_id=session_id,details={"learner_id":learner_id,"status":body.status})
    return SessionAttendanceRecord(learner_id=learner_id,status=body.status,note=body.note,marked_at=now,marked_by=str(user["_id"]))

@router.post("/sessions/{session_id}/lock", response_model=AttendanceLockResponse)
async def lock_attendance(session_id: str, user=Depends(get_current_user)):
    await require_permission(user, "attendance.manage")
    s=await get_session(session_id)
    now=datetime.now(timezone.utc)
    await db.live_sessions.update_one({"_id":s["_id"]},{"$set":{"attendance_locked":True,"attendance_locked_at":now,"attendance_locked_by":user["_id"],"updated_at":now}})
    await audit_log(actor_id=str(user["_id"]),action="attendance.lock",resource="live_session",resource_id=session_id,details={})
    return AttendanceLockResponse(session_id=session_id,locked=True,locked_at=now,locked_by=str(user["_id"]))

@router.post("/sessions/{session_id}/unlock", response_model=AttendanceLockResponse)
async def unlock_attendance(session_id: str, user=Depends(get_current_user)):
    await require_permission(user, "attendance.manage")
    if not user.get("is_super_admin"): raise HTTPException(403,"Only Super Admin can unlock attendance")
    s=await get_session(session_id); now=datetime.now(timezone.utc)
    await db.live_sessions.update_one({"_id":s["_id"]},{"$set":{"attendance_locked":False,"updated_at":now},"$unset":{"attendance_locked_at":"","attendance_locked_by":""}})
    await audit_log(actor_id=str(user["_id"]),action="attendance.unlock",resource="live_session",resource_id=session_id,details={})
    return AttendanceLockResponse(session_id=session_id,locked=False,locked_by=None,locked_at=None)

@router.get("/learners/{learner_id}", response_model=LearnerAttendanceResponse)
async def learner_history(learner_id: str, cohort_id: str, user=Depends(get_current_user)):
    await require_permission(user, "attendance.view")
    cid=oid(cohort_id); lid=oid(learner_id)
    member=await db.cohort_members.find_one({"cohort_id":cid,"learner_id":lid})
    if not member: raise HTTPException(404,"Learner is not a member of this cohort")
    sessions=await db.live_sessions.find({"cohort_id":cid}).sort("starts_at",1).to_list(length=10000)
    records=await db.attendance.find({"cohort_id":cid,"learner_id":lid}).to_list(length=10000); amap={r["session_id"]:r for r in records}
    rows=[LearnerAttendanceRow(session_id=str(s["_id"]),session_title=s.get("title",""),starts_at=s["starts_at"],status=amap.get(s["_id"],{}).get("status"),note=amap.get(s["_id"],{}).get("note","")) for s in sessions]
    attended=sum(1 for r in rows if r.status in {"present","late","excused"})
    return LearnerAttendanceResponse(cohort_id=cohort_id,learner_id=learner_id,attendance_rate=round(attended/len(sessions)*100,2) if sessions else 0,attended_sessions=attended,total_sessions=len(sessions),records=rows)
