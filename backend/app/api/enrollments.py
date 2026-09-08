from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.enrollments import EnrollmentCreate, EnrollmentUpdate, EnrollmentResponse, CourseProgressResponse, LessonProgressResponse, ActivityProgressSummary, QuizProgressSummary
from app.services.authorization import require_permission
from app.services.audit import audit_log
from app.services.notifications import notify_event

router = APIRouter(tags=["Enrollment & Progress"])

def oid(value: str):
    if not ObjectId.is_valid(value): raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

async def get_enrollment(eid: str):
    doc = await db.enrollments.find_one({"_id": oid(eid)})
    if not doc: raise HTTPException(404, "Enrollment not found")
    return doc

async def serialize(doc):
    return EnrollmentResponse(id=str(doc["_id"]), course_id=str(doc["course_id"]), learner_id=str(doc["learner_id"]), status=doc.get("status","active"), progress_percent=doc.get("progress_percent",0), enrolled_at=doc["enrolled_at"], completed_at=doc.get("completed_at"), updated_at=doc["updated_at"])

@router.post("/enrollments", response_model=EnrollmentResponse, status_code=201)
async def create_enrollment(body: EnrollmentCreate, user=Depends(get_current_user)):
    await require_permission(user, "enrollments.create")
    learner, course = oid(body.learner_id), oid(body.course_id)
    if not await db.users.find_one({"_id": learner, "is_active": True}): raise HTTPException(404, "Learner not found")
    if not await db.courses.find_one({"_id": course, "status": "published"}): raise HTTPException(404, "Published course not found")
    existing = await db.enrollments.find_one({"learner_id": learner, "course_id": course})
    if existing and existing.get("status") != "cancelled": raise HTTPException(409, "Learner is already enrolled in this course")
    now=datetime.now(timezone.utc)
    doc={"learner_id":learner,"course_id":course,"status":"active","progress_percent":0,"enrolled_at":now,"completed_at":None,"updated_at":now}
    if existing:
        await db.enrollments.update_one({"_id":existing["_id"]},{"$set":doc}); doc["_id"]=existing["_id"]
    else:
        r=await db.enrollments.insert_one(doc); doc["_id"]=r.inserted_id
    await audit_log(actor_id=str(user["_id"]), action="enrollment.create", resource="enrollment", resource_id=str(doc["_id"]), details={"learner_id":body.learner_id,"course_id":body.course_id})
    await notify_event(event="enrollment", recipient_ids=[body.learner_id], title="Enrollment confirmed", message="You have been enrolled in a new course.", notification_type="enrollment", course_id=body.course_id, action_url=f"/learner/courses/{body.course_id}", actor_id=str(user["_id"]))
    return await serialize(doc)

@router.get("/enrollments", response_model=list[EnrollmentResponse])
async def list_enrollments(learner_id: str|None=Query(None), course_id: str|None=Query(None), status_filter: str|None=Query(None, alias="status"), user=Depends(get_current_user)):
    own = learner_id is None or oid(learner_id)==user["_id"]
    if not own: await require_permission(user,"enrollments.view")
    elif learner_id is None and not user.get("is_super_admin"): pass
    q={"learner_id": user["_id"]} if learner_id is None else {"learner_id":oid(learner_id)}
    if course_id: q["course_id"]=oid(course_id)
    if status_filter: q["status"]=status_filter
    docs=await db.enrollments.find(q).sort("enrolled_at",-1).to_list(length=500)
    return [await serialize(x) for x in docs]

@router.patch("/enrollments/{enrollment_id}", response_model=EnrollmentResponse)
async def update_enrollment(enrollment_id: str, body: EnrollmentUpdate, user=Depends(get_current_user)):
    await require_permission(user,"enrollments.edit")
    doc=await get_enrollment(enrollment_id); now=datetime.now(timezone.utc)
    updates={"status":body.status.value,"updated_at":now}
    if body.status.value=="completed": updates["completed_at"]=now
    elif body.status.value=="active": updates["completed_at"]=None
    await db.enrollments.update_one({"_id":doc["_id"]},{"$set":updates}); doc.update(updates)
    await audit_log(actor_id=str(user["_id"]),action="enrollment.update",resource="enrollment",resource_id=enrollment_id,details={"status":body.status.value})
    return await serialize(doc)

