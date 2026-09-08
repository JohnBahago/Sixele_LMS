from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.learner_portal import (
    LearnerDashboardResponse, LearnerCourseCard, LearnerCourseDetail,
    LearnerModule, LearnerLessonDetail, LearnerActivityDetail,
    LearnerQuizDetail, LearnerSubmitActivityResponse, LearnerSubmitQuizResponse,
    LearnerAssignmentDetail, LearnerSubmitAssignmentResponse, LearnerAssignmentSummary,
)
from app.schemas.activities import SubmissionCreate
from app.schemas.quizzes import QuizAttemptCreate
from app.schemas.assignments import AssignmentSubmissionCreate
from app.services.audit import audit_log

router = APIRouter(prefix="/learner", tags=["Learner Portal"])


def oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)


async def enrollment_for_user(enrollment_id: str, user):
    e = await db.enrollments.find_one({"_id": oid(enrollment_id), "learner_id": user["_id"]})
    if not e:
        raise HTTPException(404, "Enrollment not found")
    return e


async def enrollment_for_course(course_id: str, user):
    e = await db.enrollments.find_one({"course_id": oid(course_id), "learner_id": user["_id"], "status": {"$ne": "cancelled"}})
    if not e:
        raise HTTPException(403, "You are not enrolled in this course")
    return e


@router.get("/dashboard", response_model=LearnerDashboardResponse)
async def dashboard(user=Depends(get_current_user)):
    uid = user["_id"]
    enrollments = await db.enrollments.find({"learner_id": uid, "status": {"$ne": "cancelled"}}).sort("enrolled_at", -1).to_list(length=500)
    cards = []
    progress_values = []
    active = completed = 0
    for e in enrollments:
        course = await db.courses.find_one({"_id": e["course_id"]})
        if not course:
            continue
        p = float(e.get("progress_percent", 0))
        progress_values.append(p)
        is_completed = e.get("status") == "completed"
        if is_completed: completed += 1
        else: active += 1
        cards.append(LearnerCourseCard(
            enrollment_id=str(e["_id"]), course_id=str(course["_id"]), title=course.get("title", ""),
            short_description=course.get("short_description", ""), category=course.get("category", ""),
            level=course.get("level", ""), progress_percent=p, enrollment_status=e.get("status", "active"),
            completed=is_completed, enrolled_at=e["enrolled_at"], completed_at=e.get("completed_at")
        ))

    course_ids = [e["course_id"] for e in enrollments]
    required_activities = await db.activities.find({"course_id": {"$in": course_ids}, "is_required": True, "status": "published"}).to_list(length=5000) if course_ids else []
    activity_ids = [a["_id"] for a in required_activities]
    activity_progress = await db.activity_progress.find({"learner_id": uid, "activity_id": {"$in": activity_ids}}).to_list(length=5000) if activity_ids else []
    ap = {x["activity_id"]: x for x in activity_progress}
    pending_activities = sum(1 for a in required_activities if not ap.get(a["_id"], {}).get("passed", False))

    quizzes = await db.quizzes.find({"course_id": {"$in": course_ids}, "is_required": True, "status": "published"}).to_list(length=5000) if course_ids else []
    qids = [q["_id"] for q in quizzes]
    pending_assignments = 0
    assignments = await db.assignments.find({"course_id": {"$in": course_ids}, "status": "published"}).to_list(length=5000) if course_ids else []
    for assignment in assignments:
        progress = await db.assignment_progress.find_one({"assignment_id": assignment["_id"], "learner_id": uid})
        if not progress or progress.get("passed") is not True:
            pending_assignments += 1

    pending_assessments = 0
    if qids:
        for q in quizzes:
            passed = await db.quiz_attempts.find_one({"quiz_id": q["_id"], "learner_id": uid, "status": "graded", "passed": True})
            if not passed:
                pending_assessments += 1

    unread = await db.notifications.count_documents({"recipient_id": str(uid), "is_read": False})
    certs = await db.certificates.count_documents({"learner_id": uid, "status": "issued"})
    return LearnerDashboardResponse(
        learner_id=str(uid), total_courses=len(cards), active_courses=active, completed_courses=completed,
        average_progress=round(sum(progress_values) / len(progress_values), 2) if progress_values else 0,
        pending_activities=pending_activities, pending_assessments=pending_assessments, pending_assignments=pending_assignments,
        unread_notifications=unread, certificates_count=certs, courses=cards
    )


