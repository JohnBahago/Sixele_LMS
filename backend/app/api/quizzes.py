from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.quizzes import (
    QuizCreate, QuizUpdate, QuizResponse, QuizStatus,
    QuizQuestionCreate, QuizQuestionUpdate, QuizQuestionResponse,
    QuizQuestionAdminResponse, QuizAttemptCreate, QuizAttemptResponse,
    GradeQuizAttemptRequest, QuizAttemptStatus, QuizQuestionType,
)
from app.services.authorization import require_permission, require_course_permission
from app.services.audit import audit_log

router = APIRouter(tags=["Assessments"])

def oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

async def get_quiz(quiz_id: str):
    doc = await db.quizzes.find_one({"_id": oid(quiz_id)})
    if not doc:
        raise HTTPException(404, "Quiz not found")
    return doc

async def verify_parent(course_id: str, module_id: str):
    c, m = oid(course_id), oid(module_id)
    if not await db.courses.find_one({"_id": c}):
        raise HTTPException(404, "Course not found")
    if not await db.modules.find_one({"_id": m, "course_id": c}):
        raise HTTPException(404, "Module not found")
    return c, m

async def quiz_response(doc):
    count = await db.quiz_questions.count_documents({"quiz_id": doc["_id"]})
    pipeline = [{"$match": {"quiz_id": doc["_id"]}}, {"$group": {"_id": None, "total": {"$sum": "$points"}}}]
    rows = await db.quiz_questions.aggregate(pipeline).to_list(length=1)
    return QuizResponse(
        id=str(doc["_id"]), course_id=str(doc["course_id"]), module_id=str(doc["module_id"]),
        title=doc["title"], description=doc.get("description", ""), instructions=doc.get("instructions", ""),
        time_limit_minutes=doc.get("time_limit_minutes"), attempts_allowed=doc.get("attempts_allowed", 1),
        pass_mark=doc.get("pass_mark", 50), is_required=doc.get("is_required", True), order=doc.get("order", 0),
        status=doc.get("status", "draft"), question_count=count, total_points=(rows[0]["total"] if rows else 0),
        created_by=str(doc["created_by"]), created_at=doc["created_at"], updated_at=doc["updated_at"])

def question_response(doc, admin=False):
    data = dict(id=str(doc["_id"]), quiz_id=str(doc["quiz_id"]), question_text=doc["question_text"],
        question_type=doc["question_type"], options=doc.get("options", []), points=doc["points"],
        explanation=doc.get("explanation", ""), order=doc.get("order", 0), is_required=doc.get("is_required", True))
    if admin:
        data["correct_answers"] = doc.get("correct_answers", [])
        return QuizQuestionAdminResponse(**data)
    return QuizQuestionResponse(**data)

def attempt_response(doc):
    return QuizAttemptResponse(
        id=str(doc["_id"]), quiz_id=str(doc["quiz_id"]), learner_id=str(doc["learner_id"]),
        attempt_number=doc["attempt_number"], answers=doc.get("answers", []), score=doc.get("score"),
        total_points=doc.get("total_points", 0), percentage=doc.get("percentage"), passed=doc.get("passed"),
        status=doc.get("status", "submitted"), manual_grading_required=doc.get("manual_grading_required", False),
        feedback=doc.get("feedback", ""), submitted_at=doc["submitted_at"], graded_at=doc.get("graded_at"),
        updated_at=doc["updated_at"])

@router.get("/courses/{course_id}/modules/{module_id}/quizzes", response_model=list[QuizResponse])
async def list_quizzes(course_id: str, module_id: str, status_filter: QuizStatus | None = Query(None, alias="status"), user=Depends(get_current_user)):
    await require_permission(user, "assessments.view")
    c, m = await verify_parent(course_id, module_id)
    q = {"course_id": c, "module_id": m}
    if status_filter: q["status"] = status_filter.value
    docs = await db.quizzes.find(q).sort("order", 1).to_list(length=500)
    return [await quiz_response(d) for d in docs]

