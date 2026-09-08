from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.instructor_portal import (
    InstructorLearnerSummary, InstructorCourseDetail, InstructorWorkItem,
    InstructorLearnerDetail, InstructorPortalResponse,
)
from app.schemas.instructor_dashboard import InstructorCourseSummary
from app.services.authorization import require_permission, course_visibility_filter, has_course_permission

router = APIRouter(prefix="/instructor", tags=["Instructor Portal"])

def oid(value: str):
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

async def scoped_courses(user, permission: str):
    await require_permission(user, permission)
    filt = await course_visibility_filter(user, permission)
    return await db.courses.find(filt).sort("updated_at", -1).to_list(length=2000)

async def course_for(user, course_id: str, permission: str = "courses.view"):
    course = await db.courses.find_one({"_id": oid(course_id)})
    if not course:
        raise HTTPException(404, "Course not found")
    if not await has_course_permission(user, permission, course):
        raise HTTPException(403, f"Permission required: {permission} for this course")
    return course

async def user_map(ids):
    ids = list({x for x in ids if isinstance(x, ObjectId)})
    if not ids:
        return {}
    docs = await db.users.find({"_id": {"$in": ids}}).to_list(length=len(ids))
    return {x["_id"]: x for x in docs}

async def work_items(courses, limit=50):
    if not courses:
        return []
    ids = [c["_id"] for c in courses]
    cmap = {c["_id"]: c for c in courses}
    activities = await db.activities.find({"course_id": {"$in": ids}}, {"_id":1,"title":1,"course_id":1}).to_list(length=5000)
    assignments = await db.assignments.find({"course_id": {"$in": ids}}, {"_id":1,"title":1,"course_id":1}).to_list(length=5000)
    quizzes = await db.quizzes.find({"course_id": {"$in": ids}}, {"_id":1,"title":1,"course_id":1}).to_list(length=5000)
    amap = {x["_id"]: x for x in activities}; pmap = {x["_id"]: x for x in assignments}; qmap = {x["_id"]: x for x in quizzes}
    items = []
    subs = await db.submissions.find({"course_id": {"$in": ids}, "status": {"$in": ["submitted","under_review"]}}).sort("submitted_at", -1).to_list(length=limit)
    for x in subs:
        a = amap.get(x.get("activity_id")); c = cmap.get(x.get("course_id"));
        if a and c: items.append(InstructorWorkItem(item_id=str(x["_id"]), item_type="activity", title=a.get("title",""), course_id=str(c["_id"]), course_title=c.get("title",""), learner_id=str(x["learner_id"]), learner_name="", attempt_number=x.get("attempt_number",1), status=x.get("status","submitted"), submitted_at=x["submitted_at"]))
    asubs = await db.assignment_submissions.find({"course_id": {"$in": ids}, "status": {"$in": ["submitted","under_review"]}}).sort("submitted_at", -1).to_list(length=limit)
    for x in asubs:
        a = pmap.get(x.get("assignment_id")); c = cmap.get(x.get("course_id"));
        if a and c: items.append(InstructorWorkItem(item_id=str(x["_id"]), item_type="assignment", title=a.get("title",""), course_id=str(c["_id"]), course_title=c.get("title",""), learner_id=str(x["learner_id"]), learner_name="", attempt_number=x.get("attempt_number",1), status=x.get("status","submitted"), submitted_at=x["submitted_at"]))
    qat = await db.quiz_attempts.find({"quiz_id": {"$in": list(qmap)}, "status":"needs_manual_grading"}).sort("submitted_at", -1).to_list(length=limit)
    for x in qat:
        q = qmap.get(x.get("quiz_id")); c = cmap.get(q.get("course_id")) if q else None
        if q and c: items.append(InstructorWorkItem(item_id=str(x["_id"]), item_type="assessment", title=q.get("title",""), course_id=str(c["_id"]), course_title=c.get("title",""), learner_id=str(x["learner_id"]), learner_name="", attempt_number=x.get("attempt_number",1), status=x.get("status","needs_manual_grading"), submitted_at=x["submitted_at"]))
    items.sort(key=lambda x: x.submitted_at, reverse=True)
    users = await user_map([oid(x.learner_id) for x in items])
    for x in items:
        u = users.get(oid(x.learner_id), {})
        x.learner_name = u.get("full_name", "")
    return items[:limit]

