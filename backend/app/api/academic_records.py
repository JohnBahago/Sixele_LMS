from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.academic_records import AcademicRecordResponse, AcademicRecordItem
from app.services.authorization import require_permission
from app.api.enrollments import calculate_progress

router = APIRouter(tags=['Academic Records'])

def oid(v):
    if not ObjectId.is_valid(v): raise HTTPException(400, 'Invalid ID')
    return ObjectId(v)

@router.get('/academic-records', response_model=AcademicRecordResponse)
async def academic_record(learner_id: str | None = None, user=Depends(get_current_user)):
    target = user['_id'] if not learner_id else oid(learner_id)
    if target != user['_id']:
        await require_permission(user, 'reports.view')
    learner = await db.users.find_one({'_id': target})
    if not learner: raise HTTPException(404, 'Learner not found')
    enrollments = await db.enrollments.find({'learner_id': target}).sort('enrolled_at', 1).to_list(length=2000)
    records=[]; scores=[]; cert_count=0
    for e in enrollments:
        course=await db.courses.find_one({'_id': e['course_id']})
        if not course: continue
        try:
            progress=await calculate_progress(dict(e))
            score=progress.calculated_score
            progress_percent=progress.progress_percent
            status=progress.status
            completed_at=e.get('completed_at')
        except Exception:
            score=e.get('score')
            progress_percent=e.get('progress_percent',0)
            status=e.get('status','active')
            completed_at=e.get('completed_at')
        if score is not None: scores.append(float(score))
        cert=await db.certificates.find_one({'enrollment_id':e['_id']}, sort=[('issued_at',-1)])
        if cert and cert.get('status')=='issued': cert_count += 1
        records.append(AcademicRecordItem(
            course_id=str(e['course_id']), course_title=course.get('title','Course'),
            enrollment_id=str(e['_id']), status=status,
            enrolled_at=e.get('enrolled_at'), completed_at=completed_at,
            progress_percent=progress_percent or 0, score=score,
            certificate_number=cert.get('certificate_number') if cert else None,
            certificate_status=cert.get('status') if cert else None,
        ))
    completed=sum(1 for r in records if r.status=='completed')
    name=learner.get('full_name') or learner.get('name') or learner.get('email') or 'Learner'
    return AcademicRecordResponse(learner_id=str(target), learner_name=name, email=learner.get('email',''), generated_at=datetime.now(timezone.utc), total_courses=len(records), completed_courses=completed, certificates_issued=cert_count, average_score=round(sum(scores)/len(scores),2) if scores else None, records=records)
