from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.communications import CommunicationCreate, CommunicationReplyCreate, CommunicationListResponse, CommunicationResponse
from app.services.authorization import require_permission
from app.services.audit import audit_log
from app.services.notifications import notify_event

router = APIRouter(prefix="/communications", tags=["Communications"])

def oid(value: str):
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

async def _author_name(uid):
    u = await db.users.find_one({"_id": oid(uid)}) if ObjectId.is_valid(uid) else None
    return (u or {}).get("full_name") or (u or {}).get("name") or (u or {}).get("email") or "User"

async def _course_info(course_id):
    if not course_id or not ObjectId.is_valid(course_id): return None, ""
    c = await db.courses.find_one({"_id": ObjectId(course_id)})
    return c, (c or {}).get("title", "")

async def _response(doc, uid):
    course, title = await _course_info(doc.get("course_id"))
    author_id = str(doc["author_id"])
    author = await db.users.find_one({"_id": ObjectId(author_id)}) if ObjectId.is_valid(author_id) else None
    roles = author.get("role_ids", []) if author else []
    replies=[]
    for r in doc.get("replies", []):
        replies.append({**r, "id": str(r.get("id")), "author_id": str(r.get("author_id")), "author_name": r.get("author_name", "User")})
    read = uid in set(doc.get("read_by", []))
    return CommunicationResponse(id=str(doc["_id"]), type=doc["type"], title=doc["title"], body=doc["body"], course_id=doc.get("course_id"), course_title=title, author_id=author_id, author_name=(author or {}).get("full_name", "User"), author_role="", is_read=read, status=doc.get("status", "open"), replies=replies, created_at=doc["created_at"], updated_at=doc.get("updated_at", doc["created_at"]))

async def _course_recipients(course_id: str):
    ids=set()
    if not course_id or not ObjectId.is_valid(course_id): return []
    cid=ObjectId(course_id)
    for e in await db.enrollments.find({"course_id":cid,"status":{"$in":["active","in_progress"]}}).to_list(length=5000):
        if e.get("learner_id"): ids.add(str(e["learner_id"]))
    c=await db.courses.find_one({"_id":cid})
    for x in (c or {}).get("instructor_ids", []): ids.add(str(x))
    return list(ids)

@router.get("", response_model=CommunicationListResponse)
async def list_communications(course_id: str | None = None, type_filter: str | None = Query(None, alias="type"), search: str | None = None, status: str | None = None, user=Depends(get_current_user)):
    await require_permission(user, "communications.view")
    uid=str(user["_id"])
    q={"recipient_ids":uid}
    # Authors can also see threads/announcements they created.
    q={"$or":[{"recipient_ids":uid},{"author_id":uid}]}
    if course_id: q["course_id"]=oid(course_id)
    if type_filter: q["type"]=type_filter
    if status: q["status"]=status
    if search: q["$and"]=[{"$or":[{"title":{"$regex":search,"$options":"i"}},{"body":{"$regex":search,"$options":"i"}}]}]
    total=await db.communications.count_documents(q)
    docs=await db.communications.find(q).sort("created_at",-1).limit(500).to_list(length=500)
    unread=await db.communications.count_documents({**q,"read_by":{"$ne":uid}})
    return CommunicationListResponse(items=[await _response(x,uid) for x in docs], unread_count=unread, total=total)

@router.get("/{communication_id}", response_model=CommunicationResponse)
async def get_communication(communication_id: str, user=Depends(get_current_user)):
    await require_permission(user,"communications.view")
    uid=str(user["_id"]); doc=await db.communications.find_one({"_id":oid(communication_id),"$or":[{"recipient_ids":uid},{"author_id":uid}]})
    if not doc: raise HTTPException(404,"Communication not found")
    return await _response(doc,uid)