@router.get("/courses", response_model=list[LearnerCourseCard])
async def my_courses(status_filter: str | None = Query(None, alias="status"), user=Depends(get_current_user)):
    q = {"learner_id": user["_id"]}
    if status_filter: q["status"] = status_filter
    else: q["status"] = {"$ne": "cancelled"}
    enrollments = await db.enrollments.find(q).sort("enrolled_at", -1).to_list(length=500)
    result = []
    for e in enrollments:
        c = await db.courses.find_one({"_id": e["course_id"]})
        if c:
            result.append(LearnerCourseCard(enrollment_id=str(e["_id"]), course_id=str(c["_id"]), title=c.get("title", ""), short_description=c.get("short_description", ""), category=c.get("category", ""), level=c.get("level", ""), progress_percent=float(e.get("progress_percent", 0)), enrollment_status=e.get("status", "active"), completed=e.get("status") == "completed", enrolled_at=e["enrolled_at"], completed_at=e.get("completed_at")))
    return result


@router.get("/courses/{course_id}", response_model=LearnerCourseDetail)
async def course_detail(course_id: str, user=Depends(get_current_user)):
    e = await enrollment_for_course(course_id, user)
    c = await db.courses.find_one({"_id": oid(course_id), "status": "published"})
    if not c: raise HTTPException(404, "Course not found")
    modules = await db.modules.find({"course_id": c["_id"]}).sort("order", 1).to_list(length=500)
    output = []
    for m in modules:
        output.append(LearnerModule(
            id=str(m["_id"]), title=m.get("title", ""), description=m.get("description", ""), order=m.get("order", 0),
            lesson_count=await db.lessons.count_documents({"module_id": m["_id"]}),
            activity_count=await db.activities.count_documents({"module_id": m["_id"], "status": "published"}),
            assessment_count=await db.quizzes.count_documents({"module_id": m["_id"], "status": "published"}),
            assignment_count=await db.assignments.count_documents({"module_id": m["_id"], "status": "published"}),
        ))
    return LearnerCourseDetail(
        enrollment_id=str(e["_id"]), course_id=str(c["_id"]), title=c.get("title", ""), short_description=c.get("short_description", ""),
        description=c.get("description", ""), category=c.get("category", ""), level=c.get("level", ""),
        duration_minutes=c.get("duration_minutes", 0), objectives=c.get("objectives", []), progress_percent=float(e.get("progress_percent", 0)),
        enrollment_status=e.get("status", "active"), completed=e.get("status") == "completed", modules=output
    )


@router.get("/enrollments/{enrollment_id}/lessons/{lesson_id}", response_model=LearnerLessonDetail)
async def lesson_detail(enrollment_id: str, lesson_id: str, user=Depends(get_current_user)):
    e = await enrollment_for_user(enrollment_id, user)
    lesson = await db.lessons.find_one({"_id": oid(lesson_id), "course_id": e["course_id"]})
    if not lesson: raise HTTPException(404, "Lesson not found")
    progress = await db.lesson_progress.find_one({"lesson_id": lesson["_id"], "learner_id": user["_id"]})
    resources = await db.resources.find({"module_id": lesson["module_id"]}).to_list(length=100)
    return LearnerLessonDetail(
        id=str(lesson["_id"]), module_id=str(lesson["module_id"]), course_id=str(e["course_id"]), title=lesson.get("title", ""),
        description=lesson.get("description", ""), lesson_type=lesson.get("lesson_type", "reading"), content=lesson.get("content", ""),
        duration_minutes=lesson.get("duration_minutes", 0), order=lesson.get("order", 0), is_required=lesson.get("is_required", True),
        completed=bool(progress and progress.get("completed")), completed_at=progress.get("completed_at") if progress else None,
        resources=[{**{k: v for k, v in r.items() if k != "_id"}, "id": str(r["_id"])} for r in resources]
    )


