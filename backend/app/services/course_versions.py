from copy import deepcopy
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import HTTPException
from app.database.mongodb import db

CHILD_COLLECTIONS = [
    "modules", "lessons", "resources", "activities", "rubrics", "rubric_criteria",
    "quizzes", "quiz_questions", "assignments"
]

async def snapshot_course(course: dict) -> dict:
    cid = course["_id"]
    snapshot = {"course": deepcopy(course), "collections": {}}
    for name in CHILD_COLLECTIONS:
        docs = await db[name].find({"course_id": cid}).to_list(length=10000)
        # Rubric criteria are linked through rubric_id rather than course_id in this schema.
        if name == "rubric_criteria":
            rubric_ids = [d["_id"] for d in snapshot["collections"].get("rubrics", [])]
            docs = await db[name].find({"rubric_id": {"$in": rubric_ids}}).to_list(length=10000) if rubric_ids else []
        if name == "resources":
            docs = await db[name].find({"course_id": cid}).to_list(length=10000)
        snapshot["collections"][name] = docs
    return snapshot

def counts(snapshot: dict) -> dict:
    return {k: len(v) for k, v in snapshot.get("collections", {}).items()}

def version_response(doc: dict) -> dict:
    snap = doc.get("snapshot", {})
    return {
        "id": str(doc["_id"]), "course_id": str(doc["course_id"]),
        "version_number": doc["version_number"], "status": doc.get("status", "draft"),
        "change_note": doc.get("change_note", ""), "source_version": doc.get("source_version"),
        "created_by": str(doc["created_by"]), "created_at": doc["created_at"],
        "published_at": doc.get("published_at"),
        "published_by": str(doc["published_by"]) if doc.get("published_by") else None,
        "snapshot_counts": counts(snap),
    }

async def get_version(course_id: ObjectId, version_number: int):
    doc = await db.course_versions.find_one({"course_id": course_id, "version_number": version_number})
    if not doc:
        raise HTTPException(404, "Course version not found")
    return doc

async def create_snapshot_version(course: dict, version_number: int, actor_id, status: str, change_note: str = "", source_version=None):
    snap = await snapshot_course(course)
    now = datetime.now(timezone.utc)
    doc = {
        "course_id": course["_id"], "version_number": version_number, "status": status,
        "change_note": change_note, "source_version": source_version,
        "created_by": ObjectId(str(actor_id)), "created_at": now,
        "published_at": now if status == "published" else None,
        "published_by": ObjectId(str(actor_id)) if status == "published" else None,
        "snapshot": snap,
    }
    await db.course_versions.update_one(
        {"course_id": course["_id"], "version_number": version_number},
        {"$set": doc}, upsert=True
    )
    return await db.course_versions.find_one({"course_id": course["_id"], "version_number": version_number})

async def ensure_revision_open(course: dict):
    if course.get("status") == "published":
        raise HTTPException(409, "Published course is immutable. Create a new revision before editing.")

async def open_revision(course: dict, actor_id, change_note: str = ""):
    if course.get("status") != "published":
        raise HTTPException(409, "A revision can only be opened from a published course.")
    current_version = int(course.get("published_version") or course.get("version_number") or 1)
    await create_snapshot_version(course, current_version, course.get("published_by") or actor_id, "published", "Published version", current_version)
    new_version = current_version + 1
    now = datetime.now(timezone.utc)
    await db.courses.update_one({"_id": course["_id"]}, {"$set": {
        "status": "setup", "version_number": new_version, "published_version": current_version,
        "active_revision_version": new_version, "revision_note": change_note,
        "revision_opened_at": now, "revision_opened_by": ObjectId(str(actor_id)), "updated_at": now,
    }})
    return await db.courses.find_one({"_id": course["_id"]})

async def publish_revision(course: dict, actor_id, change_note: str = ""):
    current_version = int(course.get("version_number") or 1)
    published_version = course.get("published_version")
    if published_version == current_version and course.get("status") == "published":
        return await create_snapshot_version(course, current_version, actor_id, "published", change_note or "Published version", current_version)
    snap = await snapshot_course(course)
    now = datetime.now(timezone.utc)
    doc = {
        "course_id": course["_id"], "version_number": current_version, "status": "published",
        "change_note": change_note or course.get("revision_note", ""), "source_version": published_version,
        "created_by": ObjectId(str(actor_id)), "created_at": now, "published_at": now,
        "published_by": ObjectId(str(actor_id)), "snapshot": snap,
    }
    await db.course_versions.update_one({"course_id": course["_id"], "version_number": current_version}, {"$set": doc}, upsert=True)
    return await db.course_versions.find_one({"course_id": course["_id"], "version_number": current_version})

async def restore_snapshot(course: dict, version_doc: dict):
    snap = version_doc["snapshot"]
    course_doc = deepcopy(snap["course"])
    course_id = course["_id"]
    # Preserve the canonical course identity and audit timestamps.
    course_doc["_id"] = course_id
    course_doc["status"] = "setup"
    course_doc["published_version"] = course.get("published_version")
    course_doc["version_number"] = int(course.get("version_number") or version_doc["version_number"] + 1)
    course_doc["updated_at"] = datetime.now(timezone.utc)
    await db.courses.replace_one({"_id": course_id}, course_doc)

    # Restore only versioned instructional content. IDs are preserved so existing progress
    # records continue to point to the same lesson/activity/assessment where possible.
    for name in CHILD_COLLECTIONS:
        docs = deepcopy(snap.get("collections", {}).get(name, []))
        if name == "rubric_criteria":
            continue
        existing = await db[name].find({"course_id": course_id}).to_list(length=10000)
        existing_ids = {d["_id"] for d in existing}
        target_ids = {d["_id"] for d in docs}
        # Do not delete existing learner-linked content. Archive content absent from the target snapshot.
        if name in {"activities", "quizzes", "assignments"}:
            missing = existing_ids - target_ids
            if missing:
                await db[name].update_many({"_id": {"$in": list(missing)}}, {"$set": {"status": "archived", "updated_at": datetime.now(timezone.utc)}})
        else:
            missing = existing_ids - target_ids
            if missing:
                await db[name].delete_many({"_id": {"$in": list(missing)}})
        for doc in docs:
            await db[name].replace_one({"_id": doc["_id"]}, doc, upsert=True)
    return await db.courses.find_one({"_id": course_id})
