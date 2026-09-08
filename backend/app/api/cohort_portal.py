from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.cohort_portal import *
from app.services.authorization import has_course_permission

learner_router = APIRouter(prefix="/learner/cohorts", tags=["Learner Cohort Portal"])
instructor_router = APIRouter(prefix="/instructor/cohorts", tags=["Instructor Cohort Portal"])


def oid(value: str):
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)


async def cohort_summary(c):
    course = await db.courses.find_one({"_id": c["course_id"]})
    return PortalCohortSummary(
        id=str(c["_id"]), name=c.get("name", ""), code=c.get("code", ""),
        status=c.get("status", "draft"), start_date=c.get("start_date"), end_date=c.get("end_date"),
        course=PortalCourseRef(id=str(c["course_id"]), title=(course or {}).get("title", "")),
        learner_count=await db.cohort_members.count_documents({"cohort_id": c["_id"], "status": "active"}),
    )


async def session_response(s, learner_id=None):
    attendance_status = None
    if learner_id:
        a = await db.attendance.find_one({"session_id": s["_id"], "learner_id": learner_id})
        attendance_status = a.get("status") if a else None
    return PortalSession(
        id=str(s["_id"]), cohort_id=str(s["cohort_id"]), title=s.get("title", ""),
        starts_at=s["starts_at"], ends_at=s["ends_at"], location=s.get("location", ""),
        meeting_url=s.get("meeting_url"), notes=s.get("notes", ""), status=s.get("status", "scheduled"),
        attendance_status=attendance_status,
    )


async def attendance_stats(cohort_id, learner_id):
    sessions = await db.live_sessions.find({"cohort_id": cohort_id}).to_list(length=5000)
    ids = [s["_id"] for s in sessions]
    if not ids:
        return 0, 0, 0, 0.0
    records = await db.attendance.find({"cohort_id": cohort_id, "learner_id": learner_id, "session_id": {"$in": ids}}).to_list(length=5000)
    present = sum(1 for x in records if x.get("status") == "present")
    attended = sum(1 for x in records if x.get("status") in {"present", "late", "excused"})
    rate = round(attended / len(sessions) * 100, 2)
    return present, attended, len(sessions), rate


async def learner_membership(cohort_id, user):
    c = await db.cohorts.find_one({"_id": oid(cohort_id)})
    if not c:
        raise HTTPException(404, "Cohort not found")
    member = await db.cohort_members.find_one({"cohort_id": c["_id"], "learner_id": user["_id"], "status": "active"})
    if not member:
        raise HTTPException(403, "You are not an active member of this cohort")
    return c


async def instructor_access(c, user):
    if user.get("is_super_admin"):
        return
    if str(user["_id"]) in {str(x) for x in c.get("instructor_ids", [])}:
        return
    course = await db.courses.find_one({"_id": c["course_id"]})
    if course and await has_course_permission(user, "courses.view", course):
        return
    raise HTTPException(403, "You are not assigned to this cohort")


@learner_router.get("", response_model=LearnerCohortPortalResponse)
async def learner_cohorts(user=Depends(get_current_user)):
    memberships = await db.cohort_members.find({"learner_id": user["_id"], "status": "active"}).to_list(length=1000)
    cohorts = []
    for m in memberships:
        c = await db.cohorts.find_one({"_id": m["cohort_id"]})
        if c:
            cohorts.append(await cohort_summary(c))
    now = datetime.now(timezone.utc)
    sessions = await db.live_sessions.find({"cohort_id": {"$in": [m["cohort_id"] for m in memberships]}, "starts_at": {"$gte": now}, "status": "scheduled"}).sort("starts_at", 1).to_list(length=50) if memberships else []
    upcoming = [await session_response(s, user["_id"]) for s in sessions]
    return LearnerCohortPortalResponse(learner_id=str(user["_id"]), cohorts=cohorts, upcoming_sessions=upcoming)


@learner_router.get("/{cohort_id}", response_model=LearnerCohortDetail)
async def learner_cohort_detail(cohort_id: str, user=Depends(get_current_user)):
    c = await learner_membership(cohort_id, user)
    enrollment = await db.enrollments.find_one({"learner_id": user["_id"], "course_id": c["course_id"], "status": {"$ne": "cancelled"}})
    if not enrollment:
        raise HTTPException(404, "Course enrollment not found")
    present, attended, total, rate = await attendance_stats(c["_id"], user["_id"])
    now = datetime.now(timezone.utc)
    docs = await db.live_sessions.find({"cohort_id": c["_id"]}).sort("starts_at", 1).to_list(length=5000)
    sessions = [await session_response(s, user["_id"]) for s in docs]
    upcoming = sum(1 for s in docs if s.get("starts_at") >= now and s.get("status") == "scheduled")
    return LearnerCohortDetail(cohort=await cohort_summary(c), progress_percent=float(enrollment.get("progress_percent", 0)), enrollment_status=enrollment.get("status", "active"), attendance_rate=rate, present_sessions=present, attended_sessions=attended, total_sessions=total, upcoming_sessions=upcoming, sessions=sessions)


