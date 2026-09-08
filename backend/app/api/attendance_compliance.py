from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.attendance_compliance import CohortAttendanceComplianceResponse, AttendanceComplianceRow, AttendanceComplianceSummary
from app.services.authorization import require_permission
from app.services.attendance_compliance import get_threshold, learner_compliance

router = APIRouter(prefix="/attendance-compliance", tags=["Attendance Compliance"])

def oid(value: str):
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

@router.get("/cohorts/{cohort_id}", response_model=CohortAttendanceComplianceResponse)
async def cohort_compliance(cohort_id: str, user=Depends(get_current_user)):
    await require_permission(user, "attendance.view")
    cid = oid(cohort_id)
    cohort = await db.cohorts.find_one({"_id": cid})
    if not cohort:
        raise HTTPException(404, "Cohort not found")
    threshold = await get_threshold()
    members = await db.cohort_members.find({"cohort_id": cid, "status": "active"}).to_list(length=10000)
    learners = await db.users.find({"_id": {"$in": [m["learner_id"] for m in members]}}).to_list(length=10000) if members else []
    umap = {u["_id"]: u for u in learners}
    rows = []
    for m in members:
        lid = m["learner_id"]
        result = await learner_compliance(cid, lid, threshold)
        u = umap.get(lid, {})
        rows.append(AttendanceComplianceRow(learner_id=str(lid), full_name=u.get("full_name", ""), email=u.get("email", ""), **{k: result[k] for k in ["attended_sessions", "total_sessions", "attendance_rate", "status"]}))
    return CohortAttendanceComplianceResponse(cohort_id=cohort_id, threshold_percent=threshold, learners=rows)

@router.get("/cohorts/{cohort_id}/learners/{learner_id}", response_model=AttendanceComplianceSummary)
async def learner_compliance_endpoint(cohort_id: str, learner_id: str, user=Depends(get_current_user)):
    await require_permission(user, "attendance.view")
    cid, lid = oid(cohort_id), oid(learner_id)
    member = await db.cohort_members.find_one({"cohort_id": cid, "learner_id": lid})
    if not member:
        raise HTTPException(404, "Learner is not a member of this cohort")
    return AttendanceComplianceSummary(**await learner_compliance(cid, lid))