@router.get("/portal", response_model=InstructorPortalResponse)
async def portal(user=Depends(get_current_user)):
    courses = await scoped_courses(user, "courses.view")
    summaries=[]; total=0; active=0; completed=0
    for c in courses:
        ens = await db.enrollments.find({"course_id":c["_id"],"status":{"$ne":"cancelled"}}, {"status":1,"progress_percent":1}).to_list(length=10000)
        total += len(ens); active += sum(1 for e in ens if e.get("status")=="active"); completed += sum(1 for e in ens if e.get("status")=="completed")
        psub=await db.submissions.count_documents({"course_id":c["_id"],"status":{"$in":["submitted","under_review"]}})
        pasub=await db.assignment_submissions.count_documents({"course_id":c["_id"],"status":{"$in":["submitted","under_review"]}})
        quizzes=await db.quizzes.find({"course_id":c["_id"]},{"_id":1}).to_list(length=5000)
        pquiz=await db.quiz_attempts.count_documents({"quiz_id":{"$in":[q["_id"] for q in quizzes]},"status":"needs_manual_grading"}) if quizzes else 0
        avg=round(sum(float(e.get("progress_percent",0)) for e in ens)/len(ens),2) if ens else 0
        summaries.append(InstructorCourseSummary(course_id=str(c["_id"]),title=c.get("title",""),status=c.get("status","draft"),enrolled_learners=len(ens),completed_learners=sum(1 for e in ens if e.get("status")=="completed"),average_progress=avg,pending_submissions=psub+pasub,pending_assessments=pquiz))
    recent=await work_items(courses,50)
    return InstructorPortalResponse(instructor_id=str(user["_id"]),assigned_courses=len(courses),total_enrollments=total,active_learners=active,completed_learners=completed,pending_work=len(recent),courses=summaries,recent_work=recent)

@router.get("/courses/{course_id}", response_model=InstructorCourseDetail)
async def course_detail(course_id: str, user=Depends(get_current_user)):
    c=await course_for(user,course_id,"courses.view")
    modules=await db.modules.find({"course_id":c["_id"]}).sort("order",1).to_list(length=500)
    out=[]
    for m in modules:
        lessons=await db.lessons.find({"module_id":m["_id"]}).sort("order",1).to_list(length=1000)
        acts=await db.activities.find({"module_id":m["_id"]},{"_id":1,"title":1,"status":1,"is_required":1}).sort("order",1).to_list(length=1000)
        ass=await db.assignments.find({"module_id":m["_id"]},{"_id":1,"title":1,"status":1,"is_required":1,"assignment_type":1}).sort("order",1).to_list(length=1000)
        quizzes=await db.quizzes.find({"module_id":m["_id"]},{"_id":1,"title":1,"status":1}).sort("order",1).to_list(length=1000)
        out.append({"id":str(m["_id"]),"title":m.get("title",""),"description":m.get("description",""),"order":m.get("order",0),"lessons":[{"id":str(x["_id"]),"title":x.get("title",""),"type":x.get("type",""),"status":x.get("status","draft")} for x in lessons],"activities":[{"id":str(x["_id"]),"title":x.get("title",""),"status":x.get("status","draft"),"is_required":x.get("is_required",False)} for x in acts],"assignments":[{"id":str(x["_id"]),"title":x.get("title",""),"status":x.get("status","draft"),"is_required":x.get("is_required",False),"assignment_type":x.get("assignment_type","assignment")} for x in ass],"assessments":[{"id":str(x["_id"]),"title":x.get("title",""),"status":x.get("status","draft")} for x in quizzes]})
    learner_count=await db.enrollments.count_documents({"course_id":c["_id"],"status":{"$ne":"cancelled"}})
    work=await work_items([c],200)
    return InstructorCourseDetail(course_id=str(c["_id"]),title=c.get("title",""),description=c.get("description",""),status=c.get("status","draft"),visibility=c.get("visibility","private"),modules=out,learner_count=learner_count,pending_work_count=len(work))

