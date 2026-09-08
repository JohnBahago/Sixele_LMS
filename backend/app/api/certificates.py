from datetime import datetime, timezone
from uuid import uuid4
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.certificates import (
    CertificateTemplateCreate, CertificateTemplateUpdate, CertificateTemplateResponse,
    CertificateIssueRequest, CertificateResponse, CertificateVerificationResponse
)
from app.services.authorization import require_permission, require_course_permission
from app.services.audit import audit_log
from app.services.notifications import create_notifications
from app.api.enrollments import calculate_progress
from app.services.certificate_pdf import generate_certificate_pdf

router = APIRouter(tags=["Certificates"])

def oid(value: str):
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

def template_response(doc):
    return CertificateTemplateResponse(
        id=str(doc["_id"]), name=doc["name"], description=doc.get("description", ""),
        title=doc.get("title", "Certificate of Completion"), issuer_name=doc["issuer_name"],
        body_text=doc.get("body_text", ""), signature_name=doc.get("signature_name", ""),
        signature_title=doc.get("signature_title", ""), is_active=doc.get("is_active", True),
        created_by=str(doc["created_by"]), created_at=doc["created_at"], updated_at=doc["updated_at"]
    )

def cert_response(doc):
    return CertificateResponse(
        id=str(doc["_id"]), certificate_number=doc["certificate_number"],
        enrollment_id=str(doc["enrollment_id"]), learner_id=str(doc["learner_id"]),
        course_id=str(doc["course_id"]), learner_name=doc["learner_name"],
        course_title=doc["course_title"], template_id=str(doc["template_id"]) if doc.get("template_id") else None,
        status=doc["status"], issued_at=doc["issued_at"], revoked_at=doc.get("revoked_at"),
        revoked_by=str(doc["revoked_by"]) if doc.get("revoked_by") else None,
        revocation_reason=doc.get("revocation_reason"), completion_score=doc.get("completion_score"),
        verification_url=doc["verification_url"], override_used=doc.get("override_used", False),
        override_reason=doc.get("override_reason"), pdf_url=doc.get("pdf_url"), pdf_generated=bool(doc.get("pdf_path"))
    )



async def issue_certificate_for_enrollment(enrollment: dict, *, actor_id: str | None = None, automatic: bool = False, template_id: str | None = None, force_override: bool = False, override_reason: str | None = None):
    """Internal certificate issuance service used by manual and automatic completion flows."""
    eid = enrollment["_id"]
    course = await db.courses.find_one({"_id": enrollment["course_id"]})
    if not course:
        return None
    learner = await db.users.find_one({"_id": enrollment["learner_id"]})
    if not learner:
        return None
    progress = await calculate_progress(dict(enrollment))
    if not progress.completed and not force_override:
        return None
    existing = await db.certificates.find_one({"enrollment_id": eid, "status": "issued"})
    if existing:
        return existing

    selected_template_id = template_id
    if not selected_template_id:
        configured = await db.system_settings.find_one({"key": "certificates.default_template"})
        selected_template_id = configured.get("value") if configured else None
    template = None
    if selected_template_id:
        try:
            template = await db.certificate_templates.find_one({"_id": oid(str(selected_template_id)), "is_active": True})
        except Exception:
            template = None
    if template is None:
        template = await db.certificate_templates.find_one({"is_active": True}, sort=[("created_at", -1)])

    now = datetime.now(timezone.utc)
    number = f"SIX-{now.year}-{uuid4().hex[:10].upper()}"
    verification_url = f"/api/certificates/verify/{number}"
    issuer_id = ObjectId(actor_id) if actor_id and ObjectId.is_valid(str(actor_id)) else None
    doc = {
        "certificate_number": number, "enrollment_id": eid, "learner_id": enrollment["learner_id"],
        "course_id": enrollment["course_id"], "learner_name": learner.get("full_name", learner.get("name", "Learner")),
        "course_title": course.get("title", "Course"), "template_id": template["_id"] if template else None,
        "status": "issued", "issued_at": now, "revoked_at": None, "revoked_by": None,
        "revocation_reason": None, "completion_score": progress.calculated_score,
        "verification_url": verification_url, "override_used": force_override,
        "override_reason": override_reason if force_override else None, "issued_by": issuer_id,
        "automatic": automatic,
    }
    try:
        result = await db.certificates.insert_one(doc)
    except Exception as exc:
        # Unique enrollment_id protects against duplicate automatic issuance races.
        existing = await db.certificates.find_one({"enrollment_id": eid, "status": "issued"})
        if existing:
            return existing
        raise exc
    doc["_id"] = result.inserted_id
    try:
        pdf_path = generate_certificate_pdf(doc, template)
        doc["pdf_path"] = pdf_path
        doc["pdf_url"] = f"/api/certificates/{result.inserted_id}/download"
        await db.certificates.update_one({"_id": result.inserted_id}, {"$set": {"pdf_path": pdf_path, "pdf_url": doc["pdf_url"]}})
    except Exception as exc:
        await audit_log(actor_id=actor_id, action="certificate.pdf.failed", resource="certificate", resource_id=str(result.inserted_id), details={"error": str(exc)[:1000]})
    await audit_log(actor_id=actor_id, action="certificate.issue.automatic" if automatic else "certificate.issue", resource="certificate", resource_id=str(result.inserted_id), details={"certificate_number": number, "automatic": automatic, "override_used": force_override, "pdf_generated": bool(doc.get("pdf_path"))})
    await create_notifications(recipient_ids=[str(enrollment["learner_id"])], title="Certificate issued", message=f"Your certificate for {course.get('title', 'the course')} has been issued.", notification_type="completion", course_id=str(course["_id"]), action_url=verification_url, actor_id=actor_id)
    return doc

