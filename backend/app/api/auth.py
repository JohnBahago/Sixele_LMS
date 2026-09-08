from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.database.mongodb import db
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])
bearer = HTTPBearer(auto_error=False)

def serialize_user(user: dict) -> UserResponse:
    return UserResponse(id=str(user["_id"]), full_name=user["full_name"], email=user["email"], is_active=user.get("is_active", True))

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest):
    if await db.users.find_one({"email": body.email.lower()}):
        raise HTTPException(409, "Email is already registered")
    user = {"full_name": body.full_name.strip(), "email": body.email.lower(), "password_hash": hash_password(body.password), "is_active": True, "role_ids": []}
    result = await db.users.insert_one(user)
    user["_id"] = result.inserted_id
    return TokenResponse(access_token=create_access_token(str(result.inserted_id)), user=serialize_user(user))

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.get("is_active", True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User account is inactive")
    return TokenResponse(access_token=create_access_token(str(user["_id"])), user=serialize_user(user))

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if not credentials:
        raise HTTPException(401, "Authentication required")
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        user = await db.users.find_one({"_id": ObjectId(user_id)})
    except (JWTError, ValueError, TypeError):
        user = None
    if not user or not user.get("is_active", True):
        raise HTTPException(401, "Invalid or expired token")
    return user

@router.get("/me", response_model=UserResponse)
async def me(user=Depends(get_current_user)):
    return serialize_user(user)
