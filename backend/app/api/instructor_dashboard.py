from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.instructor_dashboard import (
    InstructorCourseSummary, LearnerCourseProgress, PendingSubmissionSummary,
    PendingAssessmentSummary, InstructorDashboardResponse,
)
from app.services.authorization import require_permission, course_visibility_filter, has_course_permission

router = APIRouter(prefix="/instructor", tags=["Instructor Dashboard"])

def oid(value: str):
    if not ObjectId.is_valid(value): raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

async def visible_courses(user, permission="courses.view"):
    await require_permission(user, permission)
    filt = await course_visibility_filter(user, permission)
    return await db.courses.find(filt).sort("updated_at", -1).to_list(length=1000)

async def course_or_403(course_id: str, user, permission="courses.view"):
    course = await db.courses.find_one({"_id": oid(course_id)})
    if not course: raise HTTPException(404, "Course not found")
    if not await has_course_permission(user, permission, course):
        raise HTTPException(403, f"Permission required: {permission} for this course")
    return course

async def learner_map(ids):
    ids = list({x for x in ids if isinstance(x, ObjectId)})
    if not ids: return {}
    users = await db.users.find({"_id": {"$in": ids}}).to_list(length=len(ids))
    return {u["_id"]: u for u in users}

@router.get("/courses", response_model=list[InstructorCourseSummary])
async def instructor_courses(user=Depends(get_current_user)):
    courses = await visible_courses(user)
    result=[]
    for c in courses:
        cid=c["_id"]
        enrollments=await db.enrollments.find({"course_id":cid,"status":{"$ne":"cancelled"}}, {"learner_id":1,"status":1,"progress_percent":1}).to_list(length=5000)
        pending_sub=await db.submissions.count_documents({"course_id":cid,"status":{"$in":["submitted","under_review"]}})
        pending_ass=await db.quiz_attempts.count_documents({"quiz_id":{"$in":[x["_id"] for x in await db.quizzes.find({"course_id":cid},{"_id":1}).to_list(length=1000)]},"status":"needs_manual_grading"})
        result.append(InstructorCourseSummary(course_id=str(cid),title=c.get("title",""),status=c.get("status","draft"),enrolled_learners=len(enrollments),completed_learners=sum(1 for e in enrollments if e.get("status")=="completed"),average_progress=round(sum(float(e.get("progress_percent",0)) for e in enrollments)/len(enrollments),2) if enrollments else 0,pending_submissions=pending_sub,pending_assessments=pending_ass))
    return result

@router.get("/courses/{course_id}/learners", response_model=list[LearnerCourseProgress])
async def course_learners(course_id: str, search: str|None=Query(None), status_filter: str|None=Query(None, alias="status"), user=Depends(get_current_user)):
    course=await course_or_403(course_id,user,"courses.view")
    q={"course_id":course["_id"]}
    if status_filter: q["status"]=status_filter
    enrollments=await db.enrollments.find(q).sort("enrolled_at",-1).to_list(length=5000)
    users=await learner_map([e["learner_id"] for e in enrollments])
    out=[]
    for e in enrollments:
        u=users.get(e["learner_id"])
        if not u: continue
        if search and search.lower() not in (u.get("full_name","")+" "+u.get("email","")).lower(): continue
        out.append(LearnerCourseProgress(enrollment_id=str(e["_id"]),learner_id=str(e["learner_id"]),full_name=u.get("full_name",""),email=u.get("email",""),status=e.get("status","active"),progress_percent=float(e.get("progress_percent",0)),enrolled_at=e["enrolled_at"],completed_at=e.get("completed_at")))
    return out

@router.get("/submissions/pending", response_model=list[PendingSubmissionSummary])
async def pending_submissions(limit: int=Query(50,ge=1,le=200), user=Depends(get_current_user)):
    courses=await visible_courses(user,"submissions.view"); ids=[c["_id"] for c in courses]
    if not ids: return []
    docs=await db.submissions.find({"course_id":{"$in":ids},"status":{"$in":["submitted","under_review"]}}).sort("submitted_at",-1).to_list(length=limit)
    acts=await db.activities.find({"_id":{"$in":[d["activity_id"] for d in docs]}}).to_list(length=limit)
    amap={a["_id"]:a for a in acts}; cmap={c["_id"]:c for c in courses}; users=await learner_map([d["learner_id"] for d in docs])
    return [PendingSubmissionSummary(submission_id=str(d["_id"]),activity_id=str(d["activity_id"]),activity_title=amap.get(d["activity_id"],{}).get("title",""),course_id=str(d["course_id"]),course_title=cmap.get(d["course_id"],{}).get("title",""),learner_id=str(d["learner_id"]),learner_name=users.get(d["learner_id"],{}).get("full_name",""),attempt_number=d.get("attempt_number",1),status=d.get("status","submitted"),submitted_at=d["submitted_at"]) for d in docs]

@router.get("/assessments/pending", response_model=list[PendingAssessmentSummary])
async def pending_assessments(limit: int=Query(50,ge=1,le=200), user=Depends(get_current_user)):
    courses=await visible_courses(user,"assessments.view"); ids=[c["_id"] for c in courses]
    if not ids: return []
    quizzes=await db.quizzes.find({"course_id":{"$in":ids}},{"_id":1,"title":1,"course_id":1}).to_list(length=2000); qmap={q["_id"]:q for q in quizzes}
    docs=await db.quiz_attempts.find({"quiz_id":{"$in":list(qmap)},"status":"needs_manual_grading"}).sort("submitted_at",-1).to_list(length=limit)
    cmap={c["_id"]:c for c in courses}; users=await learner_map([d["learner_id"] for d in docs])
    return [PendingAssessmentSummary(attempt_id=str(d["_id"]),quiz_id=str(d["quiz_id"]),quiz_title=qmap[d["quiz_id"]].get("title",""),course_id=str(qmap[d["quiz_id"]]["course_id"]),course_title=cmap.get(qmap[d["quiz_id"]]["course_id"],{}).get("title",""),learner_id=str(d["learner_id"]),learner_name=users.get(d["learner_id"],{}).get("full_name",""),attempt_number=d.get("attempt_number",1),status=d.get("status","needs_manual_grading"),submitted_at=d["submitted_at"]) for d in docs]

@router.get("/dashboard", response_model=InstructorDashboardResponse)
async def instructor_dashboard(user=Depends(get_current_user)):
    courses=await instructor_courses(user)
    course_ids=[oid(c.course_id) for c in courses]
    enroll=await db.enrollments.find({"course_id":{"$in":course_ids},"status":{"$ne":"cancelled"}},{"learner_id":1,"status":1}).to_list(length=10000) if course_ids else []
    unique={e["learner_id"] for e in enroll}
    pending_sub=await pending_submissions(100,user); pending_ass=await pending_assessments(100,user)
    return InstructorDashboardResponse(assigned_courses=len(courses),total_learners=len(unique),active_learners=sum(1 for e in enroll if e.get("status")=="active"),completed_learners=sum(1 for e in enroll if e.get("status")=="completed"),pending_submissions=sum(c.pending_submissions for c in courses),pending_assessments=sum(c.pending_assessments for c in courses),courses=courses,recent_submissions=pending_sub[:10],recent_assessments=pending_ass[:10])