@router.get("/certificate-templates", response_model=list[CertificateTemplateResponse])
async def list_templates(user=Depends(get_current_user)):
    await require_permission(user, "certificates.view")
    docs = await db.certificate_templates.find({}).sort("created_at", -1).to_list(length=500)
    return [template_response(x) for x in docs]

@router.post("/certificate-templates", response_model=CertificateTemplateResponse, status_code=201)
async def create_template(body: CertificateTemplateCreate, user=Depends(get_current_user)):
    await require_permission(user, "certificates.manage_templates")
    now = datetime.now(timezone.utc)
    doc = {**body.model_dump(), "created_by": user["_id"], "created_at": now, "updated_at": now}
    result = await db.certificate_templates.insert_one(doc); doc["_id"] = result.inserted_id
    await audit_log(actor_id=str(user["_id"]), action="certificate_template.create", resource="certificate_template", resource_id=str(result.inserted_id))
    return template_response(doc)

@router.patch("/certificate-templates/{template_id}", response_model=CertificateTemplateResponse)
async def update_template(template_id: str, body: CertificateTemplateUpdate, user=Depends(get_current_user)):
    await require_permission(user, "certificates.manage_templates")
    tid = oid(template_id); doc = await db.certificate_templates.find_one({"_id": tid})
    if not doc: raise HTTPException(404, "Certificate template not found")
    updates = {k:v for k,v in body.model_dump().items() if v is not None}
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.certificate_templates.update_one({"_id": tid}, {"$set": updates}); doc.update(updates)
    await audit_log(actor_id=str(user["_id"]), action="certificate_template.update", resource="certificate_template", resource_id=template_id)
    return template_response(doc)

@router.delete("/certificate-templates/{template_id}", status_code=204)
async def delete_template(template_id: str, user=Depends(get_current_user)):
    await require_permission(user, "certificates.manage_templates")
    tid = oid(template_id)
    if await db.certificates.find_one({"template_id": tid, "status": "issued"}):
        raise HTTPException(409, "Template is used by an issued certificate; deactivate it instead")
    result = await db.certificate_templates.delete_one({"_id": tid})
    if result.deleted_count == 0: raise HTTPException(404, "Certificate template not found")
    await audit_log(actor_id=str(user["_id"]), action="certificate_template.delete", resource="certificate_template", resource_id=template_id)

@router.post("/certificates/issue", response_model=CertificateResponse, status_code=201)
async def issue_certificate(body: CertificateIssueRequest, user=Depends(get_current_user)):
    await require_permission(user, "certificates.issue")
    eid = oid(body.enrollment_id)
    enrollment = await db.enrollments.find_one({"_id": eid})
    if not enrollment:
        raise HTTPException(404, "Enrollment not found")
    course = await db.courses.find_one({"_id": enrollment["course_id"]})
    if not course:
        raise HTTPException(404, "Course not found")
    await require_course_permission(user, "certificates.issue", course)
    if body.force_override:
        await require_permission(user, "certificates.manage")
        if not body.override_reason or not body.override_reason.strip():
            raise HTTPException(400, "override_reason is required when force_override is true")
    doc = await issue_certificate_for_enrollment(enrollment, actor_id=str(user["_id"]), automatic=False, template_id=body.template_id, force_override=body.force_override, override_reason=body.override_reason)
    if not doc:
        raise HTTPException(409, "Learner is not eligible for certification; course completion requirements are not satisfied")
    return cert_response(doc)

