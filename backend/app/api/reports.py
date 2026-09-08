import csv
import io
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.reports import ReportOverview, CourseReport, InstructorReport, LearnerReport, SubmissionReport
from app.services.authorization import require_permission, course_visibility_filter
from app.services.audit import audit_log

router = APIRouter(prefix="/reports", tags=["Reports"])

def oid(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

async def visible_course_docs(user):
    await require_permission(user, "reports.view")
    filt = await course_visibility_filter(user, "reports.view")
    return await db.courses.find(filt).sort("title", 1).to_list(length=5000)

async def scoped_course_ids(user, course_id: str | None = None):
    courses = await visible_course_docs(user)
    ids = {c["_id"] for c in courses}
    if course_id:
        cid = oid(course_id)
        if cid not in ids:
            raise HTTPException(403, "You do not have report access to this course")
        return [cid], courses
    return list(ids), courses

@router.get("/overview", response_model=ReportOverview)
async def overview(user=Depends(get_current_user)):
    course_ids, courses = await scoped_course_ids(user)
    enrollment_filter = {"course_id": {"$in": course_ids}} if course_ids else {"_id": None}
    enrollments = await db.enrollments.find(enrollment_filter, {"learner_id":1,"status":1,"progress_percent":1}).to_list(length=100000)
    learners = {e["learner_id"] for e in enrollments}
    active = sum(e.get("status") == "active" for e in enrollments)
    completed = sum(e.get("status") == "completed" for e in enrollments)
    total_non_cancelled = sum(e.get("status") != "cancelled" for e in enrollments)
    avg = round(sum(float(e.get("progress_percent", 0)) for e in enrollments if e.get("status") != "cancelled") / total_non_cancelled, 2) if total_non_cancelled else 0
    submissions = await db.submissions.count_documents({"course_id":{"$in":course_ids},"status":{"$in":["submitted","under_review"]}}) if course_ids else 0
    quizzes = await db.quizzes.find({"course_id":{"$in":course_ids}}, {"_id":1}).to_list(length=10000) if course_ids else []
    attempts_pending = await db.quiz_attempts.count_documents({"quiz_id":{"$in":[q["_id"] for q in quizzes]},"status":"needs_manual_grading"}) if quizzes else 0
    cert_issued = await db.certificates.count_documents({"course_id":{"$in":course_ids},"status":"issued"}) if course_ids else 0
    cert_revoked = await db.certificates.count_documents({"course_id":{"$in":course_ids},"status":"revoked"}) if course_ids else 0
    return ReportOverview(courses=len(courses), published_courses=sum(c.get("status")=="published" for c in courses), learners=len(learners), active_enrollments=active, completed_enrollments=completed, completion_rate=round(completed/total_non_cancelled*100,2) if total_non_cancelled else 0, certificates_issued=cert_issued, certificates_revoked=cert_revoked, submissions_pending=submissions, assessments_pending=attempts_pending, average_course_progress=avg)

@router.get("/courses", response_model=list[CourseReport])
async def course_reports(course_id: str | None = Query(None), status_filter: str | None = Query(None, alias="status"), user=Depends(get_current_user)):
    ids, courses = await scoped_course_ids(user, course_id)
    if status_filter:
        courses = [c for c in courses if c.get("status") == status_filter]
        ids = [c["_id"] for c in courses]
    out=[]
    for c in courses:
        cid=c["_id"]
        ens=await db.enrollments.find({"course_id":cid,"status":{"$ne":"cancelled"}}, {"learner_id":1,"status":1,"progress_percent":1}).to_list(length=10000)
        completed=sum(e.get("status")=="completed" for e in ens); active=sum(e.get("status")=="active" for e in ens)
        acts=await db.activities.find({"course_id":cid},{"_id":1}).to_list(length=10000); act_ids=[a["_id"] for a in acts]
        subs=await db.submissions.find({"course_id":cid},{"status":1}).to_list(length=20000)
        q=await db.quizzes.find({"course_id":cid},{"_id":1}).to_list(length=10000); qids=[x["_id"] for x in q]
        attempts=await db.quiz_attempts.find({"quiz_id":{"$in":qids},"status":"graded"},{"percentage":1}).to_list(length=50000) if qids else []
        pending=sum(s.get("status") in {"submitted","under_review"} for s in subs)
        issued=await db.certificates.count_documents({"course_id":cid,"status":"issued"})
        instructors=len(c.get("instructor_ids",[]))
        avg=round(sum(float(e.get("progress_percent",0)) for e in ens)/len(ens),2) if ens else 0
        score_values=[float(a["percentage"]) for a in attempts if a.get("percentage") is not None]
        out.append(CourseReport(course_id=str(cid),course_title=c.get("title",""),status=c.get("status","draft"),instructors=instructors,enrollments=len(ens),active_learners=active,completed_learners=completed,completion_rate=round(completed/len(ens)*100,2) if ens else 0,average_progress=avg,activities=len(acts),activity_submissions=len(subs),pending_submissions=pending,assessments=len(q),assessment_attempts=len(attempts),average_assessment_score=round(sum(score_values)/len(score_values),2) if score_values else None,certificates_issued=issued))
    return out

@router.get("/instructors", response_model=list[InstructorReport])
async def instructor_reports(user=Depends(get_current_user)):
    course_ids, courses = await scoped_course_ids(user)
    instructor_ids={oid(str(x)) for c in courses for x in c.get("instructor_ids",[]) if ObjectId.is_valid(str(x))}
    users=await db.users.find({"_id":{"$in":list(instructor_ids)}},{"full_name":1,"email":1}).to_list(length=10000) if instructor_ids else []
    out=[]
    for u in users:
        u_courses=[c for c in courses if str(u["_id"]) in {str(x) for x in c.get("instructor_ids",[])}]
        cids=[c["_id"] for c in u_courses]
        ens=await db.enrollments.find({"course_id":{"$in":cids},"status":{"$ne":"cancelled"}},{"learner_id":1,"status":1}).to_list(length=50000)
        q=await db.quizzes.find({"course_id":{"$in":cids}},{"_id":1}).to_list(length=10000)
        pending_ass=await db.quiz_attempts.count_documents({"quiz_id":{"$in":[x["_id"] for x in q]},"status":"needs_manual_grading"}) if q else 0
        pending_sub=await db.submissions.count_documents({"course_id":{"$in":cids},"status":{"$in":["submitted","under_review"]}}) if cids else 0
        unique={e["learner_id"] for e in ens}; completed=sum(e.get("status")=="completed" for e in ens)
        out.append(InstructorReport(instructor_id=str(u["_id"]),instructor_name=u.get("full_name",""),email=u.get("email",""),assigned_courses=len(u_courses),total_learners=len(unique),completed_learners=completed,pending_submissions=pending_sub,pending_assessments=pending_ass))
    return out

@router.get("/learners", response_model=list[LearnerReport])
async def learner_reports(search: str | None = Query(None), user=Depends(get_current_user)):
    course_ids, _ = await scoped_course_ids(user)
    ens=await db.enrollments.find({"course_id":{"$in":course_ids},"status":{"$ne":"cancelled"}},{"learner_id":1,"status":1,"progress_percent":1}).to_list(length=100000) if course_ids else []
    by={}
    for e in ens:
        x=by.setdefault(e["learner_id"],[]); x.append(e)
    users=await db.users.find({"_id":{"$in":list(by)}},{"full_name":1,"email":1}).to_list(length=10000) if by else []
    out=[]
    for u in users:
        if search and search.lower() not in (u.get("full_name","")+" "+u.get("email","")).lower(): continue
        rows=by[u["_id"]]; cert=await db.certificates.count_documents({"learner_id":u["_id"],"course_id":{"$in":course_ids},"status":"issued"})
        out.append(LearnerReport(learner_id=str(u["_id"]),learner_name=u.get("full_name",""),email=u.get("email",""),enrollments=len(rows),active_enrollments=sum(r.get("status")=="active" for r in rows),completed_courses=sum(r.get("status")=="completed" for r in rows),average_progress=round(sum(float(r.get("progress_percent",0)) for r in rows)/len(rows),2),certificates_issued=cert))
    return out

@router.get("/submissions", response_model=list[SubmissionReport])
async def submission_reports(status_filter: str | None = Query(None, alias="status"), limit: int = Query(500, ge=1, le=5000), user=Depends(get_current_user)):
    ids, courses=await scoped_course_ids(user)
    q={"course_id":{"$in":ids}} if ids else {"_id":None}
    if status_filter: q["status"]=status_filter
    docs=await db.submissions.find(q).sort("submitted_at",-1).to_list(length=limit)
    acts=await db.activities.find({"_id":{"$in":[d["activity_id"] for d in docs]}}).to_list(length=limit) if docs else []
    users=await db.users.find({"_id":{"$in":[d["learner_id"] for d in docs]}}).to_list(length=limit) if docs else []
    amap={x["_id"]:x for x in acts}; umap={x["_id"]:x for x in users}; cmap={x["_id"]:x for x in courses}
    return [SubmissionReport(submission_id=str(d["_id"]),activity_id=str(d["activity_id"]),activity_title=amap.get(d["activity_id"],{}).get("title",""),course_id=str(d["course_id"]),course_title=cmap.get(d["course_id"],{}).get("title",""),learner_id=str(d["learner_id"]),learner_name=umap.get(d["learner_id"],{}).get("full_name",""),status=d.get("status","submitted"),score=d.get("score"),percentage=d.get("percentage"),submitted_at=d["submitted_at"],graded_at=d.get("graded_at")) for d in docs]

@router.get("/export")
async def export_report(report: str = Query("courses", pattern="^(courses|instructors|learners|submissions)$"), user=Depends(get_current_user)):
    await require_permission(user, "reports.export")
    if report == "courses": rows=await course_reports(user=user)
    elif report == "instructors": rows=await instructor_reports(user=user)
    elif report == "learners": rows=await learner_reports(user=user)
    else: rows=await submission_reports(user=user)
    data=[r.model_dump() for r in rows]
    output=io.StringIO(); writer=csv.DictWriter(output, fieldnames=list(data[0].keys()) if data else ["message"])
    writer.writeheader()
    if data: writer.writerows(data)
    else: writer.writerow({"message":"No records"})
    output.seek(0)
    await audit_log(actor_id=str(user["_id"]), action="report.export", resource="report", details={"report":report,"rows":len(data)})
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition":f'attachment; filename="sixele-{report}-report.csv"'})
