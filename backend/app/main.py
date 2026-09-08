from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse
from app.middleware.security import SecurityMiddleware
from app.core.config import settings as app_settings
from app.database.mongodb import init_db, close_db
from app.services.jobs import JobScheduler
from app.api import health, auth, roles, users, audit, courses, activities, quizzes, enrollments, instructors, instructor_dashboard, notifications, certificates, reports, content, catalog, learner_portal, learner_experience, assignments, instructor_portal, course_builder, course_versions, admin_operations, notification_events, email, jobs, settings as settings_api, cohort_portal, attendance, attendance_compliance

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler = JobScheduler()
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()
        await close_db()

app = FastAPI(title=app_settings.app_name, version="3.4.1", lifespan=lifespan)

if app_settings.environment.lower() in {"production", "prod"} and app_settings.jwt_secret == "change-me-in-production":
    raise RuntimeError("JWT_SECRET must be changed in production")

app.add_middleware(SecurityMiddleware)
origins = [x.strip() for x in app_settings.cors_origins.split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
for router in [health.router, auth.router, roles.router, users.router, audit.router, courses.router, activities.router, quizzes.router, enrollments.router, instructors.router, instructor_dashboard.router, notifications.router, certificates.router, reports.router, content.router, catalog.router, learner_portal.router, learner_experience.router, assignments.router, instructor_portal.router, course_builder.router, admin_operations.router, course_versions.router, notification_events.router, email.router, jobs.router, settings_api.router, cohorts.router, cohort_portal.learner_router, cohort_portal.instructor_router, attendance.router, attendance_compliance.router]:
    app.include_router(router, prefix=app_settings.api_prefix)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": getattr(request.state, "request_id", None)})
