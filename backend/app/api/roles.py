from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from app.database.mongodb import db
from app.api.auth import get_current_user
from app.schemas.roles import RoleCreate, RoleResponse, AssignRolesRequest, RoleStatusUpdate
from app.core.permissions import PERMISSIONS, PERMISSION_IDS
from app.services.authorization import require_permission
from app.services.audit import audit_log

router = APIRouter(prefix="/roles", tags=["Roles"])

def valid_oid(value: str):
    return ObjectId(value) if ObjectId.is_valid(value) else None

async def role_response(role):
    rid = str(role["_id"])
    return RoleResponse(
        id=rid,
        name=role["name"],
        description=role.get("description", ""),
        permission_ids=role.get("permission_ids", []),
        scope=role.get("scope"),
        is_active=role.get("is_active", True),
        is_system=role.get("is_system", False),
        user_count=await db.users.count_documents({"role_ids": rid}),
        created_at=role.get("created_at", "").isoformat() if hasattr(role.get("created_at"), "isoformat") else str(role.get("created_at", "")),
        updated_at=role.get("updated_at", "").isoformat() if hasattr(role.get("updated_at"), "isoformat") else str(role.get("updated_at", "")),
    )

def validate_permissions(permission_ids: list[str]):
    invalid = set(permission_ids) - PERMISSION_IDS
    if invalid:
        raise HTTPException(400, f"Unknown permissions: {', '.join(sorted(invalid))}")

def normalize_role_ids(role_ids: list[str]) -> list[str]:
    normalized = []
    for role_id in role_ids:
        if not ObjectId.is_valid(role_id):
            raise HTTPException(400, f"Invalid role id: {role_id}")
        value = str(ObjectId(role_id))
        if value not in normalized:
            normalized.append(value)
    return normalized

async def validate_assignable_roles(role_ids: list[str]):
    role_ids = normalize_role_ids(role_ids)
    if not role_ids:
        return []
    docs = await db.roles.find({"_id": {"$in": [ObjectId(x) for x in role_ids]}}).to_list(length=len(role_ids))
    found = {str(x["_id"]): x for x in docs}
    missing = [x for x in role_ids if x not in found]
    if missing:
        raise HTTPException(404, f"Role not found: {missing[0]}")
    inactive = [x for x in role_ids if not found[x].get("is_active", True)]
    if inactive:
        raise HTTPException(409, "Inactive roles cannot be assigned")
    return role_ids

@router.get("/permissions")
async def permission_catalog(user=Depends(get_current_user)):
    await require_permission(user, "roles.view")
    return {"permissions": PERMISSIONS, "groups": sorted({p["group"] for p in PERMISSIONS})}

@router.get("/stats")
async def role_stats(user=Depends(get_current_user)):
    await require_permission(user, "roles.view")
    total = await db.roles.count_documents({})
    active = await db.roles.count_documents({"is_active": True})
    custom = await db.roles.count_documents({"is_system": {"$ne": True}})
    assigned_users = await db.users.count_documents({"role_ids": {"$exists": True, "$ne": []}})
    return {"total_roles": total, "active_roles": active, "custom_roles": custom, "users_with_roles": assigned_users}

@router.get("", response_model=list[RoleResponse])
async def list_roles(active: bool | None = None, user=Depends(get_current_user)):
    await require_permission(user, "roles.view")
    query = {} if active is None else {"is_active": active}
    return [await role_response(role) async for role in db.roles.find(query).sort("name", 1)]

@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(role_id: str, user=Depends(get_current_user)):
    await require_permission(user, "roles.view")
    rid = valid_oid(role_id)
    if not rid:
        raise HTTPException(400, "Invalid role id")
    role = await db.roles.find_one({"_id": rid})
    if not role:
        raise HTTPException(404, "Role not found")
    return await role_response(role)

@router.post("", response_model=RoleResponse, status_code=201)
async def create_role(body: RoleCreate, user=Depends(get_current_user)):
    await require_permission(user, "roles.create")
    name = body.name.strip()
    if await db.roles.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}}):
        raise HTTPException(409, "Role already exists")
    validate_permissions(body.permission_ids)
    now = datetime.now(timezone.utc)
    doc = {**body.model_dump(), "name": name, "created_at": now, "updated_at": now, "is_system": False}
    result = await db.roles.insert_one(doc)
    doc["_id"] = result.inserted_id
    await audit_log(actor_id=str(user["_id"]), action="role.create", resource="role", resource_id=str(result.inserted_id), details={"name": name, "permission_count": len(body.permission_ids)})
    return await role_response(doc)

