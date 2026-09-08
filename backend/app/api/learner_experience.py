from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.learner_experience import (
    LearningItem, LearnerResumeResponse, LearnerCourseExperienceResponse,
    LearnerNavigationResponse,
)
from app.api.enrollments import calculate_progress

router = APIRouter(prefix="/learner", tags=["Learner Experience"])


def oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)


async def get_enrollment(enrollment_id: str, user):
    e = await db.enrollments.find_one({"_id": oid(enrollment_id), "learner_id": user["_id"], "status": {"$ne": "cancelled"}})
    if not e:
        raise HTTPException(404, "Enrollment not found")
    course = await db.courses.find_one({"_id": e["course_id"], "status": "published"})
    if not course:
        raise HTTPException(404, "Published course not found")
    return e, course


async def build_items(enrollment):
    cid, lid = enrollment["course_id"], enrollment["learner_id"]
    modules = await db.modules.find({"course_id": cid}).sort("order", 1).to_list(length=500)
    items = []
    for module in modules:
        mid = module["_id"]
        mt = module.get("title", "")
        lessons = await db.lessons.find({"module_id": mid}).sort("order", 1).to_list(length=1000)
        for lesson in lessons:
            p = await db.lesson_progress.find_one({"lesson_id": lesson["_id"], "learner_id": lid})
            completed = bool(p and p.get("completed"))
            items.append(LearningItem(
                id=str(lesson["_id"]), item_type="lesson", title=lesson.get("title", ""), module_id=str(mid),
                module_title=mt, order=lesson.get("order", 0), is_required=lesson.get("is_required", True),
                status="completed" if completed else "available", completed=completed,
                route=f"/learner/enrollments/{enrollment['_id']}/lessons/{lesson['_id']}"
            ))
        activities = await db.activities.find({"module_id": mid, "status": "published"}).sort("order", 1).to_list(length=1000)
        for activity in activities:
            p = await db.activity_progress.find_one({"activity_id": activity["_id"], "learner_id": lid})
            passed = p and p.get("passed") is True
            status = p.get("status", "not_started") if p else "not_started"
            completed = bool(passed)
            items.append(LearningItem(
                id=str(activity["_id"]), item_type="activity", title=activity.get("title", ""), module_id=str(mid),
                module_title=mt, order=activity.get("order", 0), is_required=activity.get("is_required", True),
                status="completed" if completed else status, completed=completed,
                route=f"/learner/enrollments/{enrollment['_id']}/activities/{activity['_id']}"
            ))
        quizzes = await db.quizzes.find({"module_id": mid, "status": "published"}).sort("order", 1).to_list(length=1000)
        for quiz in quizzes:
            attempts = await db.quiz_attempts.find({"quiz_id": quiz["_id"], "learner_id": lid, "status": "graded"}).sort("percentage", -1).to_list(length=100)
            best = attempts[0] if attempts else None
            completed = bool(best and best.get("passed") is True)
            status = "completed" if completed else ("attempted" if attempts else "not_started")
            items.append(LearningItem(
                id=str(quiz["_id"]), item_type="assessment", title=quiz.get("title", ""), module_id=str(mid),
                module_title=mt, order=quiz.get("order", 0), is_required=quiz.get("is_required", True),
                status=status, completed=completed,
                route=f"/learner/enrollments/{enrollment['_id']}/quizzes/{quiz['_id']}"
            ))
        assignments = await db.assignments.find({"module_id": mid, "status": "published"}).sort("order", 1).to_list(length=1000)
        for assignment in assignments:
            p = await db.assignment_progress.find_one({"assignment_id": assignment["_id"], "learner_id": lid})
            completed = bool(p and p.get("passed") is True)
            status = p.get("status", "not_started") if p else "not_started"
            items.append(LearningItem(
                id=str(assignment["_id"]), item_type="final_project" if assignment.get("assignment_type") == "final_project" else "assignment",
                title=assignment.get("title", ""), module_id=str(mid), module_title=mt, order=assignment.get("order", 0),
                is_required=assignment.get("is_required", True), status="completed" if completed else status, completed=completed,
                route=f"/learner/enrollments/{enrollment['_id']}/assignments/{assignment['_id']}"
            ))
    # Preserve module ordering, then item ordering within each module/type.
    return items


def choose_current(items):
    for item in items:
        if not item.completed and not item.locked:
            return item
    return items[-1] if items else None


def choose_next(items, current):
    if not current:
        return items[0] if items else None
    for i, item in enumerate(items):
        if item.id == current.id and i + 1 < len(items):
            return items[i + 1]
    return None


@router.get("/enrollments/{enrollment_id}/experience", response_model=LearnerCourseExperienceResponse)
async def course_experience(enrollment_id: str, user=Depends(get_current_user)):
    enrollment, course = await get_enrollment(enrollment_id, user)
    progress = await calculate_progress(enrollment)
    items = await build_items(enrollment)
    required = [x for x in items if x.is_required]
    completed_required = [x for x in required if x.completed]
    current = choose_current(items)
    nxt = choose_next(items, current)
    return LearnerCourseExperienceResponse(
        enrollment_id=str(enrollment["_id"]), course_id=str(course["_id"]), course_title=course.get("title", ""),
        progress_percent=progress.progress_percent, completed=progress.completed,
        total_items=len(items), completed_items=sum(1 for x in items if x.completed), required_items=len(required),
        completed_required_items=len(completed_required), current_item=current, next_item=nxt, items=items
    )


@router.get("/enrollments/{enrollment_id}/resume", response_model=LearnerResumeResponse)
async def resume_learning(enrollment_id: str, user=Depends(get_current_user)):
    enrollment, course = await get_enrollment(enrollment_id, user)
    items = await build_items(enrollment)
    current = choose_current(items)
    nxt = choose_next(items, current)
    last = await db.lesson_progress.find({"learner_id": user["_id"], "course_id": course["_id"], "completed": True}).sort("completed_at", -1).to_list(length=1)
    last_activity = last[0].get("completed_at") if last else enrollment.get("updated_at")
    return LearnerResumeResponse(
        enrollment_id=str(enrollment["_id"]), course_id=str(course["_id"]), course_title=course.get("title", ""),
        progress_percent=float(enrollment.get("progress_percent", 0)), completed=enrollment.get("status") == "completed",
        current_item=current, next_item=nxt, last_activity_at=last_activity
    )


@router.get("/enrollments/{enrollment_id}/navigate/{item_type}/{item_id}", response_model=LearnerNavigationResponse)
async def navigate(enrollment_id: str, item_type: str, item_id: str, user=Depends(get_current_user)):
    enrollment, _ = await get_enrollment(enrollment_id, user)
    items = await build_items(enrollment)
    current = next((x for x in items if x.id == item_id and x.item_type == item_type), None)
    if not current:
        raise HTTPException(404, "Learning item not found")
    index = items.index(current)
    return LearnerNavigationResponse(
        enrollment_id=str(enrollment["_id"]), current_item=current,
        previous_item=items[index - 1] if index > 0 else None,
        next_item=items[index + 1] if index + 1 < len(items) else None,
    )
