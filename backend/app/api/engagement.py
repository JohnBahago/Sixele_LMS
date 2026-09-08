from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.engagement import EngagementLearner, EngagementCourse, EngagementResponse
from app.services.authorization import require_permission, course_visibility_filter, has_course_permission
from app.services.notifications import notify_event
from app.services.audit import audit_log

router = APIRouter(prefix="/reports", tags=["Engagement Analytics"])

def oid(value: str):
    if not ObjectId.is_valid(value): raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

def risk_for(progress: float, days: int, has_activity: bool):
    reasons=[]
    if days >= 14: reasons.append("No learning activity for 14+ days")
    elif days >= 7: reasons.append("No learning activity for 7+ days")
    if progress < 20: reasons.append("Progress is below 20%")
    elif progress < 40: reasons.append("Progress is below 40%")
    if not has_activity: reasons.append("No recorded learning activity")
    if days >= 14 or (progress < 20 and days >= 7): level="critical"
    elif days >= 7 or progress < 40: level="high"
    elif days >= 3 or progress < 60: level="watch"
    else: level="healthy"
    return level, reasons

async def visible_courses(user):
    await require_permission(user, "reports.view")
    filt=await course_visibility_filter(user, "reports.view")
    return await db.courses.find(filt, {"title":1}).sort("title",1).to_list(length=5000)

@router.get("/engagement", response_model=EngagementResponse)
async def engagement(course_id: str | None = Query(None), risk: str | None = Query(None), user=Depends(get_current_user)):
    courses=await visible_courses(user)
    course_map={c["_id"]:c for c in courses}
    ids=list(course_map)
    if course_id:
        cid=oid(course_id)
        if cid not in course_map: raise HTTPException(403,"You do not have report access to this course")
        ids=[cid]
    now=datetime.now(timezone.utc)
    ens=await db.enrollments.find({"course_id":{"$in":ids},"status":{"$in":["active","completed"]}}).to_list(length=50000)
    learner_ids=list({e["learner_id"] for e in ens})
    users=await db.users.find({"_id":{"$in":learner_ids}}, {"full_name":1,"email":1}).to_list(length=len(learner_ids)) if learner_ids else []
    umap={u["_id"]:u for u in users}
    lp=await db.lesson_progress.find({"course_id":{"$in":ids},"completed":True}, {"course_id":1,"learner_id":1,"completed_at":1}).to_list(length=100000) if ids else []
    sub=await db.submissions.find({"course_id":{"$in":ids}}, {"course_id":1,"learner_id":1,"submitted_at":1,"graded_at":1}).to_list(length=100000) if ids else []
    quizzes=await db.quizzes.find({"course_id":{"$in":ids}}, {"_id":1,"course_id":1}).to_list(length=10000) if ids else []
    qmap={q["_id"]:q["course_id"] for q in quizzes}
    attempts=await db.quiz_attempts.find({"quiz_id":{"$in":list(qmap)}}, {"quiz_id":1,"learner_id":1,"submitted_at":1}).to_list(length=100000) if qmap else []
    last={}
    for row in lp:
        k=(row["course_id"],row["learner_id"]); t=row.get("completed_at")
        if t and (k not in last or t>last[k]): last[k]=t
    for row in sub:
        k=(row["course_id"],row["learner_id"]); t=row.get("submitted_at") or row.get("graded_at")
        if t and (k not in last or t>last[k]): last[k]=t
    for row in attempts:
        cid=qmap.get(row["quiz_id"]); k=(cid,row["learner_id"]); t=row.get("submitted_at")
        if cid and t and (k not in last or t>last[k]): last[k]=t
    out=[]
    for e in ens:
        cid=e["course_id"]; lid=e["learner_id"]; p=float(e.get("progress_percent",0)); activity=last.get((cid,lid)); fallback=e.get("updated_at") or e.get("enrolled_at")
        t=activity or fallback; days=max(0,(now-t).days) if t else 0
        level,reasons=risk_for(p,days,bool(activity))
        if risk and level!=risk: continue
        u=umap.get(lid,{})
        out.append(EngagementLearner(enrollment_id=str(e["_id"]),learner_id=str(lid),learner_name=u.get("full_name", "Learner"),email=u.get("email",""),course_id=str(cid),course_title=course_map[cid].get("title",""),status=e.get("status","active"),progress_percent=p,last_activity_at=t,days_inactive=days,risk_level=level,risk_reasons=reasons))
    out.sort(key=lambda x: ({"critical":0,"high":1,"watch":2,"healthy":3}[x.risk_level],-x.days_inactive,x.progress_percent))
    course_rows=[]
    for cid,c in course_map.items():
        base=[e for e in ens if e["course_id"]==cid]
        rows=[]
        for e in base:
            t=last.get((cid,e["learner_id"])) or e.get("updated_at") or e.get("enrolled_at")
            days=max(0,(now-t).days) if t else 0
            level,_=risk_for(float(e.get("progress_percent",0)),days,bool(last.get((cid,e["learner_id"]))))
            rows.append((float(e.get("progress_percent",0)),e.get("status","active"),days,level))
        active=sum(status=="active" for _,status,_,_ in rows)
        avg=round(sum(p for p,_,_,_ in rows)/len(rows),2) if rows else 0
        course_rows.append(EngagementCourse(course_id=str(cid),course_title=c.get("title",""),learners=len(rows),active_learners=active,average_progress=avg,active_7d=sum(d<7 for _,_,d,_ in rows),inactive_7d=sum(d>=7 for _,_,d,_ in rows),at_risk=sum(level in {"high","critical"} for _,_,_,level in rows)))
    counts={k:sum(x.risk_level==k for x in out) for k in ["healthy","watch","high","critical"]}
    return EngagementResponse(learners=out,courses=course_rows,**counts)

@router.post("/engagement/{enrollment_id}/nudge")
async def nudge(enrollment_id: str, user=Depends(get_current_user)):
    await require_permission(user,"reports.view")
    e=await db.enrollments.find_one({"_id":oid(enrollment_id),"status":"active"})
    if not e: raise HTTPException(404,"Active enrollment not found")
    course=await db.courses.find_one({"_id":e["course_id"]},{"title":1})
    if not course or not await has_course_permission(user,"reports.view",course): raise HTTPException(403,"You do not have access to this course")
    docs=await notify_event(event="learning.nudge",recipient_ids=[str(e["learner_id"])],title="Keep your learning momentum",message=f"You have learning progress waiting in {course.get('title','your course')}. Continue your next lesson or activity when you are ready.",notification_type="course",course_id=str(e["course_id"]),action_url=f"/learn/{enrollment_id}/progress",actor_id=str(user["_id"]))
    await audit_log(actor_id=str(user["_id"]),action="engagement.nudge",resource="enrollment",resource_id=enrollment_id,details={"recipient_id":str(e["learner_id"])})
    return {"sent":bool(docs),"notification_id":str(docs[0]["_id"]) if docs else None}