@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(role_id: str, body: RoleCreate, user=Depends(get_current_user)):
    await require_permission(user, "roles.edit")
    rid = valid_oid(role_id)
    if not rid:
        raise HTTPException(400, "Invalid role id")
    role = await db.roles.find_one({"_id": rid})
    if not role:
        raise HTTPException(404, "Role not found")
    if role.get("is_system"):
        raise HTTPException(403, "System roles cannot be modified")
    name = body.name.strip()
    duplicate = await db.roles.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}, "_id": {"$ne": rid}})
    if duplicate:
        raise HTTPException(409, "Role already exists")
    validate_permissions(body.permission_ids)
    now = datetime.now(timezone.utc)
    data = body.model_dump()
    data["name"] = name
    data["updated_at"] = now
    await db.roles.update_one({"_id": rid}, {"$set": data})
    updated = await db.roles.find_one({"_id": rid})
    await audit_log(actor_id=str(user["_id"]), action="role.update", resource="role", resource_id=role_id, details={"fields": list(body.model_dump().keys())})
    return await role_response(updated)

@router.post("/{role_id}/duplicate", response_model=RoleResponse, status_code=201)
async def duplicate_role(role_id: str, user=Depends(get_current_user)):
    await require_permission(user, "roles.create")
    rid = valid_oid(role_id)
    if not rid:
        raise HTTPException(400, "Invalid role id")
    source = await db.roles.find_one({"_id": rid})
    if not source:
        raise HTTPException(404, "Role not found")
    base = f"{source['name']} Copy"
    name, n = base, 2
    while await db.roles.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}}):
        name = f"{base} {n}"
        n += 1
    now = datetime.now(timezone.utc)
    doc = {"name": name, "description": source.get("description", ""), "permission_ids": list(source.get("permission_ids", [])), "scope": source.get("scope"), "is_active": True, "is_system": False, "created_at": now, "updated_at": now}
    result = await db.roles.insert_one(doc)
    doc["_id"] = result.inserted_id
    await audit_log(actor_id=str(user["_id"]), action="role.duplicate", resource="role", resource_id=str(result.inserted_id), details={"source_role_id": role_id, "name": name})
    return await role_response(doc)

@router.patch("/{role_id}/status", response_model=RoleResponse)
async def update_role_status(role_id: str, body: RoleStatusUpdate, user=Depends(get_current_user)):
    await require_permission(user, "roles.edit")
    rid = valid_oid(role_id)
    if not rid:
        raise HTTPException(400, "Invalid role id")
    role = await db.roles.find_one({"_id": rid})
    if not role:
        raise HTTPException(404, "Role not found")
    if role.get("is_system") and not body.is_active:
        raise HTTPException(403, "System roles cannot be deactivated")
    now = datetime.now(timezone.utc)
    await db.roles.update_one({"_id": rid}, {"$set": {"is_active": body.is_active, "updated_at": now}})
    await audit_log(actor_id=str(user["_id"]), action="role.activate" if body.is_active else "role.deactivate", resource="role", resource_id=role_id)
    return await role_response(await db.roles.find_one({"_id": rid}))

@router.delete("/{role_id}")
async def deactivate_role(role_id: str, user=Depends(get_current_user)):
    await require_permission(user, "roles.delete")
    rid = valid_oid(role_id)
    if not rid:
        raise HTTPException(400, "Invalid role id")
    role = await db.roles.find_one({"_id": rid})
    if not role:
        raise HTTPException(404, "Role not found")
    if role.get("is_system"):
        raise HTTPException(403, "System roles cannot be deleted")
    if await db.users.count_documents({"role_ids": str(rid)}):
        raise HTTPException(409, "Role is assigned to users; reassign users first")
    await db.roles.update_one({"_id": rid}, {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}})
    await audit_log(actor_id=str(user["_id"]), action="role.deactivate", resource="role", resource_id=role_id)
    return {"message": "Role deactivated"}

@router.patch("/users/{user_id}")
async def assign_roles(user_id: str, body: AssignRolesRequest, user=Depends(get_current_user)):
    await require_permission(user, "users.manage")
    uid = valid_oid(user_id)
    if not uid:
        raise HTTPException(400, "Invalid user id")
    target = await db.users.find_one({"_id": uid})
    if not target:
        raise HTTPException(404, "User not found")
    if target.get("is_super_admin"):
        raise HTTPException(403, "Super Admin role assignment is system-controlled")
    role_ids = await validate_assignable_roles(body.role_ids)
    await db.users.update_one({"_id": uid}, {"$set": {"role_ids": role_ids, "updated_at": datetime.now(timezone.utc)}})
    await audit_log(actor_id=str(user["_id"]), action="user.roles.update", resource="user", resource_id=user_id, details={"role_ids": role_ids})
    return {"message": "Roles assigned", "role_ids": role_ids}
