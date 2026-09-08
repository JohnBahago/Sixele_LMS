from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from app.database.mongodb import db
from app.core.security import hash_password, verify_password, create_access_token, decode_access_token
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from app.services.audit import audit_log

router = APIRouter(prefix="/auth", tags=["Authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

async def serialize_user(user: dict) -> UserResponse:
    role_ids = [str(x) for x in user.get("role_ids", [])]
    permissions: set[str] = set()
    if role_ids:
        roles = db.roles.find({"_id": {"$in": [ObjectId(x) for x in role_ids if ObjectId.is_valid(x)]}, "is_active": True})
        async for role in roles:
            permissions.update(role.get("permission_ids", []))
    return UserResponse(id=str(user["_id"]), full_name=user["full_name"], email=user["email"], is_active=user.get("is_active", True), role_ids=role_ids, permissions=sorted(permissions))

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "An account with this email already exists")
    user = {"full_name": body.full_name.strip(), "email": email, "password_hash": hash_password(body.password), "is_active": True, "role_ids": [], "created_at": __import__('datetime').datetime.now(__import__("datetime").timezone.utc)}
    result = await db.users.insert_one(user)
    user["_id"] = result.inserted_id
    response_user = await serialize_user(user)
    await audit_log(actor_id=str(result.inserted_id), action="account.registered", resource="user", resource_id=str(result.inserted_id), request=request)
    return TokenResponse(access_token=create_access_token(str(result.inserted_id)), user=response_user)

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request):
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        await audit_log(actor_id=None, action="auth.login_failed", resource="authentication", details={"email": body.email.lower()}, request=request)
        raise HTTPException(401, "Invalid email or password")
    if not user.get("is_active", True):
        await audit_log(actor_id=str(user["_id"]), action="auth.login_blocked_inactive", resource="authentication", resource_id=str(user["_id"]), request=request)
        raise HTTPException(403, "This account is inactive")
    response_user = await serialize_user(user)
    await audit_log(actor_id=str(user["_id"]), action="auth.login_success", resource="authentication", resource_id=str(user["_id"]), request=request)
    return TokenResponse(access_token=create_access_token(str(user["_id"])), user=response_user)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        user = await db.users.find_one({"_id": ObjectId(user_id), "is_active": True})
    except Exception:
        user = None
    if not user:
        raise HTTPException(401, "Invalid or expired token")
    return user

@router.get("/me", response_model=UserResponse)
async def me(user=Depends(get_current_user)):
    return await serialize_user(user)