async def calculate_progress(enrollment):
    cid, lid = enrollment["course_id"], enrollment["learner_id"]
    course=await db.courses.find_one({"_id":cid})
    if not course: raise HTTPException(404,"Course not found")
    rule=course.get("completion_rule",{})
    lessons=await db.lessons.find({"course_id":cid,"is_required":True}).to_list(length=5000)
    lp=await db.lesson_progress.find({"course_id":cid,"learner_id":lid}).to_list(length=5000)
    lpmap={x["lesson_id"]:x for x in lp}
    lessons_completed=sum(1 for x in lessons if lpmap.get(x["_id"],{}).get("completed"))
    acts=await db.activities.find({"course_id":cid,"is_required":True,"status":"published"}).to_list(length=5000)
    aps=await db.activity_progress.find({"learner_id":lid,"activity_id":{"$in":[x["_id"] for x in acts]}}).to_list(length=5000)
    apmap={x["activity_id"]:x for x in aps}; activities_passed=sum(1 for x in acts if apmap.get(x["_id"],{}).get("passed") is True)
    quizzes=await db.quizzes.find({"course_id":cid,"is_required":True,"status":"published"}).to_list(length=5000)
    qps=[]; assessments_passed=0; scores=[]
    for q in quizzes:
        attempts=await db.quiz_attempts.find({"quiz_id":q["_id"],"learner_id":lid,"status":"graded"}).sort("percentage",-1).to_list(length=100)
        best=attempts[0] if attempts else None
        passed=bool(best and best.get("passed") is True)
        if passed: assessments_passed+=1
        if best and best.get("percentage") is not None: scores.append(best["percentage"])
        qps.append(QuizProgressSummary(quiz_id=str(q["_id"]),attempts_used=await db.quiz_attempts.count_documents({"quiz_id":q["_id"],"learner_id":lid}),passed=(best.get("passed") if best else None),best_percentage=(best.get("percentage") if best else None)))
    final_projects=await db.assignments.find({"course_id":cid,"assignment_type":"final_project","is_required":True,"status":"published"}).to_list(length=5000)
    final_project_completed=0
    final_project_progress=[]
    for project in final_projects:
        best_sub=await db.assignment_submissions.find_one({"assignment_id":project["_id"],"learner_id":lid,"status":"passed"}, sort=[("percentage",-1),("attempt_number",-1)])
        passed=best_sub is not None and best_sub.get("passed") is True
        if passed: final_project_completed += 1
        final_project_progress.append((project, best_sub))
    required_components=[]
    if rule.get("require_all_lessons",True): required_components.append((len(lessons),lessons_completed))
    if rule.get("require_activities",False): required_components.append((len(acts),activities_passed))
    if rule.get("require_assessments",False): required_components.append((len(quizzes),assessments_passed))
    if rule.get("require_final_project",False): required_components.append((len(final_projects),final_project_completed))
    completion_ok=all(total==done for total,done in required_components)
    calculated_score=(sum(scores)/len(scores)) if scores else None
    if rule.get("minimum_score") is not None: completion_ok = completion_ok and calculated_score is not None and calculated_score >= rule["minimum_score"]
    total=sum(x[0] for x in required_components); done=sum(x[1] for x in required_components)
    percent=round((done/total)*100,2) if total else 0
    now=datetime.now(timezone.utc)
    status="completed" if completion_ok else ("active" if enrollment.get("status")!="cancelled" else "cancelled")
    updates={"progress_percent":percent,"status":status,"updated_at":now}
    if completion_ok and not enrollment.get("completed_at"): updates["completed_at"]=now
    await db.enrollments.update_one({"_id":enrollment["_id"]},{"$set":updates})
    enrollment.update(updates)
    return CourseProgressResponse(enrollment_id=str(enrollment["_id"]),course_id=str(cid),learner_id=str(lid),progress_percent=percent,completed=completion_ok,final_project_required=bool(rule.get("require_final_project",False)),final_project_completed=(final_project_completed == len(final_projects) if final_projects else not rule.get("require_final_project",False)),lessons_required=len(lessons),lessons_completed=lessons_completed,activities_required=len(acts),activities_passed=activities_passed,assessments_required=len(quizzes),assessments_passed=assessments_passed,lesson_progress=[LessonProgressResponse(lesson_id=str(x["_id"]),learner_id=str(lid),completed=bool(lpmap.get(x["_id"],{}).get("completed")),completed_at=lpmap.get(x["_id"],{}).get("completed_at")) for x in lessons],activity_progress=[ActivityProgressSummary(activity_id=str(x["_id"]),status=apmap.get(x["_id"],{}).get("status","not_started"),attempts_used=apmap.get(x["_id"],{}).get("attempts_used",0),passed=apmap.get(x["_id"],{}).get("passed"),percentage=apmap.get(x["_id"],{}).get("percentage")) for x in acts],assessment_progress=qps,minimum_score=rule.get("minimum_score"),calculated_score=(round(calculated_score,2) if calculated_score is not None else None))

@router.get("/enrollments/{enrollment_id}/progress", response_model=CourseProgressResponse)
async def get_progress(enrollment_id: str, user=Depends(get_current_user)):
    e=await get_enrollment(enrollment_id)
    if e["learner_id"]!=user["_id"]: await require_permission(user,"enrollments.view")
    return await calculate_progress(e)

@router.post("/enrollments/{enrollment_id}/lessons/{lesson_id}/complete", response_model=CourseProgressResponse)
async def complete_lesson(enrollment_id: str, lesson_id: str, user=Depends(get_current_user)):
    e=await get_enrollment(enrollment_id)
    if e["learner_id"]!=user["_id"]: await require_permission(user,"enrollments.edit")
    lesson=await db.lessons.find_one({"_id":oid(lesson_id),"course_id":e["course_id"]})
    if not lesson: raise HTTPException(404,"Lesson not found in this course")
    now=datetime.now(timezone.utc)
    await db.lesson_progress.update_one({"lesson_id":lesson["_id"],"learner_id":e["learner_id"]},{"$set":{"lesson_id":lesson["_id"],"course_id":e["course_id"],"module_id":lesson["module_id"],"learner_id":e["learner_id"],"completed":True,"completed_at":now,"updated_at":now}},upsert=True)
    await audit_log(actor_id=str(user["_id"]),action="lesson.complete",resource="lesson_progress",resource_id=lesson_id)
    return await calculate_progress(e)
