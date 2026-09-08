from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, health, roles
from app.core.config import settings
from app.database.mongodb import close_mongodb

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_mongodb()

app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
origins = [x.strip() for x in settings.cors_origins.split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(roles.router, prefix=settings.api_prefix)

@app.get("/")
async def root():
    return {"name": settings.app_name, "status": "running"}