@learner_router.get("/{cohort_id}/sessions", response_model=list[PortalSession])
async def learner_sessions(cohort_id: str, status: str | None = Query(None), user=Depends(get_current_user)):
    c = await learner_membership(cohort_id, user)
    q = {"cohort_id": c["_id"]}
    if status:
        q["status"] = status
    docs = await db.live_sessions.find(q).sort("starts_at", 1).to_list(length=5000)
    return [await session_response(s, user["_id"]) for s in docs]


@instructor_router.get("", response_model=InstructorCohortPortalResponse)
async def instructor_cohorts(user=Depends(get_current_user)):
    if user.get("is_super_admin"):
        docs = await db.cohorts.find({}).sort("start_date", 1).to_list(length=1000)
    else:
        docs = await db.cohorts.find({"instructor_ids": str(user["_id"])}).sort("start_date", 1).to_list(length=1000)
        if not docs:
            # Course-scoped instructors may manage cohorts belonging to their assigned courses.
            course_filter = {"instructor_ids": str(user["_id"])}
            courses = await db.courses.find(course_filter, {"_id": 1}).to_list(length=2000)
            if courses:
                docs = await db.cohorts.find({"course_id": {"$in": [x["_id"] for x in courses]}}).sort("start_date", 1).to_list(length=1000)
    cohorts = [await cohort_summary(c) for c in docs]
    now = datetime.now(timezone.utc)
    ids = [c["_id"] for c in docs]
    sessions = await db.live_sessions.find({"cohort_id": {"$in": ids}, "starts_at": {"$gte": now}, "status": "scheduled"}).sort("starts_at", 1).to_list(length=50) if ids else []
    return InstructorCohortPortalResponse(instructor_id=str(user["_id"]), cohorts=cohorts, upcoming_sessions=[await session_response(s) for s in sessions])


@instructor_router.get("/{cohort_id}", response_model=InstructorCohortDetail)
async def instructor_cohort_detail(cohort_id: str, user=Depends(get_current_user)):
    c = await db.cohorts.find_one({"_id": oid(cohort_id)})
    if not c:
        raise HTTPException(404, "Cohort not found")
    await instructor_access(c, user)
    members = await db.cohort_members.find({"cohort_id": c["_id"], "status": "active"}).to_list(length=5000)
    learner_ids = [m["learner_id"] for m in members]
    users = await db.users.find({"_id": {"$in": learner_ids}}).to_list(length=len(learner_ids)) if learner_ids else []
    umap = {u["_id"]: u for u in users}
    course = await db.courses.find_one({"_id": c["course_id"]})
    course_enrollments = await db.enrollments.find({"course_id": c["course_id"], "learner_id": {"$in": learner_ids}, "status": {"$ne": "cancelled"}}).to_list(length=5000) if learner_ids else []
    emap = {e["learner_id"]: e for e in course_enrollments}
    learners = []
    for lid in learner_ids:
        u = umap.get(lid, {})
        e = emap.get(lid, {})
        present, attended, total, rate = await attendance_stats(c["_id"], lid)
        learners.append(InstructorCohortLearner(learner_id=str(lid), full_name=u.get("full_name", ""), email=u.get("email", ""), enrollment_status=e.get("status", "active"), progress_percent=float(e.get("progress_percent", 0)), attendance_rate=rate, present_sessions=present, attended_sessions=attended, total_sessions=total))
    docs = await db.live_sessions.find({"cohort_id": c["_id"]}).sort("starts_at", 1).to_list(length=5000)
    now = datetime.now(timezone.utc)
    upcoming = [await session_response(s) for s in docs if s.get("starts_at") >= now and s.get("status") == "scheduled"]
    avg_progress = round(sum(x.progress_percent for x in learners) / len(learners), 2) if learners else 0
    avg_attendance = round(sum(x.attendance_rate for x in learners) / len(learners), 2) if learners else 0
    return InstructorCohortDetail(cohort=await cohort_summary(c), learners=learners, upcoming_sessions=upcoming, total_sessions=len(docs), average_progress=avg_progress, average_attendance_rate=avg_attendance)


@instructor_router.get("/{cohort_id}/learners", response_model=list[InstructorCohortLearner])
async def instructor_learners(cohort_id: str, search: str | None = Query(None), user=Depends(get_current_user)):
    detail = await instructor_cohort_detail(cohort_id, user)
    if not search:
        return detail.learners
    term = search.lower()
    return [x for x in detail.learners if term in x.full_name.lower() or term in x.email.lower()]


@instructor_router.get("/{cohort_id}/sessions", response_model=list[PortalSession])
async def instructor_sessions(cohort_id: str, status: str | None = Query(None), user=Depends(get_current_user)):
    c = await db.cohorts.find_one({"_id": oid(cohort_id)})
    if not c:
        raise HTTPException(404, "Cohort not found")
    await instructor_access(c, user)
    q = {"cohort_id": c["_id"]}
    if status:
        q["status"] = status
    docs = await db.live_sessions.find(q).sort("starts_at", 1).to_list(length=5000)
    return [await session_response(s) for s in docs]
