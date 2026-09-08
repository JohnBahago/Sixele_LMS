from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from app.database.mongodb import db
from app.api.auth import get_current_user
from app.schemas.settings import SettingDefinition, SettingUpdate, SettingsResponse
from app.services.authorization import require_permission
from app.services.audit import audit_log

router = APIRouter(prefix="/settings", tags=["System Settings"])

SETTING_CATALOG = [
    ("lms.name", "branding", "LMS Name", "Display name used throughout the LMS.", "Sixele LMS", "string"),
    ("lms.tagline", "branding", "LMS Tagline", "Short description shown with the LMS name.", "Learning. Practice. Progress.", "string"),
    ("courses.default_visibility", "courses", "Default Course Visibility", "Visibility assigned to newly created courses.", "private", "string"),
    ("courses.default_completion_rule", "courses", "Default Completion Rule", "Default completion rule for new courses.", "require_all_lessons", "string"),
    ("enrollment.allow_self_enrollment", "enrollment", "Allow Self Enrollment", "Whether learners may enroll themselves in catalog courses.", True, "boolean"),
    ("enrollment.allow_cancel", "enrollment", "Allow Enrollment Cancellation", "Whether active enrollments may be cancelled by authorized staff.", True, "boolean"),
    ("submissions.default_attempts", "submissions", "Default Submission Attempts", "Default maximum attempts for new activities.", 3, "integer"),
    ("submissions.max_file_size_mb", "submissions", "Maximum Submission File Size", "Maximum size of an individual submission file in MB.", 25, "integer"),
    ("content.max_upload_size_mb", "content", "Maximum Content Upload Size", "Maximum size of an individual content-library file in MB.", 25, "integer"),
    ("content.allowed_extensions", "content", "Allowed Content Extensions", "Comma-separated extensions accepted by the content library.", "pdf,doc,docx,xls,xlsx,ppt,pptx,csv,txt,jpg,jpeg,png,webp,mp4,mp3,wav,zip", "string"),
    ("assessments.default_pass_mark", "assessments", "Default Assessment Pass Mark", "Default percentage required to pass a new assessment.", 50, "number"),
    ("assessments.default_attempts", "assessments", "Default Assessment Attempts", "Default maximum attempts for new assessments.", 2, "integer"),
    ("attendance.minimum_percentage", "attendance", "Minimum Attendance Percentage", "Minimum attendance percentage required for training compliance.", 75, "number"),
    ("attendance.alerts_enabled", "attendance", "Attendance Compliance Alerts", "Automatically notify learners when attendance falls below the compliance threshold.", True, "boolean"),
    ("attendance.warning_margin", "attendance", "Attendance Warning Margin", "Additional percentage-point margin below the minimum threshold used for early warnings.", 5, "number"),
    ("attendance.notify_instructors", "attendance", "Notify Instructors of Attendance Risk", "Notify assigned cohort instructors when a learner enters or leaves attendance risk.", True, "boolean"),
    ("certificates.default_template", "certificates", "Default Certificate Template", "Optional certificate template ID used when issuing certificates.", "", "string"),
    ("certificates.allow_admin_override", "certificates", "Allow Certification Override", "Whether authorized administrators may override normal certificate eligibility.", True, "boolean"),
    ("certificates.auto_issue_on_completion", "certificates", "Automatically Issue Certificates", "Issue a certificate automatically when a learner satisfies all course completion rules.", True, "boolean"),
    ("notifications.email_enabled", "notifications", "Email Notifications Enabled", "Global switch for outbound email notifications.", False, "boolean"),
    ("notifications.in_app_enabled", "notifications", "In-App Notifications Enabled", "Global switch for in-app notifications.", True, "boolean"),
    ("system.maintenance_mode", "system", "Maintenance Mode", "Temporarily restrict non-administrative LMS access.", False, "boolean"),
    ("system.timezone", "system", "System Timezone", "Default timezone used for system-level scheduling and display.", "UTC", "string"),
]
CATALOG = {x[0]: x for x in SETTING_CATALOG}

