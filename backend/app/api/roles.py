from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.roles import RoleCreate, RoleResponse

router = APIRouter(prefix="/roles", tags=["Roles"])

@router.get("", response_model=list[RoleResponse])
async def list_roles(user=Depends(get_current_user)):
    roles = []
    async for role in db.roles.find({}).sort("name", 1):
        roles.append(RoleResponse(id=str(role["_id"]), name=role["name"], description=role.get("description", ""), permissions=role.get("permissions", []), scope=role.get("scope", {"type":"all","ids":[]}), is_active=role.get("is_active", True)))
    return roles

@router.post("", response_model=RoleResponse, status_code=201)
async def create_role(body: RoleCreate, user=Depends(get_current_user)):
    existing = await db.roles.find_one({"name": body.name})
    if existing:
        raise HTTPException(409, "Role name already exists")
    data = body.model_dump()
    result = await db.roles.insert_one(data)
    return RoleResponse(id=str(result.inserted_id), **data)
