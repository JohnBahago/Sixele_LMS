from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from app.database.mongodb import db
from app.api.auth import get_current_user
from app.core.security import hash_password
from app.schemas.users import UserCreate, UserUpdate, UserResponse
from app.services.authorization import require_permission
from app.services.audit import audit_log

router = APIRouter(prefix="/users", tags=["Users"])

def oid(value: str):
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid user id")
    return ObjectId(value)

async def serialize_user(user: dict) -> UserResponse:
    role_ids = [str(x) for x in user.get("role_ids", [])]
    role_names, permissions = [], set()
    valid_ids = [ObjectId(x) for x in role_ids if ObjectId.is_valid(x)]
    async for role in db.roles.find({"_id": {"$in": valid_ids}}):
        role_names.append(role["name"])
        permissions.update(role.get("permission_ids", []))
    created = user.get("created_at")
    return UserResponse(
        id=str(user["_id"]), full_name=user["full_name"], email=user["email"],
        is_active=user.get("is_active", True), is_super_admin=user.get("is_super_admin", False),
        role_ids=role_ids, roles=sorted(role_names), permissions=sorted(permissions),
        created_at=created.isoformat() if hasattr(created, "isoformat") else str(created or ""),
    )

@router.get("", response_model=list[UserResponse])
async def list_users(search: str | None = Query(default=None), active: bool | None = None, role_id: str | None = None, user=Depends(get_current_user)):
    await require_permission(user, "users.view")
    query = {}
    if active is not None: query["is_active"] = active
    if search: query["$or"] = [{"full_name": {"$regex": search, "$options": "i"}}, {"email": {"$regex": search, "$options": "i"}}]
    if role_id:
        if not ObjectId.is_valid(role_id): raise HTTPException(400, "Invalid role id")
        query["role_ids"] = str(ObjectId(role_id))
    return [await serialize_user(x) async for x in db.users.find(query).sort("created_at", -1)]

@router.post("", response_model=UserResponse, status_code=201)
async def create_user(body: UserCreate, user=Depends(get_current_user)):
    await require_permission(user, "users.create")
    email = body.email.lower()
    if await db.users.find_one({"email": email}): raise HTTPException(409, "Email already exists")
    role_ids = [str(ObjectId(x)) for x in body.role_ids if ObjectId.is_valid(x)]
    if len(role_ids) != len(body.role_ids): raise HTTPException(400, "One or more role ids are invalid")
    if role_ids:
        roles = await db.roles.find({"_id": {"$in": [ObjectId(x) for x in role_ids]}, "is_active": True}).to_list(length=len(role_ids))
        if len(roles) != len(set(role_ids)): raise HTTPException(409, "All assigned roles must exist and be active")
    now = datetime.now(timezone.utc)
    doc = {"full_name": body.full_name.strip(), "email": email, "password_hash": hash_password(body.password), "is_active": body.is_active, "is_super_admin": False, "role_ids": role_ids, "created_at": now, "updated_at": now}
    result = await db.users.insert_one(doc); doc["_id"] = result.inserted_id
    await audit_log(actor_id=str(user["_id"]), action="user.create", resource="user", resource_id=str(result.inserted_id), details={"email": email})
    return await serialize_user(doc)

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, user=Depends(get_current_user)):
    await require_permission(user, "users.view")
    doc = await db.users.find_one({"_id": oid(user_id)})
    if not doc: raise HTTPException(404, "User not found")
    return await serialize_user(doc)

@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, body: UserUpdate, user=Depends(get_current_user)):
    await require_permission(user, "users.edit")
    target_id = oid(user_id)
    target = await db.users.find_one({"_id": target_id})
    if not target: raise HTTPException(404, "User not found")
    if target.get("is_super_admin"):
        raise HTTPException(403, "The Super Admin account is system-controlled")
    changes = body.model_dump(exclude_unset=True)
    if "email" in changes:
        changes["email"] = changes["email"].lower()
        duplicate = await db.users.find_one({"email": changes["email"], "_id": {"$ne": target_id}})
        if duplicate: raise HTTPException(409, "Email already exists")
    if "role_ids" in changes:
        if any(not ObjectId.is_valid(x) for x in changes["role_ids"]): raise HTTPException(400, "Invalid role id")
        changes["role_ids"] = list(dict.fromkeys(str(ObjectId(x)) for x in changes["role_ids"]))
        if changes["role_ids"]:
            roles = await db.roles.find({"_id": {"$in": [ObjectId(x) for x in changes["role_ids"]]}, "is_active": True}).to_list(length=len(changes["role_ids"]))
            if len(roles) != len(changes["role_ids"]): raise HTTPException(409, "All assigned roles must exist and be active")
    changes["updated_at"] = datetime.now(timezone.utc)
    await db.users.update_one({"_id": target_id}, {"$set": changes})
    updated = await db.users.find_one({"_id": target_id})
    await audit_log(actor_id=str(user["_id"]), action="user.update", resource="user", resource_id=user_id, details={"fields": list(changes.keys())})
    return await serialize_user(updated)

@router.patch("/{user_id}/status", response_model=UserResponse)
async def update_user_status(user_id: str, active: bool, user=Depends(get_current_user)):
    await require_permission(user, "users.edit")
    target_id = oid(user_id)
    target = await db.users.find_one({"_id": target_id})
    if not target: raise HTTPException(404, "User not found")
    if target.get("is_super_admin") and not active:
        raise HTTPException(403, "The Super Admin account cannot be deactivated here")
    now = datetime.now(timezone.utc)
    await db.users.update_one({"_id": target_id}, {"$set": {"is_active": active, "updated_at": now}})
    await audit_log(actor_id=str(user["_id"]), action="user.activate" if active else "user.deactivate", resource="user", resource_id=user_id)
    return await serialize_user(await db.users.find_one({"_id": target_id}))

@router.delete("/{user_id}")
async def deactivate_user(user_id: str, user=Depends(get_current_user)):
    await require_permission(user, "users.delete")
    target_id = oid(user_id)
    target = await db.users.find_one({"_id": target_id})
    if not target: raise HTTPException(404, "User not found")
    if target.get("is_super_admin"): raise HTTPException(403, "The Super Admin account cannot be deactivated here")
    await db.users.update_one({"_id": target_id}, {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}})
    await audit_log(actor_id=str(user["_id"]), action="user.deactivate", resource="user", resource_id=user_id)
    return {"message": "User deactivated"}
