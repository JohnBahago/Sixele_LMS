from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.activities import (
    ActivityCreate, ActivityUpdate, ActivityResponse, ActivityStatus,
    RubricCreate, RubricUpdate, RubricResponse, RubricCriterionResponse,
    SubmissionCreate, SubmissionResponse, GradeSubmissionRequest,
    SubmissionStatus, ActivityProgressResponse,
)
from app.services.authorization import require_permission, require_course_permission
from app.services.audit import audit_log

router = APIRouter(tags=["Activities"])


def oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)


async def get_activity(activity_id: str) -> dict:
    doc = await db.activities.find_one({"_id": oid(activity_id)})
    if not doc:
        raise HTTPException(404, "Activity not found")
    return doc


async def verify_parent(course_id: str, module_id: str):
    c_id, m_id = oid(course_id), oid(module_id)
    if not await db.courses.find_one({"_id": c_id}):
        raise HTTPException(404, "Course not found")
    if not await db.modules.find_one({"_id": m_id, "course_id": c_id}):
        raise HTTPException(404, "Module not found")
    return c_id, m_id


def activity_response(doc: dict) -> ActivityResponse:
    return ActivityResponse(
        id=str(doc["_id"]), course_id=str(doc["course_id"]), module_id=str(doc["module_id"]),
        title=doc["title"], description=doc.get("description", ""),
        activity_type=doc.get("activity_type", "practical_task"),
        submission_type=doc.get("submission_type", "text"), instructions=doc.get("instructions", ""),
        materials=doc.get("materials", []), task_description=doc.get("task_description", ""),
        max_score=doc.get("max_score", 100), pass_mark=doc.get("pass_mark", 50),
        attempts_allowed=doc.get("attempts_allowed", 1), due_days=doc.get("due_days"),
        is_required=doc.get("is_required", True), order=doc.get("order", 0),
        rubric_id=str(doc["rubric_id"]) if doc.get("rubric_id") else None,
        status=doc.get("status", "draft"), created_by=str(doc["created_by"]),
        created_at=doc["created_at"], updated_at=doc["updated_at"],
    )


def rubric_response(doc: dict, criteria: list[dict]) -> RubricResponse:
    return RubricResponse(
        id=str(doc["_id"]), activity_id=str(doc["activity_id"]), name=doc["name"],
        description=doc.get("description", ""),
        criteria=[RubricCriterionResponse(id=str(c["_id"]), name=c["name"], description=c.get("description", ""), max_score=c["max_score"], order=c.get("order", 0)) for c in criteria],
        created_by=str(doc["created_by"]), created_at=doc["created_at"], updated_at=doc["updated_at"],
    )


def submission_response(doc: dict) -> SubmissionResponse:
    return SubmissionResponse(
        id=str(doc["_id"]), activity_id=str(doc["activity_id"]), course_id=str(doc["course_id"]),
        module_id=str(doc["module_id"]), learner_id=str(doc["learner_id"]),
        attempt_number=doc["attempt_number"], text_response=doc.get("text_response", ""),
        files=doc.get("files", []), checklist=doc.get("checklist", []), evidence_notes=doc.get("evidence_notes", ""),
        status=doc.get("status", "submitted"), score=doc.get("score"), percentage=doc.get("percentage"),
        passed=doc.get("passed"), grader_id=str(doc["grader_id"]) if doc.get("grader_id") else None,
        feedback=doc.get("feedback", ""), criterion_scores=doc.get("criterion_scores", []),
        submitted_at=doc["submitted_at"], graded_at=doc.get("graded_at"), updated_at=doc["updated_at"],
    )


@router.get("/courses/{course_id}/modules/{module_id}/activities", response_model=list[ActivityResponse])
async def list_activities(course_id: str, module_id: str, status_filter: ActivityStatus | None = Query(None, alias="status"), user=Depends(get_current_user)):
    await require_permission(user, "activities.view")
    c_id, m_id = await verify_parent(course_id, module_id)
    query = {"course_id": c_id, "module_id": m_id}
    if status_filter:
        query["status"] = status_filter.value
    docs = await db.activities.find(query).sort("order", 1).to_list(length=500)
    return [activity_response(x) for x in docs]