@router.get("/enrollments/{enrollment_id}/activities/{activity_id}", response_model=LearnerActivityDetail)
async def activity_detail(enrollment_id: str, activity_id: str, user=Depends(get_current_user)):
    e = await enrollment_for_user(enrollment_id, user)
    a = await db.activities.find_one({"_id": oid(activity_id), "course_id": e["course_id"], "status": "published"})
    if not a: raise HTTPException(404, "Activity not found")
    p = await db.activity_progress.find_one({"activity_id": a["_id"], "learner_id": user["_id"]})
    return LearnerActivityDetail(
        id=str(a["_id"]), course_id=str(a["course_id"]), module_id=str(a["module_id"]), title=a.get("title", ""), description=a.get("description", ""),
        activity_type=a.get("activity_type", "practical_task"), submission_type=a.get("submission_type", "text"), instructions=a.get("instructions", ""),
        materials=a.get("materials", []), task_description=a.get("task_description", ""), max_score=a.get("max_score", 100), pass_mark=a.get("pass_mark", 50),
        attempts_allowed=a.get("attempts_allowed", 1), due_days=a.get("due_days"), is_required=a.get("is_required", True), order=a.get("order", 0), status=a.get("status", "published"),
        progress_status=p.get("status", "not_started") if p else "not_started", attempts_used=p.get("attempts_used", 0) if p else 0,
        latest_submission_id=str(p["latest_submission_id"]) if p and p.get("latest_submission_id") else None, score=p.get("score") if p else None,
        percentage=p.get("percentage") if p else None, passed=p.get("passed") if p else None
    )


@router.post("/enrollments/{enrollment_id}/activities/{activity_id}/submit", response_model=LearnerSubmitActivityResponse, status_code=201)
async def submit_activity(enrollment_id: str, activity_id: str, body: SubmissionCreate, user=Depends(get_current_user)):
    e = await enrollment_for_user(enrollment_id, user)
    a = await db.activities.find_one({"_id": oid(activity_id), "course_id": e["course_id"], "status": "published"})
    if not a: raise HTTPException(404, "Activity not found")
    attempts = await db.submissions.count_documents({"activity_id": a["_id"], "learner_id": user["_id"]})
    if attempts >= int(a.get("attempts_allowed", 1)):
        raise HTTPException(409, "Maximum attempts reached")
    # New submissions are only allowed after a revision request or before the first submission.
    latest = await db.submissions.find_one({"activity_id": a["_id"], "learner_id": user["_id"]}, sort=[("attempt_number", -1)])
    if latest and latest.get("status") not in {"revision_requested", "failed"}:
        raise HTTPException(409, "A new submission is not currently allowed")
    now = datetime.now(timezone.utc)
    doc = {
        "activity_id": a["_id"], "course_id": a["course_id"], "module_id": a["module_id"], "learner_id": user["_id"],
        "attempt_number": attempts + 1, "text_response": body.text_response, "files": [x.model_dump() for x in body.files],
        "checklist": [x.model_dump() for x in body.checklist], "evidence_notes": body.evidence_notes, "status": "submitted",
        "score": None, "percentage": None, "passed": None, "grader_id": None, "feedback": "", "criterion_scores": [],
        "submitted_at": now, "graded_at": None, "updated_at": now,
    }
    r = await db.submissions.insert_one(doc)
    await db.activity_progress.update_one({"activity_id": a["_id"], "learner_id": user["_id"]}, {"$set": {"activity_id": a["_id"], "course_id": a["course_id"], "learner_id": user["_id"], "status": "submitted", "latest_submission_id": r.inserted_id, "attempts_used": attempts + 1, "updated_at": now}}, upsert=True)
    await audit_log(actor_id=str(user["_id"]), action="learner.activity_submitted", resource="submission", resource_id=str(r.inserted_id), details={"activity_id": activity_id, "attempt_number": attempts + 1})
    return LearnerSubmitActivityResponse(submission_id=str(r.inserted_id), activity_id=activity_id, attempt_number=attempts + 1, status="submitted", message="Activity submitted successfully")