@router.post("/courses/{course_id}/modules/{module_id}/quizzes", response_model=QuizResponse, status_code=201)
async def create_quiz(course_id: str, module_id: str, body: QuizCreate, user=Depends(get_current_user)):
    await require_permission(user, "assessments.create")
    c, m = await verify_parent(course_id, module_id)
    course = await db.courses.find_one({"_id": c})
    await require_course_permission(user, "assessments.create", course)
    now = datetime.now(timezone.utc)
    doc = {"course_id": c, "module_id": m, **body.model_dump(), "status": "draft", "created_by": user["_id"], "created_at": now, "updated_at": now}
    r = await db.quizzes.insert_one(doc); doc["_id"] = r.inserted_id
    await audit_log(actor_id=str(user["_id"]), action="quiz.create", resource="quiz", resource_id=str(r.inserted_id))
    return await quiz_response(doc)

@router.get("/quizzes/{quiz_id}", response_model=QuizResponse)
async def get_quiz_endpoint(quiz_id: str, user=Depends(get_current_user)):
    await require_permission(user, "assessments.view")
    return await quiz_response(await get_quiz(quiz_id))

@router.patch("/quizzes/{quiz_id}", response_model=QuizResponse)
async def update_quiz(quiz_id: str, body: QuizUpdate, user=Depends(get_current_user)):
    await require_permission(user, "assessments.edit")
    doc = await get_quiz(quiz_id)
    course = await db.courses.find_one({"_id": doc["course_id"]})
    await require_course_permission(user, "assessments.edit", course)
    updates = body.model_dump(exclude_unset=True)
    if updates.get("pass_mark") is not None and not 0 <= updates["pass_mark"] <= 100:
        raise HTTPException(400, "Pass mark must be between 0 and 100")
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.quizzes.update_one({"_id": doc["_id"]}, {"$set": updates}); doc.update(updates)
    await audit_log(actor_id=str(user["_id"]), action="quiz.update", resource="quiz", resource_id=quiz_id)
    return await quiz_response(doc)

@router.post("/quizzes/{quiz_id}/publish", response_model=QuizResponse)
async def publish_quiz(quiz_id: str, user=Depends(get_current_user)):
    await require_permission(user, "assessments.edit")
    doc = await get_quiz(quiz_id)
    course = await db.courses.find_one({"_id": doc["course_id"]})
    await require_course_permission(user, "assessments.edit", course)
    if await db.quiz_questions.count_documents({"quiz_id": doc["_id"]}) == 0:
        raise HTTPException(400, "A quiz must contain at least one question before publishing")
    now = datetime.now(timezone.utc)
    await db.quizzes.update_one({"_id": doc["_id"]}, {"$set": {"status": "published", "updated_at": now}})
    doc.update(status="published", updated_at=now)
    await audit_log(actor_id=str(user["_id"]), action="quiz.publish", resource="quiz", resource_id=quiz_id)
    return await quiz_response(doc)

@router.post("/quizzes/{quiz_id}/archive", response_model=QuizResponse)
async def archive_quiz(quiz_id: str, user=Depends(get_current_user)):
    await require_permission(user, "assessments.delete")
    doc = await get_quiz(quiz_id); now = datetime.now(timezone.utc)
    await db.quizzes.update_one({"_id": doc["_id"]}, {"$set": {"status": "archived", "updated_at": now}})
    doc.update(status="archived", updated_at=now)
    await audit_log(actor_id=str(user["_id"]), action="quiz.archive", resource="quiz", resource_id=quiz_id)
    return await quiz_response(doc)

@router.delete("/quizzes/{quiz_id}", status_code=204)
async def delete_quiz(quiz_id: str, user=Depends(get_current_user)):
    await require_permission(user, "assessments.delete")
    q = await get_quiz(quiz_id)
    await db.quizzes.delete_one({"_id": q["_id"]}); await db.quiz_questions.delete_many({"quiz_id": q["_id"]}); await db.quiz_attempts.delete_many({"quiz_id": q["_id"]})
    await audit_log(actor_id=str(user["_id"]), action="quiz.delete", resource="quiz", resource_id=quiz_id)

@router.get("/quizzes/{quiz_id}/questions", response_model=list[QuizQuestionResponse])
async def list_questions(quiz_id: str, user=Depends(get_current_user)):
    await require_permission(user, "assessments.view"); q = await get_quiz(quiz_id)
    docs = await db.quiz_questions.find({"quiz_id": q["_id"]}).sort("order", 1).to_list(length=500)
    return [question_response(x, admin=False) for x in docs]