@router.get("/courses/{course_id}/learners", response_model=list[InstructorLearnerSummary])
async def learners(course_id: str, search: str|None=Query(None), status: str|None=None, user=Depends(get_current_user)):
    c=await course_for(user,course_id,"courses.view")
    q={"course_id":c["_id"]}
    if status: q["status"]=status
    ens=await db.enrollments.find(q).sort("enrolled_at",-1).to_list(length=10000)
    users=await user_map([e["learner_id"] for e in ens]); out=[]
    for e in ens:
        u=users.get(e["learner_id"])
        if not u: continue
        if search and search.lower() not in (u.get("full_name","")+" "+u.get("email","")).lower(): continue
        out.append(InstructorLearnerSummary(learner_id=str(u["_id"]),full_name=u.get("full_name",""),email=u.get("email",""),enrollment_id=str(e["_id"]),course_id=course_id,course_title=c.get("title",""),status=e.get("status","active"),progress_percent=float(e.get("progress_percent",0)),enrolled_at=e["enrolled_at"],completed_at=e.get("completed_at")))
    return out

@router.get("/learners/{learner_id}/courses/{course_id}", response_model=InstructorLearnerDetail)
async def learner_detail(learner_id: str, course_id: str, user=Depends(get_current_user)):
    c=await course_for(user,course_id,"courses.view"); lid=oid(learner_id)
    learner=await db.users.find_one({"_id":lid})
    if not learner: raise HTTPException(404,"Learner not found")
    e=await db.enrollments.find_one({"learner_id":lid,"course_id":c["_id"]})
    if not e: raise HTTPException(404,"Enrollment not found")
    lessons=await db.lesson_progress.count_documents({"enrollment_id":e["_id"],"status":"completed"})
    activities=await db.activity_progress.count_documents({"learner_id":lid,"status":"completed","activity_id":{"$in":[x["_id"] for x in await db.activities.find({"course_id":c["_id"]},{"_id":1}).to_list(length=5000)]}})
    assignments=await db.assignment_progress.count_documents({"learner_id":lid,"status":"completed","assignment_id":{"$in":[x["_id"] for x in await db.assignments.find({"course_id":c["_id"]},{"_id":1}).to_list(length=5000)]}})
    quizzes=await db.quiz_attempts.count_documents({"learner_id":lid,"status":"graded","quiz_id":{"$in":[x["_id"] for x in await db.quizzes.find({"course_id":c["_id"]},{"_id":1}).to_list(length=5000)]}})
    allwork=await work_items([c],100)
    recent=[x for x in allwork if x.learner_id==learner_id][:20]
    return InstructorLearnerDetail(learner_id=learner_id,full_name=learner.get("full_name",""),email=learner.get("email",""),enrollment_id=str(e["_id"]),course_id=course_id,course_title=c.get("title",""),enrollment_status=e.get("status","active"),progress_percent=float(e.get("progress_percent",0)),lessons_completed=lessons,activities_completed=activities,assignments_completed=assignments,assessments_completed=quizzes,recent_work=recent)

@router.get("/work/pending", response_model=list[InstructorWorkItem])
async def pending_work(limit: int=Query(50,ge=1,le=200), user=Depends(get_current_user)):
    courses=await scoped_courses(user,"courses.view")
    return await work_items(courses,limit)
