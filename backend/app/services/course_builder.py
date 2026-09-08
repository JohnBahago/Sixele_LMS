from bson import ObjectId
from app.database.mongodb import db

async def validate_course_for_publishing(course: dict) -> dict:
    cid = course["_id"]
    errors = []
    warnings = []

    def issue(code, severity, message, resource_type=None, resource_id=None):
        target = errors if severity == "error" else warnings
        target.append({"code": code, "severity": severity, "message": message,
                       "resource_type": resource_type, "resource_id": resource_id})

    if not str(course.get("title", "")).strip():
        issue("course.title_required", "error", "Course title is required.", "course", str(cid))
    if not str(course.get("description", "")).strip() and not str(course.get("short_description", "")).strip():
        issue("course.description_required", "error", "Course description or short description is required.", "course", str(cid))
    if not course.get("objectives"):
        issue("course.objectives_required", "error", "At least one learning objective is required.", "course", str(cid))
    if not course.get("instructor_ids"):
        issue("course.instructor_required", "error", "At least one instructor must be assigned before publishing.", "course", str(cid))

    modules = await db.modules.find({"course_id": cid}).sort("order", 1).to_list(length=1000)
    lessons = await db.lessons.find({"course_id": cid}).sort("order", 1).to_list(length=5000)
    activities = await db.activities.find({"course_id": cid}).to_list(length=5000)
    quizzes = await db.quizzes.find({"course_id": cid}).to_list(length=5000)
    assignments = await db.assignments.find({"course_id": cid}).to_list(length=5000)

    if not modules:
        issue("structure.modules_required", "error", "Course must contain at least one module.", "course", str(cid))
    if not lessons:
        issue("structure.lessons_required", "error", "Course must contain at least one lesson.", "course", str(cid))

    module_ids = {m["_id"] for m in modules}
    lessons_by_module = {mid: [] for mid in module_ids}
    for lesson in lessons:
        if lesson.get("module_id") not in module_ids:
            issue("lesson.invalid_module", "error", f"Lesson '{lesson.get('title', '')}' is linked to a missing module.", "lesson", str(lesson["_id"]))
        else:
            lessons_by_module[lesson["module_id"]].append(lesson)
        if lesson.get("is_required", True) and not str(lesson.get("content", "")).strip():
            issue("lesson.content_required", "error", f"Required lesson '{lesson.get('title', '')}' has no content.", "lesson", str(lesson["_id"]))

    for module in modules:
        if not lessons_by_module.get(module["_id"]):
            issue("module.lesson_required", "error", f"Module '{module.get('title', '')}' has no lessons.", "module", str(module["_id"]))

    activity_by_id = {a["_id"]: a for a in activities}
    for activity in activities:
        if activity.get("module_id") not in module_ids:
            issue("activity.invalid_module", "error", f"Activity '{activity.get('title', '')}' is linked to a missing module.", "activity", str(activity["_id"]))
        if activity.get("status") == "published" and not str(activity.get("instructions", "")).strip() and not str(activity.get("task_description", "")).strip():
            issue("activity.instructions_required", "error", f"Published activity '{activity.get('title', '')}' needs instructions or a task description.", "activity", str(activity["_id"]))

    quiz_by_id = {q["_id"]: q for q in quizzes}
    for quiz in quizzes:
        if quiz.get("module_id") not in module_ids:
            issue("quiz.invalid_module", "error", f"Assessment '{quiz.get('title', '')}' is linked to a missing module.", "quiz", str(quiz["_id"]))
        if quiz.get("status") == "published":
            question_count = await db.quiz_questions.count_documents({"quiz_id": quiz["_id"]})
            if question_count == 0:
                issue("quiz.questions_required", "error", f"Published assessment '{quiz.get('title', '')}' has no questions.", "quiz", str(quiz["_id"]))

    published_required_activities = {a["_id"] for a in activities if a.get("is_required", True) and a.get("status") == "published"}
    published_required_quizzes = {q["_id"] for q in quizzes if q.get("is_required", True) and q.get("status") == "published"}

    rule = course.get("completion_rule", {}) or {}
    if rule.get("require_activities") and not published_required_activities:
        issue("completion.activities_required", "error", "Completion requires activities, but no required published activity is available.", "course", str(cid))
    if rule.get("require_assessments") and not published_required_quizzes:
        issue("completion.assessments_required", "error", "Completion requires assessments, but no required published assessment is available.", "course", str(cid))

    final_projects = [a for a in assignments if a.get("assignment_type") == "final_project" and a.get("is_required", True)]
    if rule.get("require_final_project"):
        published_final = [a for a in final_projects if a.get("status") == "published"]
        if not published_final:
            issue("completion.final_project_required", "error", "Final project completion is required, but no required published final project exists.", "course", str(cid))
    for assignment in assignments:
        if assignment.get("module_id") and assignment.get("module_id") not in module_ids:
            issue("assignment.invalid_module", "error", f"Assignment '{assignment.get('title', '')}' is linked to a missing module.", "assignment", str(assignment["_id"]))
        if assignment.get("status") == "published" and not str(assignment.get("instructions", "")).strip() and not str(assignment.get("brief", "")).strip():
            issue("assignment.instructions_required", "error", f"Published assignment '{assignment.get('title', '')}' needs instructions or a project brief.", "assignment", str(assignment["_id"]))

    if course.get("visibility") == "catalog" and not course.get("category"):
        issue("catalog.category_recommended", "warning", "Catalog courses should have a category.", "course", str(cid))

    return {
        "course_id": str(cid),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {"modules": len(modules), "lessons": len(lessons), "activities": len(activities), "assessments": len(quizzes), "assignments": len(assignments), "final_projects": len(final_projects), "instructors": len(course.get("instructor_ids", []))},
    }