@router.get("/quizzes/{quiz_id}/questions/admin", response_model=list[QuizQuestionAdminResponse])
async def list_questions_admin(quiz_id: str, user=Depends(get_current_user)):
    await require_permission(user, "assessments.edit"); q = await get_quiz(quiz_id)
    docs = await db.quiz_questions.find({"quiz_id": q["_id"]}).sort("order", 1).to_list(length=500)
    return [question_response(x, admin=True) for x in docs]

@router.post("/quizzes/{quiz_id}/questions", response_model=QuizQuestionAdminResponse, status_code=201)
async def create_question(quiz_id: str, body: QuizQuestionCreate, user=Depends(get_current_user)):
    await require_permission(user, "assessments.create"); q = await get_quiz(quiz_id)
    if q.get("status") == "published": raise HTTPException(400, "Unpublish the quiz before changing questions")
    now = datetime.now(timezone.utc)
    doc = {"quiz_id": q["_id"], **body.model_dump(), "question_type": body.question_type.value, "created_by": user["_id"], "created_at": now, "updated_at": now}
    r = await db.quiz_questions.insert_one(doc); doc["_id"] = r.inserted_id
    await audit_log(actor_id=str(user["_id"]), action="quiz_question.create", resource="quiz_question", resource_id=str(r.inserted_id))
    return question_response(doc, admin=True)

@router.patch("/quiz-questions/{question_id}", response_model=QuizQuestionAdminResponse)
async def update_question(question_id: str, body: QuizQuestionUpdate, user=Depends(get_current_user)):
    await require_permission(user, "assessments.edit")
    qd = await db.quiz_questions.find_one({"_id": oid(question_id)})
    if not qd: raise HTTPException(404, "Question not found")
    quiz = await db.quizzes.find_one({"_id": qd["quiz_id"]})
    if quiz.get("status") == "published": raise HTTPException(400, "Unpublish the quiz before changing questions")
    updates = body.model_dump(exclude_unset=True)
    if "question_type" in updates: updates["question_type"] = body.question_type.value
    if "options" in updates and "correct_answers" not in updates:
        bad = [a for a in qd.get("correct_answers", []) if a not in updates["options"]]
        if bad: raise HTTPException(400, "Existing correct answers must remain valid options")
    if "correct_answers" in updates:
        opts = updates.get("options", qd.get("options", []))
        if any(a not in opts for a in updates["correct_answers"]): raise HTTPException(400, "Correct answers must exist in options")
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.quiz_questions.update_one({"_id": qd["_id"]}, {"$set": updates}); qd.update(updates)
    return question_response(qd, admin=True)

@router.delete("/quiz-questions/{question_id}", status_code=204)
async def delete_question(question_id: str, user=Depends(get_current_user)):
    await require_permission(user, "assessments.delete")
    qd = await db.quiz_questions.find_one({"_id": oid(question_id)})
    if not qd: raise HTTPException(404, "Question not found")
    quiz = await db.quizzes.find_one({"_id": qd["quiz_id"]})
    if quiz.get("status") == "published": raise HTTPException(400, "Unpublish the quiz before changing questions")
    await db.quiz_questions.delete_one({"_id": qd["_id"]})
    await audit_log(actor_id=str(user["_id"]), action="quiz_question.delete", resource="quiz_question", resource_id=question_id)

def normalize_answer(value):
    if isinstance(value, list): return sorted(str(x).strip().lower() for x in value)
    if value is None: return ""
    return str(value).strip().lower()