@router.get("/enrollments/{enrollment_id}/assignments", response_model=list[LearnerAssignmentSummary])
async def learner_assignments(enrollment_id: str, assignment_type: str | None = Query(None), user=Depends(get_current_user)):
    e = await enrollment_for_user(enrollment_id, user)
    q = {"course_id": e["course_id"], "status": "published"}
    if assignment_type:
        q["assignment_type"] = assignment_type
    assignments = await db.assignments.find(q).sort("order", 1).to_list(length=500)
    result = []
    for a in assignments:
        p = await db.assignment_progress.find_one({"assignment_id": a["_id"], "learner_id": user["_id"]})
        result.append(LearnerAssignmentSummary(
            assignment_id=str(a["_id"]), title=a.get("title", ""), assignment_type=a.get("assignment_type", "assignment"),
            is_required=a.get("is_required", True), status=a.get("status", "published"),
            progress_status=p.get("status", "not_started") if p else "not_started",
            attempts_used=p.get("attempts_used", 0) if p else 0, attempts_allowed=a.get("attempts_allowed", 1),
            percentage=p.get("percentage") if p else None, passed=p.get("passed") if p else None
        ))
    return result


@router.get("/enrollments/{enrollment_id}/assignments/{assignment_id}", response_model=LearnerAssignmentDetail)
async def learner_assignment_detail(enrollment_id: str, assignment_id: str, user=Depends(get_current_user)):
    e = await enrollment_for_user(enrollment_id, user)
    a = await db.assignments.find_one({"_id": oid(assignment_id), "course_id": e["course_id"], "status": "published"})
    if not a:
        raise HTTPException(404, "Assignment not found")
    p = await db.assignment_progress.find_one({"assignment_id": a["_id"], "learner_id": user["_id"]})
    latest = None
    if p and p.get("latest_submission_id"):
        latest = await db.assignment_submissions.find_one({"_id": p["latest_submission_id"], "learner_id": user["_id"]})
    return LearnerAssignmentDetail(
        id=str(a["_id"]), course_id=str(a["course_id"]), module_id=str(a["module_id"]) if a.get("module_id") else None,
        title=a.get("title", ""), description=a.get("description", ""), instructions=a.get("instructions", ""),
        assignment_type=a.get("assignment_type", "assignment"), brief=a.get("brief", ""), deliverables=a.get("deliverables", []),
        submission_type=a.get("submission_type", "text_and_file"), max_score=a.get("max_score", 100), pass_mark=a.get("pass_mark", 50),
        attempts_allowed=a.get("attempts_allowed", 1), due_days=a.get("due_days"), is_required=a.get("is_required", True),
        order=a.get("order", 0), status=a.get("status", "published"), progress_status=p.get("status", "not_started") if p else "not_started",
        attempts_used=p.get("attempts_used", 0) if p else 0, latest_submission_id=str(p["latest_submission_id"]) if p and p.get("latest_submission_id") else None,
        score=p.get("score") if p else None, percentage=p.get("percentage") if p else None, passed=p.get("passed") if p else None,
        feedback=latest.get("feedback", "") if latest else ""
    )