@router.get("/certificates", response_model=list[CertificateResponse])
async def list_certificates(learner_id: str | None = Query(None), course_id: str | None = Query(None), user=Depends(get_current_user)):
    if learner_id and oid(learner_id) != user["_id"]:
        await require_permission(user, "certificates.view")
    elif not learner_id:
        await require_permission(user, "certificates.view")
    q = {}
    if learner_id: q["learner_id"] = oid(learner_id)
    elif not user.get("is_super_admin") and not await _has_global_certificate_view(user): q["learner_id"] = user["_id"]
    if course_id: q["course_id"] = oid(course_id)
    docs = await db.certificates.find(q).sort("issued_at", -1).to_list(length=500)
    return [cert_response(x) for x in docs]

async def _has_global_certificate_view(user):
    if user.get("is_super_admin"): return True
    from app.services.authorization import _roles_for_user
    for role in await _roles_for_user(user):
        if "certificates.view" not in role.get("permission_ids", []): continue
        scope = role.get("scope") or {}
        if scope.get("type", "all") in {"all", "global"}: return True
    return False

@router.post("/certificates/{certificate_id}/revoke", response_model=CertificateResponse)
async def revoke_certificate(certificate_id: str, reason: str = Query(..., min_length=3, max_length=1000), user=Depends(get_current_user)):
    await require_permission(user, "certificates.revoke")
    cid = oid(certificate_id); doc = await db.certificates.find_one({"_id": cid})
    if not doc: raise HTTPException(404, "Certificate not found")
    course = await db.courses.find_one({"_id": doc["course_id"]})
    if course: await require_course_permission(user, "certificates.revoke", course)
    if doc["status"] == "revoked": return cert_response(doc)
    now = datetime.now(timezone.utc)
    updates = {"status":"revoked", "revoked_at":now, "revoked_by":user["_id"], "revocation_reason":reason.strip()}
    await db.certificates.update_one({"_id":cid},{"$set":updates}); doc.update(updates)
    await audit_log(actor_id=str(user["_id"]), action="certificate.revoke", resource="certificate", resource_id=certificate_id, details={"reason": reason.strip()})
    return cert_response(doc)

@router.get("/certificates/{certificate_id}/download")
async def download_certificate(certificate_id: str, user=Depends(get_current_user)):
    cid = oid(certificate_id)
    doc = await db.certificates.find_one({"_id": cid})
    if not doc:
        raise HTTPException(404, "Certificate not found")
    if doc.get("learner_id") != user["_id"]:
        await require_permission(user, "certificates.view")
    path = doc.get("pdf_path")
    if not path:
        raise HTTPException(404, "Certificate PDF has not been generated")
    from pathlib import Path
    pdf = Path(path)
    if not pdf.exists() or pdf.suffix.lower() != ".pdf":
        raise HTTPException(404, "Certificate PDF is unavailable")
    return FileResponse(str(pdf), media_type="application/pdf", filename=f"{doc['certificate_number']}.pdf")


@router.get("/certificates/verify/{certificate_number}", response_model=CertificateVerificationResponse)
async def verify_certificate(certificate_number: str):
    doc = await db.certificates.find_one({"certificate_number": certificate_number.strip().upper()})
    if not doc:
        return CertificateVerificationResponse(valid=False, certificate_number=certificate_number, message="Certificate not found")
    template = await db.certificate_templates.find_one({"_id": doc["template_id"]}) if doc.get("template_id") else None
    valid = doc.get("status") == "issued"
    return CertificateVerificationResponse(valid=valid, certificate_number=doc["certificate_number"], status=doc.get("status"), learner_name=doc.get("learner_name"), course_title=doc.get("course_title"), issued_at=doc.get("issued_at"), completion_score=doc.get("completion_score"), issuer_name=template.get("issuer_name") if template else None, message="Certificate is valid" if valid else "Certificate has been revoked")
