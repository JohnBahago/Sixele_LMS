from fastapi import APIRouter
from app.database.mongodb import db

router = APIRouter(tags=["Health"])

@router.get("/health")
async def health():
    await db.command("ping")
    return {"status": "ok", "service": "sixele-lms-api"}