@router.get("/enrollments/{enrollment_id}/assignments/{assignment_id}/submissions")
async def learner_assignment_submissions(enrollment_id: str, assignment_id: str, user=Depends(get_current_user)):
    e = await enrollment_for_user(enrollment_id, user)
    a = await db.assignments.find_one({"_id": oid(assignment_id), "course_id": e["course_id"], "status": "published"})
    if not a:
        raise HTTPException(404, "Assignment not found")
    submissions = await db.assignment_submissions.find({"assignment_id": a["_id"], "learner_id": user["_id"]}).sort("attempt_number", 1).to_list(length=100)
    # Learners receive their own submission history, including feedback, but never grader internals beyond the safe ID.
    return [{
        "id": str(x["_id"]), "assignment_id": str(x["assignment_id"]), "attempt_number": x.get("attempt_number", 0),
        "text_response": x.get("text_response", ""), "files": x.get("files", []), "deliverable_notes": x.get("deliverable_notes", ""),
        "status": x.get("status", "submitted"), "score": x.get("score"), "percentage": x.get("percentage"),
        "passed": x.get("passed"), "feedback": x.get("feedback", ""), "criterion_scores": x.get("criterion_scores", []),
        "submitted_at": x.get("submitted_at"), "graded_at": x.get("graded_at"), "updated_at": x.get("updated_at")
    } for x in submissions]


@router.post("/enrollments/{enrollment_id}/assignments/{assignment_id}/submit", response_model=LearnerSubmitAssignmentResponse, status_code=201)
async def submit_learner_assignment(enrollment_id: str, assignment_id: str, body: AssignmentSubmissionCreate, user=Depends(get_current_user)):
    e = await enrollment_for_user(enrollment_id, user)
    a = await db.assignments.find_one({"_id": oid(assignment_id), "course_id": e["course_id"], "status": "published"})
    if not a:
        raise HTTPException(404, "Assignment not found")
    existing = await db.assignment_submissions.find({"assignment_id": a["_id"], "learner_id": user["_id"]}).sort("attempt_number", -1).to_list(length=100)
    if existing and existing[0].get("status") not in {"failed", "revision_requested"}:
        raise HTTPException(409, "The current submission is not eligible for resubmission")
    attempt = len(existing) + 1
    if attempt > int(a.get("attempts_allowed", 1)):
        raise HTTPException(400, "Maximum attempts reached")
    now = datetime.now(timezone.utc)
    doc = {
        "assignment_id": a["_id"], "course_id": a["course_id"], "module_id": a.get("module_id"), "learner_id": user["_id"],
        "attempt_number": attempt, **body.model_dump(), "status": "submitted", "score": None, "percentage": None, "passed": None,
        "grader_id": None, "feedback": "", "criterion_scores": [], "submitted_at": now, "graded_at": None, "updated_at": now
    }
    r = await db.assignment_submissions.insert_one(doc)
    await db.assignment_progress.update_one(
        {"assignment_id": a["_id"], "learner_id": user["_id"]},
        {"$set": {"assignment_id": a["_id"], "learner_id": user["_id"], "status": "submitted", "latest_submission_id": r.inserted_id, "attempts_used": attempt, "updated_at": now}},
        upsert=True
    )
    await audit_log(actor_id=str(user["_id"]), action="learner.assignment_submitted", resource="assignment_submission", resource_id=str(r.inserted_id), details={"assignment_id": assignment_id, "attempt_number": attempt})
    return LearnerSubmitAssignmentResponse(submission_id=str(r.inserted_id), assignment_id=assignment_id, attempt_number=attempt, status="submitted", message="Assignment submitted successfully")