@router.post("/quizzes/{quiz_id}/attempts", response_model=QuizAttemptResponse, status_code=201)
async def submit_quiz_attempt(quiz_id: str, body: QuizAttemptCreate, user=Depends(get_current_user)):
    await require_permission(user, "assessments.view")
    quiz = await get_quiz(quiz_id)
    if quiz.get("status") != "published": raise HTTPException(400, "Quiz is not open for attempts")
    previous = await db.quiz_attempts.find({"quiz_id": quiz["_id"], "learner_id": user["_id"]}).sort("attempt_number", -1).to_list(length=100)
    if previous and previous[0].get("status") in {"submitted", "needs_manual_grading"}: raise HTTPException(409, "Your current attempt is still being processed")
    attempt_number = len(previous) + 1
    if attempt_number > quiz.get("attempts_allowed", 1): raise HTTPException(400, "Maximum quiz attempts reached")
    questions = await db.quiz_questions.find({"quiz_id": quiz["_id"]}).sort("order", 1).to_list(length=500)
    answers = {a.question_id: a.answer for a in body.answers}
    total = sum(float(q.get("points", 1)) for q in questions)
    score = 0.0; manual = False
    for q in questions:
        qid = str(q["_id"]); answer = answers.get(qid)
        if q.get("question_type") in {QuizQuestionType.essay.value, QuizQuestionType.short_answer.value}:
            manual = True
            continue
        if normalize_answer(answer) == normalize_answer(q.get("correct_answers", [])):
            score += float(q.get("points", 1))
    percentage = round((score / total) * 100, 2) if total else 0
    passed = None if manual else percentage >= quiz.get("pass_mark", 50)
    final_status = QuizAttemptStatus.needs_manual_grading.value if manual else QuizAttemptStatus.graded.value
    now = datetime.now(timezone.utc)
    doc = {"quiz_id": quiz["_id"], "learner_id": user["_id"], "attempt_number": attempt_number, "answers": [a.model_dump() for a in body.answers], "score": score if not manual else None, "total_points": total, "percentage": percentage if not manual else None, "passed": passed, "status": final_status, "manual_grading_required": manual, "feedback": "", "submitted_at": now, "graded_at": None if manual else now, "updated_at": now}
    r = await db.quiz_attempts.insert_one(doc); doc["_id"] = r.inserted_id
    await audit_log(actor_id=str(user["_id"]), action="quiz_attempt.submit", resource="quiz_attempt", resource_id=str(r.inserted_id), details={"quiz_id": quiz_id, "attempt": attempt_number, "manual_grading": manual})
    return attempt_response(doc)

@router.get("/quizzes/{quiz_id}/attempts", response_model=list[QuizAttemptResponse])
async def list_quiz_attempts(quiz_id: str, learner_id: str | None = None, user=Depends(get_current_user)):
    await require_permission(user, "assessments.view")
    quiz = await get_quiz(quiz_id); query = {"quiz_id": quiz["_id"]}
    if learner_id:
        if oid(learner_id) != user["_id"]: await require_permission(user, "assessments.grade")
        query["learner_id"] = oid(learner_id)
    else:
        query["learner_id"] = user["_id"]
    docs = await db.quiz_attempts.find(query).sort("attempt_number", -1).to_list(length=500)
    return [attempt_response(x) for x in docs]

@router.get("/quiz-attempts/{attempt_id}", response_model=QuizAttemptResponse)
async def get_quiz_attempt(attempt_id: str, user=Depends(get_current_user)):
    await require_permission(user, "assessments.view")
    doc = await db.quiz_attempts.find_one({"_id": oid(attempt_id)})
    if not doc: raise HTTPException(404, "Quiz attempt not found")
    if doc["learner_id"] != user["_id"]: await require_permission(user, "assessments.grade")
    return attempt_response(doc)

@router.post("/quiz-attempts/{attempt_id}/grade", response_model=QuizAttemptResponse)
async def grade_quiz_attempt(attempt_id: str, body: GradeQuizAttemptRequest, user=Depends(get_current_user)):
    await require_permission(user, "assessments.grade")
    doc = await db.quiz_attempts.find_one({"_id": oid(attempt_id)})
    if not doc: raise HTTPException(404, "Quiz attempt not found")
    quiz = await db.quizzes.find_one({"_id": doc["quiz_id"]})
    if body.score > doc.get("total_points", 0): raise HTTPException(400, "Score cannot exceed total points")
    percentage = round((body.score / doc["total_points"]) * 100, 2) if doc.get("total_points") else 0
    passed = percentage >= quiz.get("pass_mark", 50)
    now = datetime.now(timezone.utc)
    updates = {"score": body.score, "percentage": percentage, "passed": passed, "status": "graded", "manual_grading_required": False, "feedback": body.feedback, "graded_at": now, "grader_id": user["_id"], "updated_at": now}
    await db.quiz_attempts.update_one({"_id": doc["_id"]}, {"$set": updates}); doc.update(updates)
    await audit_log(actor_id=str(user["_id"]), action="quiz_attempt.grade", resource="quiz_attempt", resource_id=attempt_id, details={"score": body.score, "percentage": percentage, "passed": passed})
    return attempt_response(doc)