async def seed_defaults():
    now = datetime.now(timezone.utc)
    for key, category, label, description, value, value_type in SETTING_CATALOG:
        await db.system_settings.update_one(
            {"key": key},
            {"$setOnInsert": {"key": key, "category": category, "label": label, "description": description, "value": value, "value_type": value_type, "editable": True, "created_at": now, "updated_at": now}},
            upsert=True,
        )

def serialize(doc, key):
    definition = CATALOG[key]
    return SettingDefinition(key=key, category=definition[1], label=definition[2], description=definition[3], value=doc.get("value", definition[4]), value_type=definition[5], editable=doc.get("editable", True), updated_at=doc.get("updated_at"))

def validate_value(key, value):
    definition = CATALOG[key]
    value_type = definition[5]
    if value_type == "string" and not isinstance(value, str): raise HTTPException(400, "Value must be a string")
    if value_type == "boolean" and not isinstance(value, bool): raise HTTPException(400, "Value must be boolean")
    if value_type == "integer" and (isinstance(value, bool) or not isinstance(value, int)): raise HTTPException(400, "Value must be an integer")
    if value_type == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))): raise HTTPException(400, "Value must be numeric")
    if key == "courses.default_visibility" and value not in {"private", "catalog", "unlisted"}: raise HTTPException(400, "Invalid course visibility")
    if key == "courses.default_completion_rule" and value not in {"require_all_lessons", "require_activities", "require_assessments", "minimum_score", "require_final_project"}: raise HTTPException(400, "Invalid completion rule")
    if key.endswith("pass_mark") and not 0 <= float(value) <= 100: raise HTTPException(400, "Pass mark must be between 0 and 100")
    if key in {"attendance.minimum_percentage", "attendance.warning_margin"} and not 0 <= float(value) <= 100: raise HTTPException(400, "Attendance percentage must be between 0 and 100")
    if key.endswith("attempts") and value < 1: raise HTTPException(400, "Attempts must be at least 1")
    if key.endswith("max_file_size_mb") and not 1 <= value <= 1024: raise HTTPException(400, "File size must be between 1 and 1024 MB")
    return value

@router.get("", response_model=SettingsResponse)
async def get_settings(user=Depends(get_current_user)):
    await require_permission(user, "settings.view")
    await seed_defaults()
    docs = {d["key"]: d async for d in db.system_settings.find({})}
    return SettingsResponse(settings=[serialize(docs.get(key, {}), key) for key, *_ in SETTING_CATALOG])

@router.get("/{key}", response_model=SettingDefinition)
async def get_setting(key: str, user=Depends(get_current_user)):
    await require_permission(user, "settings.view")
    if key not in CATALOG: raise HTTPException(404, "Setting not found")
    doc = await db.system_settings.find_one({"key": key})
    return serialize(doc or {}, key)

@router.put("/{key}", response_model=SettingDefinition)
async def update_setting(key: str, body: SettingUpdate, user=Depends(get_current_user)):
    await require_permission(user, "settings.edit")
    if key not in CATALOG: raise HTTPException(404, "Setting not found")
    value = validate_value(key, body.value)
    now = datetime.now(timezone.utc)
    await db.system_settings.update_one({"key": key}, {"$set": {"value": value, "updated_at": now, "updated_by": str(user["_id"])}}, upsert=True)
    await audit_log(actor_id=str(user["_id"]), action="settings.update", resource="system_setting", resource_id=key, details={"value": value})
    return serialize(await db.system_settings.find_one({"key": key}), key)

@router.post("/reset/{key}", response_model=SettingDefinition)
async def reset_setting(key: str, user=Depends(get_current_user)):
    await require_permission(user, "settings.edit")
    if key not in CATALOG: raise HTTPException(404, "Setting not found")
    default = CATALOG[key][4]
    now = datetime.now(timezone.utc)
    await db.system_settings.update_one({"key": key}, {"$set": {"value": default, "updated_at": now, "updated_by": str(user["_id"])}}, upsert=True)
    await audit_log(actor_id=str(user["_id"]), action="settings.reset", resource="system_setting", resource_id=key, details={"value": default})
    return serialize(await db.system_settings.find_one({"key": key}), key)
