from bson import ObjectId
from fastapi import HTTPException
from app.database.mongodb import db

async def _roles_for_user(user: dict) -> list[dict]:
    role_ids = [ObjectId(str(x)) for x in user.get("role_ids", []) if ObjectId.is_valid(str(x))]
    if not role_ids:
        return []
    return await db.roles.find({"_id": {"$in": role_ids}, "is_active": True}).to_list(length=100)

async def has_permission(user: dict, permission: str) -> bool:
    if user.get("is_super_admin"):
        return True
    return any(permission in role.get("permission_ids", []) for role in await _roles_for_user(user))

async def require_permission(user: dict, permission: str):
    if not await has_permission(user, permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")
    return user


def _scope_allows_course(scope: dict | None, course_id: str, course: dict, user_id: str) -> bool:
    if not scope:
        return True
    scope_type = scope.get("type", "all")
    if scope_type in {"all", "global"}:
        return True
    if scope_type == "assigned_courses":
        return user_id in {str(x) for x in course.get("instructor_ids", [])}
    if scope_type == "specific_courses":
        return course_id in {str(x) for x in scope.get("course_ids", [])}
    return False

async def has_course_permission(user: dict, permission: str, course: dict) -> bool:
    if user.get("is_super_admin"):
        return True
    user_id = str(user["_id"])
    for role in await _roles_for_user(user):
        if permission in role.get("permission_ids", []) and _scope_allows_course(role.get("scope"), str(course["_id"]), course, user_id):
            return True
    return False

async def require_course_permission(user: dict, permission: str, course: dict):
    if not await has_course_permission(user, permission, course):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission} for this course")
    # Published courses are immutable. A new revision must be opened before instructional
    # content or course configuration can be changed. Read/publish/archive operations remain allowed.
    mutating_tokens = (".create", ".edit", ".delete", ".manage", "content.upload")
    if course.get("status") == "published" and any(token in permission for token in mutating_tokens):
        raise HTTPException(status_code=409, detail="Published course is immutable. Create a new revision before editing.")
    return user

async def course_visibility_filter(user: dict, permission: str = "courses.view") -> dict:
    if user.get("is_super_admin"):
        return {}
    roles = await _roles_for_user(user)
    user_id = str(user["_id"])
    unrestricted = False
    assigned = False
    specific: set[str] = set()
    for role in roles:
        if permission not in role.get("permission_ids", []):
            continue
        scope = role.get("scope") or {}
        scope_type = scope.get("type", "all")
        if scope_type in {"all", "global"}:
            unrestricted = True
        elif scope_type == "assigned_courses":
            assigned = True
        elif scope_type == "specific_courses":
            specific.update(str(x) for x in scope.get("course_ids", []))
    if unrestricted:
        return {}
    clauses = []
    if assigned:
        clauses.append({"instructor_ids": user_id})
    if specific:
        clauses.append({"_id": {"$in": [ObjectId(x) for x in specific if ObjectId.is_valid(x)]}})
    if not clauses:
        return {"_id": None}
    return clauses[0] if len(clauses) == 1 else {"$or": clauses}