@router.get("/enrollments/{enrollment_id}/quizzes/{quiz_id}", response_model=LearnerQuizDetail)
async def quiz_detail(enrollment_id: str, quiz_id: str, user=Depends(get_current_user)):
    e = await enrollment_for_user(enrollment_id, user)
    q = await db.quizzes.find_one({"_id": oid(quiz_id), "course_id": e["course_id"], "status": "published"})
    if not q: raise HTTPException(404, "Assessment not found")
    questions = await db.quiz_questions.find({"quiz_id": q["_id"]}).sort("order", 1).to_list(length=1000)
    attempts = await db.quiz_attempts.find({"quiz_id": q["_id"], "learner_id": user["_id"]}).sort("attempt_number", 1).to_list(length=100)
    graded = [x for x in attempts if x.get("status") == "graded" and x.get("percentage") is not None]
    best = max(graded, key=lambda x: x.get("percentage", 0), default=None)
    safe_questions = [{"id": str(x["_id"]), "question_text": x.get("question_text", ""), "question_type": x.get("question_type", "single_choice"), "options": x.get("options", []), "points": x.get("points", 1), "order": x.get("order", 0), "is_required": x.get("is_required", True)} for x in questions]
    return LearnerQuizDetail(id=str(q["_id"]), course_id=str(q["course_id"]), module_id=str(q["module_id"]), title=q.get("title", ""), description=q.get("description", ""), instructions=q.get("instructions", ""), time_limit_minutes=q.get("time_limit_minutes"), attempts_allowed=q.get("attempts_allowed", 1), pass_mark=q.get("pass_mark", 50), is_required=q.get("is_required", True), order=q.get("order", 0), status=q.get("status", "published"), question_count=len(questions), total_points=sum(float(x.get("points", 0)) for x in questions), attempts_used=len(attempts), best_percentage=best.get("percentage") if best else None, passed=best.get("passed") if best else None, questions=safe_questions)


@router.post("/enrollments/{enrollment_id}/quizzes/{quiz_id}/submit", response_model=LearnerSubmitQuizResponse, status_code=201)
async def submit_quiz(enrollment_id: str, quiz_id: str, body: QuizAttemptCreate, user=Depends(get_current_user)):
    e = await enrollment_for_user(enrollment_id, user)
    q = await db.quizzes.find_one({"_id": oid(quiz_id), "course_id": e["course_id"], "status": "published"})
    if not q: raise HTTPException(404, "Assessment not found")
    attempts = await db.quiz_attempts.count_documents({"quiz_id": q["_id"], "learner_id": user["_id"]})
    if attempts >= int(q.get("attempts_allowed", 1)):
        raise HTTPException(409, "Maximum attempts reached")
    now = datetime.now(timezone.utc)
    doc = {"quiz_id": q["_id"], "learner_id": user["_id"], "attempt_number": attempts + 1, "answers": [x.model_dump() for x in body.answers], "score": None, "total_points": 0, "percentage": None, "passed": None, "status": "submitted", "manual_grading_required": False, "feedback": "", "submitted_at": now, "graded_at": None, "updated_at": now}
    questions = await db.quiz_questions.find({"quiz_id": q["_id"]}).to_list(length=1000)
    total = sum(float(x.get("points", 0)) for x in questions)
    amap = {str(x.question_id): x.answer for x in body.answers}
    auto_score = 0.0
    manual = False
    for question in questions:
        typ = question.get("question_type")
        if typ in {"single_choice", "multiple_choice", "true_false"}:
            given = amap.get(str(question["_id"]))
            correct = question.get("correct_answers", [])
            given_list = given if isinstance(given, list) else [given] if given is not None else []
            if sorted(str(x) for x in given_list) == sorted(str(x) for x in correct): auto_score += float(question.get("points", 0))
        else:
            manual = True
    doc["total_points"] = total
    if manual:
        doc["score"] = auto_score
        doc["status"] = "needs_manual_grading"
        doc["manual_grading_required"] = True
    else:
        doc["score"] = auto_score
        doc["percentage"] = round((auto_score / total) * 100, 2) if total else 0
        doc["passed"] = doc["percentage"] >= float(q.get("pass_mark", 50))
        doc["status"] = "graded"
        doc["graded_at"] = now
    r = await db.quiz_attempts.insert_one(doc)
    await audit_log(actor_id=str(user["_id"]), action="learner.quiz_submitted", resource="quiz_attempt", resource_id=str(r.inserted_id), details={"quiz_id": quiz_id, "attempt_number": attempts + 1})
    return LearnerSubmitQuizResponse(attempt_id=str(r.inserted_id), quiz_id=quiz_id, attempt_number=attempts + 1, status=doc["status"], score=doc["score"], percentage=doc["percentage"], passed=doc["passed"], message="Assessment submitted successfully")