@router.post("/courses/{course_id}/modules/{module_id}/activities", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
async def create_activity(course_id: str, module_id: str, body: ActivityCreate, user=Depends(get_current_user)):
    await require_permission(user, "activities.create")
    c_id, m_id = await verify_parent(course_id, module_id)
    course = await db.courses.find_one({"_id": c_id})
    await require_course_permission(user, "activities.create", course)
    if body.rubric_id:
        rubric = await db.rubrics.find_one({"_id": oid(body.rubric_id)})
        if not rubric:
            raise HTTPException(404, "Rubric not found")
    now = datetime.now(timezone.utc)
    doc = {"course_id": c_id, "module_id": m_id, **body.model_dump(), "activity_type": body.activity_type.value, "submission_type": body.submission_type.value, "rubric_id": oid(body.rubric_id) if body.rubric_id else None, "status": "draft", "created_by": user["_id"], "created_at": now, "updated_at": now}
    result = await db.activities.insert_one(doc)
    doc["_id"] = result.inserted_id
    await audit_log(actor_id=str(user["_id"]), action="activity.create", resource="activity", resource_id=str(result.inserted_id), details={"course_id": course_id, "module_id": module_id})
    return activity_response(doc)


@router.get("/activities/{activity_id}", response_model=ActivityResponse)
async def get_activity_endpoint(activity_id: str, user=Depends(get_current_user)):
    await require_permission(user, "activities.view")
    return activity_response(await get_activity(activity_id))


@router.patch("/activities/{activity_id}", response_model=ActivityResponse)
async def update_activity(activity_id: str, body: ActivityUpdate, user=Depends(get_current_user)):
    await require_permission(user, "activities.edit")
    _id = oid(activity_id)
    doc = await get_activity(activity_id)
    course = await db.courses.find_one({"_id": doc["course_id"]})
    await require_course_permission(user, "activities.edit", course)
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "activity_type" in updates: updates["activity_type"] = body.activity_type.value
    if "submission_type" in updates: updates["submission_type"] = body.submission_type.value
    if "rubric_id" in updates:
        if not await db.rubrics.find_one({"_id": oid(body.rubric_id)}):
            raise HTTPException(404, "Rubric not found")
        updates["rubric_id"] = oid(body.rubric_id)
    if "max_score" in updates and updates["max_score"] <= 0:
        raise HTTPException(400, "Maximum score must be greater than zero")
    if "pass_mark" in updates and updates["pass_mark"] > 100:
        raise HTTPException(400, "Pass mark cannot exceed 100")
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.activities.update_one({"_id": _id}, {"$set": updates})
    doc.update(updates)
    await audit_log(actor_id=str(user["_id"]), action="activity.update", resource="activity", resource_id=activity_id)
    return activity_response(doc)


@router.post("/activities/{activity_id}/publish", response_model=ActivityResponse)
async def publish_activity(activity_id: str, user=Depends(get_current_user)):
    await require_permission(user, "activities.edit")
    doc = await get_activity(activity_id)
    course = await db.courses.find_one({"_id": doc["course_id"]})
    await require_course_permission(user, "activities.edit", course)
    now = datetime.now(timezone.utc)
    await db.activities.update_one({"_id": doc["_id"]}, {"$set": {"status": "published", "updated_at": now}})
    doc.update({"status": "published", "updated_at": now})
    await audit_log(actor_id=str(user["_id"]), action="activity.publish", resource="activity", resource_id=activity_id)
    return activity_response(doc)


@router.post("/activities/{activity_id}/archive", response_model=ActivityResponse)
async def archive_activity(activity_id: str, user=Depends(get_current_user)):
    await require_permission(user, "activities.delete")
    doc = await get_activity(activity_id)
    now = datetime.now(timezone.utc)
    await db.activities.update_one({"_id": doc["_id"]}, {"$set": {"status": "archived", "updated_at": now}})
    doc.update({"status": "archived", "updated_at": now})
    await audit_log(actor_id=str(user["_id"]), action="activity.archive", resource="activity", resource_id=activity_id)
    return activity_response(doc)


@router.delete("/activities/{activity_id}", status_code=204)
async def delete_activity(activity_id: str, user=Depends(get_current_user)):
    await require_permission(user, "activities.delete")
    _id = oid(activity_id)
    if not await db.activities.find_one({"_id": _id}):
        raise HTTPException(404, "Activity not found")
    await db.activities.delete_one({"_id": _id})
    await db.rubrics.delete_many({"activity_id": _id})
    await db.rubric_criteria.delete_many({"activity_id": _id})
    await db.submissions.delete_many({"activity_id": _id})
    await db.activity_progress.delete_many({"activity_id": _id})
    await audit_log(actor_id=str(user["_id"]), action="activity.delete", resource="activity", resource_id=activity_id)


@router.post("/activities/{activity_id}/rubrics", response_model=RubricResponse, status_code=201)
async def create_rubric(activity_id: str, body: RubricCreate, user=Depends(get_current_user)):
    await require_permission(user, "assessments.manage_rubrics")
    activity = await get_activity(activity_id)
    if await db.rubrics.find_one({"activity_id": activity["_id"]}):
        raise HTTPException(409, "This activity already has a rubric")
    now = datetime.now(timezone.utc)
    doc = {"activity_id": activity["_id"], "name": body.name, "description": body.description, "created_by": user["_id"], "created_at": now, "updated_at": now}
    result = await db.rubrics.insert_one(doc); doc["_id"] = result.inserted_id
    criteria_docs = []
    for c in body.criteria:
        criterion = {"activity_id": activity["_id"], "rubric_id": result.inserted_id, **c.model_dump()}
        r = await db.rubric_criteria.insert_one(criterion); criterion["_id"] = r.inserted_id; criteria_docs.append(criterion)
    await db.activities.update_one({"_id": activity["_id"]}, {"$set": {"rubric_id": result.inserted_id, "updated_at": now}})
    await audit_log(actor_id=str(user["_id"]), action="rubric.create", resource="rubric", resource_id=str(result.inserted_id), details={"activity_id": activity_id})
    return rubric_response(doc, criteria_docs)


@router.get("/activities/{activity_id}/rubric", response_model=RubricResponse)
async def get_rubric(activity_id: str, user=Depends(get_current_user)):
    await require_permission(user, "assessments.view")
    activity = await get_activity(activity_id)
    doc = await db.rubrics.find_one({"activity_id": activity["_id"]})
    if not doc:
        raise HTTPException(404, "Rubric not found")
    criteria = await db.rubric_criteria.find({"rubric_id": doc["_id"]}).sort("order", 1).to_list(length=200)
    return rubric_response(doc, criteria)


@router.patch("/activities/{activity_id}/rubric", response_model=RubricResponse)
async def update_rubric(activity_id: str, body: RubricUpdate, user=Depends(get_current_user)):
    await require_permission(user, "assessments.manage_rubrics")
    activity = await get_activity(activity_id)
    doc = await db.rubrics.find_one({"activity_id": activity["_id"]})
    if not doc: raise HTTPException(404, "Rubric not found")
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.rubrics.update_one({"_id": doc["_id"]}, {"$set": updates}); doc.update(updates)
    criteria = await db.rubric_criteria.find({"rubric_id": doc["_id"]}).sort("order", 1).to_list(length=200)
    await audit_log(actor_id=str(user["_id"]), action="rubric.update", resource="rubric", resource_id=str(doc["_id"]))
    return rubric_response(doc, criteria)


@router.post("/rubrics/{rubric_id}/criteria", response_model=RubricResponse, status_code=201)
async def add_rubric_criterion(rubric_id: str, body: dict, user=Depends(get_current_user)):
    await require_permission(user, "assessments.manage_rubrics")
    rubric = await db.rubrics.find_one({"_id": oid(rubric_id)})
    if not rubric: raise HTTPException(404, "Rubric not found")
    required = {"name", "max_score"}
    if not required.issubset(body): raise HTTPException(422, "name and max_score are required")
    if float(body["max_score"]) <= 0: raise HTTPException(422, "max_score must be greater than zero")
    criterion = {"activity_id": rubric["activity_id"], "rubric_id": rubric["_id"], "name": body["name"], "description": body.get("description", ""), "max_score": float(body["max_score"]), "order": int(body.get("order", 0))}
    result = await db.rubric_criteria.insert_one(criterion); criterion["_id"] = result.inserted_id
    criteria = await db.rubric_criteria.find({"rubric_id": rubric["_id"]}).sort("order", 1).to_list(length=200)
    return rubric_response(rubric, criteria)


@router.post("/activities/{activity_id}/submissions", response_model=SubmissionResponse, status_code=201)
async def submit_activity(activity_id: str, body: SubmissionCreate, user=Depends(get_current_user)):
    await require_permission(user, "activities.view")
    activity = await get_activity(activity_id)
    if activity.get("status") != "published":
        raise HTTPException(400, "Activity is not open for submission")
    existing = await db.submissions.find({"activity_id": activity["_id"], "learner_id": user["_id"]}).sort("attempt_number", -1).to_list(length=100)
    if existing and existing[0].get("status") not in {"failed", "revision_requested"}:
        raise HTTPException(409, "The current submission is not eligible for resubmission")
    attempt = len(existing) + 1
    if attempt > activity.get("attempts_allowed", 1):
        raise HTTPException(400, "Maximum attempts reached")
    now = datetime.now(timezone.utc)
    doc = {"activity_id": activity["_id"], "course_id": activity["course_id"], "module_id": activity["module_id"], "learner_id": user["_id"], "attempt_number": attempt, **body.model_dump(), "status": "submitted", "score": None, "percentage": None, "passed": None, "grader_id": None, "feedback": "", "criterion_scores": [], "submitted_at": now, "graded_at": None, "updated_at": now}
    result = await db.submissions.insert_one(doc); doc["_id"] = result.inserted_id
    await db.activity_progress.update_one({"activity_id": activity["_id"], "learner_id": user["_id"]}, {"$set": {"activity_id": activity["_id"], "learner_id": user["_id"], "status": "submitted", "latest_submission_id": result.inserted_id, "attempts_used": attempt, "updated_at": now}}, upsert=True)
    await audit_log(actor_id=str(user["_id"]), action="submission.create", resource="submission", resource_id=str(result.inserted_id), details={"activity_id": activity_id, "attempt": attempt})
    return submission_response(doc)


@router.get("/activities/{activity_id}/submissions", response_model=list[SubmissionResponse])
async def list_activity_submissions(activity_id: str, learner_id: str | None = None, user=Depends(get_current_user)):
    await require_permission(user, "submissions.view")
    activity = await get_activity(activity_id)
    query = {"activity_id": activity["_id"]}
    if learner_id: query["learner_id"] = oid(learner_id)
    docs = await db.submissions.find(query).sort([("submitted_at", -1), ("attempt_number", -1)]).to_list(length=500)
    return [submission_response(x) for x in docs]


@router.get("/submissions/{submission_id}", response_model=SubmissionResponse)
async def get_submission(submission_id: str, user=Depends(get_current_user)):
    _id = oid(submission_id)
    doc = await db.submissions.find_one({"_id": _id})
    if not doc: raise HTTPException(404, "Submission not found")
    if doc["learner_id"] != user["_id"]:
        await require_permission(user, "submissions.view")
    return submission_response(doc)


@router.post("/submissions/{submission_id}/review", response_model=SubmissionResponse)
async def review_submission(submission_id: str, user=Depends(get_current_user)):
    await require_permission(user, "submissions.review")
    _id = oid(submission_id)
    doc = await db.submissions.find_one({"_id": _id})
    if not doc: raise HTTPException(404, "Submission not found")
    if doc.get("status") not in {"submitted", "revision_requested"}:
        raise HTTPException(400, "Submission cannot be moved to review")
    now = datetime.now(timezone.utc)
    await db.submissions.update_one({"_id": _id}, {"$set": {"status": "under_review", "updated_at": now}})
    doc.update({"status": "under_review", "updated_at": now})
    await audit_log(actor_id=str(user["_id"]), action="submission.review", resource="submission", resource_id=submission_id)
    return submission_response(doc)


@router.post("/submissions/{submission_id}/grade", response_model=SubmissionResponse)
async def grade_submission(submission_id: str, body: GradeSubmissionRequest, user=Depends(get_current_user)):
    await require_permission(user, "submissions.grade")
    _id = oid(submission_id)
    doc = await db.submissions.find_one({"_id": _id})
    if not doc: raise HTTPException(404, "Submission not found")
    activity = await db.activities.find_one({"_id": doc["activity_id"]})
    if not activity: raise HTTPException(404, "Activity not found")
    if body.score > activity.get("max_score", 100):
        raise HTTPException(400, "Score cannot exceed the activity maximum score")
    percentage = round((body.score / activity.get("max_score", 100)) * 100, 2)
    passed = percentage >= activity.get("pass_mark", 50)
    if body.status in {SubmissionStatus.passed, SubmissionStatus.failed, SubmissionStatus.revision_requested}:
        final_status = body.status.value
        if final_status == "passed" and not passed:
            raise HTTPException(400, "A submission below the pass mark cannot be marked passed")
        if final_status == "failed" and passed:
            raise HTTPException(400, "A submission meeting the pass mark cannot be marked failed")
    else:
        final_status = "passed" if passed else "failed"
    now = datetime.now(timezone.utc)
    updates = {"status": final_status, "score": body.score, "percentage": percentage, "passed": passed, "grader_id": user["_id"], "feedback": body.feedback, "criterion_scores": body.criterion_scores, "graded_at": now, "updated_at": now}
    await db.submissions.update_one({"_id": _id}, {"$set": updates}); doc.update(updates)
    progress_status = "completed" if passed else ("revision_required" if final_status == "revision_requested" else "failed")
    await db.activity_progress.update_one({"activity_id": doc["activity_id"], "learner_id": doc["learner_id"]}, {"$set": {"status": progress_status, "latest_submission_id": _id, "attempts_used": doc["attempt_number"], "score": body.score, "percentage": percentage, "passed": passed, "updated_at": now}}, upsert=True)
    await audit_log(actor_id=str(user["_id"]), action="submission.grade", resource="submission", resource_id=submission_id, details={"score": body.score, "percentage": percentage, "passed": passed, "status": final_status})
    return submission_response(doc)


@router.post("/submissions/{submission_id}/return-for-revision", response_model=SubmissionResponse)
async def return_submission_for_revision(submission_id: str, body: dict | None = None, user=Depends(get_current_user)):
    await require_permission(user, "submissions.return_for_revision")
    _id = oid(submission_id); doc = await db.submissions.find_one({"_id": _id})
    if not doc: raise HTTPException(404, "Submission not found")
    feedback = (body or {}).get("feedback", "")
    now = datetime.now(timezone.utc)
    updates = {"status": "revision_requested", "feedback": feedback, "grader_id": user["_id"], "updated_at": now}
    await db.submissions.update_one({"_id": _id}, {"$set": updates}); doc.update(updates)
    await db.activity_progress.update_one({"activity_id": doc["activity_id"], "learner_id": doc["learner_id"]}, {"$set": {"status": "revision_required", "updated_at": now}})
    await audit_log(actor_id=str(user["_id"]), action="submission.return_for_revision", resource="submission", resource_id=submission_id)
    return submission_response(doc)


@router.get("/activities/{activity_id}/progress", response_model=ActivityProgressResponse)
async def activity_progress(activity_id: str, learner_id: str | None = None, user=Depends(get_current_user)):
    await require_permission(user, "activities.view")
    activity = await get_activity(activity_id)
    target = oid(learner_id) if learner_id else user["_id"]
    if learner_id and target != user["_id"]:
        await require_permission(user, "submissions.view")
    doc = await db.activity_progress.find_one({"activity_id": activity["_id"], "learner_id": target})
    if not doc:
        now = datetime.now(timezone.utc)
        return ActivityProgressResponse(activity_id=activity_id, learner_id=str(target), status="not_started", latest_submission_id=None, attempts_used=0, score=None, percentage=None, passed=None, updated_at=now)
    return ActivityProgressResponse(activity_id=activity_id, learner_id=str(doc["learner_id"]), status=doc.get("status", "not_started"), latest_submission_id=str(doc["latest_submission_id"]) if doc.get("latest_submission_id") else None, attempts_used=doc.get("attempts_used", 0), score=doc.get("score"), percentage=doc.get("percentage"), passed=doc.get("passed"), updated_at=doc["updated_at"])
