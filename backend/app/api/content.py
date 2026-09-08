from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import mimetypes

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.api.auth import get_current_user
from app.core.config import settings
from app.database.mongodb import db
from app.schemas.content import ContentResponse, ContentStatus, ContentType, ContentUpdate
from app.services.authorization import require_permission, require_course_permission
from app.services.audit import audit_log

router = APIRouter(tags=["Content Library"])

MAX_FILE_SIZE = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".txt", ".csv", ".xls", ".xlsx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm", ".mov", ".mp3", ".wav", ".m4a",
    ".zip"
}


def oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)


def classify(ext: str, mime: str) -> str:
    if ext == ".pdf" or ext in {".doc", ".docx", ".txt"}:
        return ContentType.document.value
    if ext in {".csv", ".xls", ".xlsx"}:
        return ContentType.spreadsheet.value
    if ext in {".ppt", ".pptx"}:
        return ContentType.presentation.value
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return ContentType.image.value
    if ext in {".mp4", ".webm", ".mov"}:
        return ContentType.video.value
    if ext in {".mp3", ".wav", ".m4a"}:
        return ContentType.audio.value
    if ext == ".zip":
        return ContentType.archive.value
    return ContentType.other.value


def response(doc: dict) -> ContentResponse:
    return ContentResponse(
        id=str(doc["_id"]), name=doc["name"], description=doc.get("description", ""),
        original_filename=doc["original_filename"], content_type=doc.get("content_type", "other"),
        mime_type=doc.get("mime_type", "application/octet-stream"), extension=doc.get("extension", ""),
        size_bytes=doc.get("size_bytes", 0), storage_path=doc["storage_path"], url=doc.get("url"),
        folder=doc.get("folder", ""), status=doc.get("status", "active"),
        course_id=str(doc["course_id"]) if doc.get("course_id") else None,
        module_id=str(doc["module_id"]) if doc.get("module_id") else None,
        lesson_id=str(doc["lesson_id"]) if doc.get("lesson_id") else None,
        activity_id=str(doc["activity_id"]) if doc.get("activity_id") else None,
        uploaded_by=str(doc["uploaded_by"]), created_at=doc["created_at"], updated_at=doc["updated_at"]
    )


async def get_content(content_id: str) -> dict:
    doc = await db.content_library.find_one({"_id": oid(content_id)})
    if not doc:
        raise HTTPException(404, "Content item not found")
    return doc


async def check_scope(user: dict, doc: dict, permission: str):
    if doc.get("course_id"):
        course = await db.courses.find_one({"_id": doc["course_id"]})
        if not course:
            raise HTTPException(404, "Linked course not found")
        await require_course_permission(user, permission, course)
    else:
        await require_permission(user, permission)


@router.post("/content", response_model=ContentResponse, status_code=status.HTTP_201_CREATED)
async def upload_content(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    description: str = Form(""),
    folder: str = Form(""),
    course_id: str | None = Form(None),
    module_id: str | None = Form(None),
    lesson_id: str | None = Form(None),
    activity_id: str | None = Form(None),
    user=Depends(get_current_user),
):
    await require_permission(user, "content.upload")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext or '[none]'} is not allowed")

    course = None
    if course_id:
        course = await db.courses.find_one({"_id": oid(course_id)})
        if not course:
            raise HTTPException(404, "Course not found")
        await require_course_permission(user, "content.upload", course)
    if module_id and not await db.modules.find_one({"_id": oid(module_id), "course_id": oid(course_id)}):
        raise HTTPException(400, "Module does not belong to the course")
    if lesson_id:
        lesson = await db.lessons.find_one({"_id": oid(lesson_id)})
        if not lesson:
            raise HTTPException(404, "Lesson not found")
        if module_id and lesson.get("module_id") != oid(module_id):
            raise HTTPException(400, "Lesson does not belong to the module")
    if activity_id:
        activity = await db.activities.find_one({"_id": oid(activity_id)})
        if not activity:
            raise HTTPException(404, "Activity not found")
        if course_id and activity.get("course_id") != oid(course_id):
            raise HTTPException(400, "Activity does not belong to the course")

    safe_name = (name or file.filename or "Untitled").strip()[:255]
    content_id = ObjectId()
    root = Path(getattr(settings, "upload_dir", "uploads"))
    root.mkdir(parents=True, exist_ok=True)
    destination = root / str(content_id) / f"file{ext}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with destination.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_FILE_SIZE:
                    raise HTTPException(413, "File exceeds the 25 MB limit")
                out.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        try: destination.parent.rmdir()
        except OSError: pass
        raise
    finally:
        await file.close()

    now = datetime.now(timezone.utc)
    doc = {
        "_id": content_id, "name": safe_name, "description": description[:2000],
        "original_filename": file.filename or safe_name, "content_type": classify(ext, file.content_type or ""),
        "mime_type": file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream",
        "extension": ext, "size_bytes": total, "storage_path": str(destination), "url": None,
        "folder": folder.strip()[:255], "status": "active", "course_id": oid(course_id) if course_id else None,
        "module_id": oid(module_id) if module_id else None, "lesson_id": oid(lesson_id) if lesson_id else None,
        "activity_id": oid(activity_id) if activity_id else None, "uploaded_by": user["_id"],
        "created_at": now, "updated_at": now,
    }
    await db.content_library.insert_one(doc)
    await audit_log(actor_id=str(user["_id"]), action="content.upload", resource="content", resource_id=str(content_id), details={"filename": doc["original_filename"], "size_bytes": total})
    return response(doc)