@router.post("", response_model=CommunicationResponse, status_code=201)
async def create_communication(body: CommunicationCreate, user=Depends(get_current_user)):
    permission="communications.create"
    await require_permission(user,permission)
    uid=str(user["_id"]); course_id=body.course_id
    if course_id:
        c=await db.courses.find_one({"_id":oid(course_id)})
        if not c: raise HTTPException(404,"Course not found")
    recipients=list(dict.fromkeys([x for x in body.recipient_ids if ObjectId.is_valid(x) and x!=uid]))
    if not recipients and course_id:
        recipients=await _course_recipients(course_id)
        recipients=[x for x in recipients if x!=uid]
    now=datetime.now(timezone.utc)
    doc={"type":body.type,"title":body.title,"body":body.body,"course_id":course_id and oid(course_id),"author_id":oid(uid),"recipient_ids":recipients,"read_by":[uid],"status":"open","replies":[],"created_at":now,"updated_at":now}
    r=await db.communications.insert_one(doc); doc["_id"]=r.inserted_id
    if recipients:
        await notify_event(event="communication_created",recipient_ids=recipients,title=body.title,message=body.body[:180],notification_type="course",course_id=course_id,action_url=f"/communication/{r.inserted_id}",actor_id=uid)
    await audit_log(actor_id=uid,action="communication.create",resource="communication",resource_id=str(r.inserted_id),details={"type":body.type,"course_id":course_id,"recipient_count":len(recipients)})
    return await _response(doc,uid)

@router.post("/{communication_id}/replies", response_model=CommunicationResponse)
async def reply_communication(communication_id: str, body: CommunicationReplyCreate, user=Depends(get_current_user)):
    await require_permission(user,"communications.create")
    uid=str(user["_id"]); doc=await db.communications.find_one({"_id":oid(communication_id),"$or":[{"recipient_ids":uid},{"author_id":uid}]})
    if not doc: raise HTTPException(404,"Communication not found")
    if doc.get("status")=="resolved": raise HTTPException(409,"Conversation is resolved")
    author=await db.users.find_one({"_id":oid(uid)}); now=datetime.now(timezone.utc)
    reply={"id":ObjectId(),"author_id":oid(uid),"author_name":(author or {}).get("full_name","User"),"body":body.body,"created_at":now}
    await db.communications.update_one({"_id":doc["_id"]},{"$push":{"replies":reply},"$set":{"updated_at":now}})
    targets=[str(x) for x in doc.get("recipient_ids",[]) if str(x)!=uid]
    if str(doc.get("author_id"))!=uid: targets.append(str(doc["author_id"]))
    targets=list(dict.fromkeys([x for x in targets if ObjectId.is_valid(x)]))
    if targets:
        await notify_event(event="communication_reply",recipient_ids=targets,title=f"Reply: {doc['title']}",message=body.body[:180],notification_type="course",course_id=str(doc.get("course_id")) if doc.get("course_id") else None,action_url=f"/communication/{doc['_id']}",actor_id=uid)
    await audit_log(actor_id=uid,action="communication.reply",resource="communication",resource_id=communication_id,details={"recipient_count":len(targets)})
    fresh=await db.communications.find_one({"_id":doc["_id"]}); return await _response(fresh,uid)

@router.post("/{communication_id}/read", response_model=CommunicationResponse)
async def mark_communication_read(communication_id: str,user=Depends(get_current_user)):
    await require_permission(user,"communications.view")
    uid=str(user["_id"]); doc=await db.communications.find_one_and_update({"_id":oid(communication_id),"$or":[{"recipient_ids":uid},{"author_id":uid}]},{"$addToSet":{"read_by":uid},"$set":{"updated_at":datetime.now(timezone.utc)}},return_document=__import__('pymongo').ReturnDocument.AFTER)
    if not doc: raise HTTPException(404,"Communication not found")
    return await _response(doc,uid)

@router.post("/{communication_id}/resolve", response_model=CommunicationResponse)
async def resolve_communication(communication_id: str,user=Depends(get_current_user)):
    await require_permission(user,"communications.manage")
    uid=str(user["_id"]); doc=await db.communications.find_one({"_id":oid(communication_id),"$or":[{"recipient_ids":uid},{"author_id":uid}]})
    if not doc: raise HTTPException(404,"Communication not found")
    now=datetime.now(timezone.utc); await db.communications.update_one({"_id":doc["_id"]},{"$set":{"status":"resolved","updated_at":now}}); doc["status"]="resolved";doc["updated_at"]=now
    await audit_log(actor_id=uid,action="communication.resolve",resource="communication",resource_id=communication_id)
    return await _response(doc,uid)