@router.get("/content", response_model=list[ContentResponse])
async def list_content(folder: str | None = Query(None), content_type: ContentType | None = Query(None), course_id: str | None = Query(None), status_filter: ContentStatus | None = Query(None, alias="status"), user=Depends(get_current_user)):
    await require_permission(user, "content.view")
    q = {}
    if folder is not None: q["folder"] = folder
    if content_type: q["content_type"] = content_type.value
    if course_id:
        course = await db.courses.find_one({"_id": oid(course_id)})
        if not course: raise HTTPException(404, "Course not found")
        await require_course_permission(user, "content.view", course)
        q["course_id"] = oid(course_id)
    if status_filter: q["status"] = status_filter.value
    docs = await db.content_library.find(q).sort("created_at", -1).to_list(length=500)
    result = []
    for doc in docs:
        try:
            await check_scope(user, doc, "content.view")
            result.append(response(doc))
        except HTTPException:
            continue
    return result


@router.get("/content/{content_id}", response_model=ContentResponse)
async def get_content_endpoint(content_id: str, user=Depends(get_current_user)):
    await require_permission(user, "content.view")
    doc = await get_content(content_id)
    await check_scope(user, doc, "content.view")
    return response(doc)


@router.patch("/content/{content_id}", response_model=ContentResponse)
async def update_content(content_id: str, body: ContentUpdate, user=Depends(get_current_user)):
    await require_permission(user, "content.edit")
    doc = await get_content(content_id)
    await check_scope(user, doc, "content.edit")
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    for key in ("course_id", "module_id", "lesson_id", "activity_id"):
        if key in updates: updates[key] = oid(updates[key])
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.content_library.update_one({"_id": doc["_id"]}, {"$set": updates})
    doc.update(updates)
    await audit_log(actor_id=str(user["_id"]), action="content.update", resource="content", resource_id=content_id)
    return response(doc)


@router.post("/content/{content_id}/archive", response_model=ContentResponse)
async def archive_content(content_id: str, user=Depends(get_current_user)):
    await require_permission(user, "content.delete")
    doc = await get_content(content_id)
    await check_scope(user, doc, "content.delete")
    now = datetime.now(timezone.utc)
    await db.content_library.update_one({"_id": doc["_id"]}, {"$set": {"status": "archived", "updated_at": now}})
    doc.update({"status": "archived", "updated_at": now})
    await audit_log(actor_id=str(user["_id"]), action="content.archive", resource="content", resource_id=content_id)
    return response(doc)


@router.delete("/content/{content_id}", status_code=204)
async def delete_content(content_id: str, user=Depends(get_current_user)):
    await require_permission(user, "content.delete")
    doc = await get_content(content_id)
    await check_scope(user, doc, "content.delete")
    await db.content_library.delete_one({"_id": doc["_id"]})
    path = Path(doc["storage_path"])
    path.unlink(missing_ok=True)
    try: path.parent.rmdir()
    except OSError: pass
    await audit_log(actor_id=str(user["_id"]), action="content.delete", resource="content", resource_id=content_id)


@router.get("/content/{content_id}/download")
async def download_content(content_id: str, user=Depends(get_current_user)):
    await require_permission(user, "content.view")
    doc = await get_content(content_id)
    await check_scope(user, doc, "content.view")
    path = Path(doc["storage_path"])
    if not path.exists(): raise HTTPException(404, "Stored file not found")
    return FileResponse(path, media_type=doc.get("mime_type", "application/octet-stream"), filename=doc["original_filename"])
