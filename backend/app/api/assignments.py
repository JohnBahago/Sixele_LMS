from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.schemas.assignments import *
from app.services.authorization import require_permission, require_course_permission
from app.services.audit import audit_log
from app.services.notifications import notify_event

router = APIRouter(tags=["Assignments & Final Projects"])

def oid(value: str):
    if not ObjectId.is_valid(value): raise HTTPException(400, "Invalid ID")
    return ObjectId(value)

def response(doc):
    return AssignmentResponse(id=str(doc["_id"]), course_id=str(doc["course_id"]), module_id=str(doc["module_id"]) if doc.get("module_id") else None, title=doc["title"], description=doc.get("description",""), instructions=doc.get("instructions",""), assignment_type=doc.get("assignment_type","assignment"), brief=doc.get("brief",""), deliverables=doc.get("deliverables",[]), submission_type=doc.get("submission_type","text_and_file"), max_score=doc.get("max_score",100), pass_mark=doc.get("pass_mark",50), attempts_allowed=doc.get("attempts_allowed",1), due_days=doc.get("due_days"), is_required=doc.get("is_required",True), order=doc.get("order",0), rubric_id=str(doc["rubric_id"]) if doc.get("rubric_id") else None, status=doc.get("status","draft"), created_by=str(doc["created_by"]), created_at=doc["created_at"], updated_at=doc["updated_at"])

def sub_response(doc):
    return AssignmentSubmissionResponse(id=str(doc["_id"]), assignment_id=str(doc["assignment_id"]), course_id=str(doc["course_id"]), module_id=str(doc["module_id"]) if doc.get("module_id") else None, learner_id=str(doc["learner_id"]), attempt_number=doc["attempt_number"], text_response=doc.get("text_response",""), files=doc.get("files",[]), deliverable_notes=doc.get("deliverable_notes",""), status=doc.get("status","submitted"), score=doc.get("score"), percentage=doc.get("percentage"), passed=doc.get("passed"), grader_id=str(doc["grader_id"]) if doc.get("grader_id") else None, feedback=doc.get("feedback",""), criterion_scores=doc.get("criterion_scores",[]), submitted_at=doc["submitted_at"], graded_at=doc.get("graded_at"), updated_at=doc["updated_at"])

async def get_assignment(aid):
    doc=await db.assignments.find_one({"_id":oid(aid)})
    if not doc: raise HTTPException(404,"Assignment not found")
    return doc

async def course_for(doc):
    course=await db.courses.find_one({"_id":doc["course_id"]})
    if not course: raise HTTPException(404,"Course not found")
    return course

@router.get("/courses/{course_id}/assignments", response_model=list[AssignmentResponse])
async def list_assignments(course_id: str, assignment_type: str|None=Query(None), include_archived: bool=False, user=Depends(get_current_user)):
    course=await db.courses.find_one({"_id":oid(course_id)})
    if not course: raise HTTPException(404,"Course not found")
    await require_course_permission(user,"assignments.view",course)
    q={"course_id":course["_id"]}
    if assignment_type: q["assignment_type"]=assignment_type
    if not include_archived: q["status"]={"$ne":"archived"}
    docs=await db.assignments.find(q).sort("order",1).to_list(length=500)
    return [response(x) for x in docs]

@router.post("/courses/{course_id}/assignments", response_model=AssignmentResponse, status_code=201)
async def create_assignment(course_id: str, body: AssignmentCreate, user=Depends(get_current_user)):
    course=await db.courses.find_one({"_id":oid(course_id)})
    if not course: raise HTTPException(404,"Course not found")
    await require_course_permission(user,"assignments.create",course)
    module_id=oid(body.module_id) if body.module_id else None
    if module_id and not await db.modules.find_one({"_id":module_id,"course_id":course["_id"]}): raise HTTPException(404,"Module not found in this course")
    now=datetime.now(timezone.utc); data=body.model_dump(); data["assignment_type"]=body.assignment_type.value; data["module_id"]=module_id; data["rubric_id"]=oid(body.rubric_id) if body.rubric_id else None
    doc={**data,"course_id":course["_id"],"created_by":user["_id"],"status":"draft","created_at":now,"updated_at":now}
    r=await db.assignments.insert_one(doc); doc["_id"]=r.inserted_id
    await audit_log(actor_id=str(user["_id"]),action="assignment.create",resource="assignment",resource_id=str(r.inserted_id),details={"course_id":course_id,"assignment_type":body.assignment_type.value})
    return response(doc)

@router.get("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def get_assignment_endpoint(assignment_id: str,user=Depends(get_current_user)):
    doc=await get_assignment(assignment_id); course=await course_for(doc); await require_course_permission(user,"assignments.view",course); return response(doc)

@router.patch("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def update_assignment(assignment_id: str, body: AssignmentUpdate,user=Depends(get_current_user)):
    doc=await get_assignment(assignment_id); course=await course_for(doc); await require_course_permission(user,"assignments.edit",course)
    updates={k:v for k,v in body.model_dump().items() if v is not None}
    if "module_id" in updates: updates["module_id"]=oid(updates["module_id"]); 
    if updates.get("module_id") and not await db.modules.find_one({"_id":updates["module_id"],"course_id":course["_id"]}): raise HTTPException(404,"Module not found in this course")
    if "rubric_id" in updates: updates["rubric_id"]=oid(updates["rubric_id"]) if updates["rubric_id"] else None
    if "assignment_type" in updates: updates["assignment_type"]=updates["assignment_type"].value
    updates["updated_at"]=datetime.now(timezone.utc)
    await db.assignments.update_one({"_id":doc["_id"]},{"$set":updates}); doc.update(updates)
    await audit_log(actor_id=str(user["_id"]),action="assignment.update",resource="assignment",resource_id=assignment_id)
    return response(doc)

@router.post("/assignments/{assignment_id}/publish",response_model=AssignmentResponse)
async def publish_assignment(assignment_id:str,user=Depends(get_current_user)):
    doc=await get_assignment(assignment_id); course=await course_for(doc); await require_course_permission(user,"assignments.edit",course)
    now=datetime.now(timezone.utc); await db.assignments.update_one({"_id":doc["_id"]},{"$set":{"status":"published","updated_at":now}}); doc.update(status="published",updated_at=now)
    return response(doc)

@router.post("/assignments/{assignment_id}/archive",response_model=AssignmentResponse)
async def archive_assignment(assignment_id:str,user=Depends(get_current_user)):
    doc=await get_assignment(assignment_id); course=await course_for(doc); await require_course_permission(user,"assignments.edit",course)
    now=datetime.now(timezone.utc); await db.assignments.update_one({"_id":doc["_id"]},{"$set":{"status":"archived","updated_at":now}}); doc.update(status="archived",updated_at=now)
    return response(doc)

@router.delete("/assignments/{assignment_id}",status_code=204)
async def delete_assignment(assignment_id:str,user=Depends(get_current_user)):
    doc=await get_assignment(assignment_id); course=await course_for(doc); await require_course_permission(user,"assignments.delete",course)
    if await db.assignment_submissions.find_one({"assignment_id":doc["_id"]}): raise HTTPException(409,"Assignment has submissions; archive it instead")
    await db.assignments.delete_one({"_id":doc["_id"]})
    await audit_log(actor_id=str(user["_id"]),action="assignment.delete",resource="assignment",resource_id=assignment_id)

@router.post("/assignments/{assignment_id}/submissions",response_model=AssignmentSubmissionResponse,status_code=201)
async def submit_assignment(assignment_id:str,body:AssignmentSubmissionCreate,user=Depends(get_current_user)):
    doc=await get_assignment(assignment_id)
    if doc.get("status")!="published": raise HTTPException(400,"Assignment is not open for submission")
    course=await course_for(doc)
    if await db.enrollments.find_one({"learner_id":user["_id"],"course_id":course["_id"],"status":{"$ne":"cancelled"}}) is None: raise HTTPException(403,"You are not enrolled in this course")
    existing=await db.assignment_submissions.find({"assignment_id":doc["_id"],"learner_id":user["_id"]}).sort("attempt_number",-1).to_list(length=500)
    if existing and existing[0].get("status") not in {"failed","revision_requested"}: raise HTTPException(409,"The current submission is not eligible for resubmission")
    attempt=len(existing)+1
    if attempt>doc.get("attempts_allowed",1): raise HTTPException(400,"Maximum attempts reached")
    now=datetime.now(timezone.utc); sub={"assignment_id":doc["_id"],"course_id":doc["course_id"],"module_id":doc.get("module_id"),"learner_id":user["_id"],"attempt_number":attempt,**body.model_dump(),"status":"submitted","score":None,"percentage":None,"passed":None,"grader_id":None,"feedback":"","criterion_scores":[],"submitted_at":now,"graded_at":None,"updated_at":now}
    r=await db.assignment_submissions.insert_one(sub); sub["_id"]=r.inserted_id
    await db.assignment_progress.update_one({"assignment_id":doc["_id"],"learner_id":user["_id"]},{"$set":{"assignment_id":doc["_id"],"learner_id":user["_id"],"status":"submitted","latest_submission_id":r.inserted_id,"attempts_used":attempt,"updated_at":now}},upsert=True)
    await audit_log(actor_id=str(user["_id"]),action="assignment_submission.create",resource="assignment_submission",resource_id=str(r.inserted_id),details={"assignment_id":assignment_id,"attempt":attempt})
    instructors = await db.course_instructors.find({"course_id":course["_id"], "status":{"$ne":"inactive"}}).to_list(length=100)
    instructor_ids = [str(x.get("instructor_id")) for x in instructors if x.get("instructor_id")]
    if instructor_ids:
        await notify_event(event="submission", recipient_ids=instructor_ids, title="New assignment submission", message="A learner has submitted an assignment for review.", notification_type="submission", course_id=str(course["_id"]), action_url=f"/instructor/assignments/{assignment_id}/submissions", actor_id=str(user["_id"]))
    return sub_response(sub)

@router.get("/assignments/{assignment_id}/submissions",response_model=list[AssignmentSubmissionResponse])
async def list_submissions(assignment_id:str,learner_id:str|None=None,user=Depends(get_current_user)):
    doc=await get_assignment(assignment_id); course=await course_for(doc); await require_course_permission(user,"submissions.view",course)
    q={"assignment_id":doc["_id"]};
    if learner_id:q["learner_id"]=oid(learner_id)
    return [sub_response(x) for x in await db.assignment_submissions.find(q).sort([("submitted_at",-1),("attempt_number",-1)]).to_list(length=1000)]

@router.post("/assignment-submissions/{submission_id}/review",response_model=AssignmentSubmissionResponse)
async def review_assignment_submission(submission_id:str,user=Depends(get_current_user)):
    sid=oid(submission_id); sub=await db.assignment_submissions.find_one({"_id":sid});
    if not sub: raise HTTPException(404,"Submission not found")
    course=await db.courses.find_one({"_id":sub["course_id"]}); await require_course_permission(user,"submissions.review",course)
    if sub.get("status") not in {"submitted","revision_requested"}: raise HTTPException(400,"Submission cannot be moved to review")
    now=datetime.now(timezone.utc); await db.assignment_submissions.update_one({"_id":sid},{"$set":{"status":"under_review","updated_at":now}}); sub.update(status="under_review",updated_at=now); return sub_response(sub)

@router.post("/assignment-submissions/{submission_id}/grade",response_model=AssignmentSubmissionResponse)
async def grade_assignment_submission(submission_id:str,body:GradeAssignmentRequest,user=Depends(get_current_user)):
    sid=oid(submission_id); sub=await db.assignment_submissions.find_one({"_id":sid});
    if not sub: raise HTTPException(404,"Submission not found")
    assignment=await get_assignment(str(sub["assignment_id"])); course=await course_for(assignment); await require_course_permission(user,"assignments.grade",course)
    if body.score>assignment.get("max_score",100): raise HTTPException(400,"Score cannot exceed the assignment maximum score")
    percentage=round(body.score/assignment.get("max_score",100)*100,2); passed=percentage>=assignment.get("pass_mark",50)
    status=body.status or ("passed" if passed else "failed")
    if status=="passed" and not passed: raise HTTPException(400,"A submission below the pass mark cannot be marked passed")
    if status=="failed" and passed: raise HTTPException(400,"A submission meeting the pass mark cannot be marked failed")
    if status not in {"passed","failed","revision_requested"}: raise HTTPException(400,"Invalid submission status")
    if status=="revision_requested": passed=False
    now=datetime.now(timezone.utc); updates={"status":status,"score":body.score,"percentage":percentage,"passed":passed,"grader_id":user["_id"],"feedback":body.feedback,"criterion_scores":body.criterion_scores,"graded_at":now,"updated_at":now}
    await db.assignment_submissions.update_one({"_id":sid},{"$set":updates}); sub.update(updates)
    progress_status="completed" if passed else ("revision_required" if status=="revision_requested" else "failed")
    await db.assignment_progress.update_one({"assignment_id":sub["assignment_id"],"learner_id":sub["learner_id"]},{"$set":{"status":progress_status,"latest_submission_id":sid,"attempts_used":sub["attempt_number"],"score":body.score,"percentage":percentage,"passed":passed,"updated_at":now}},upsert=True)
    await audit_log(actor_id=str(user["_id"]),action="assignment_submission.grade",resource="assignment_submission",resource_id=submission_id,details={"score":body.score,"percentage":percentage,"passed":passed,"status":status})
    event_type = "grading" if status in {"passed", "failed"} else "revision"
    await notify_event(event=event_type, recipient_ids=[str(sub["learner_id"])], title="Assignment result" if status != "revision_requested" else "Revision requested", message=body.feedback or ("Your assignment has been graded." if status != "revision_requested" else "Please review the feedback and resubmit your assignment."), notification_type=event_type, course_id=str(sub["course_id"]), action_url=f"/learner/assignments/{assignment_id}", actor_id=str(user["_id"]))
    return sub_response(sub)

@router.post("/assignment-submissions/{submission_id}/return-for-revision",response_model=AssignmentSubmissionResponse)
async def return_assignment_submission(submission_id:str,body:dict|None=None,user=Depends(get_current_user)):
    sid=oid(submission_id); sub=await db.assignment_submissions.find_one({"_id":sid});
    if not sub: raise HTTPException(404,"Submission not found")
    course=await db.courses.find_one({"_id":sub["course_id"]}); await require_course_permission(user,"submissions.return_for_revision",course)
    now=datetime.now(timezone.utc); feedback=(body or {}).get("feedback",""); updates={"status":"revision_requested","feedback":feedback,"grader_id":user["_id"],"updated_at":now}
    await db.assignment_submissions.update_one({"_id":sid},{"$set":updates}); sub.update(updates)
    await db.assignment_progress.update_one({"assignment_id":sub["assignment_id"],"learner_id":sub["learner_id"]},{"$set":{"status":"revision_required","updated_at":now}})
    return sub_response(sub)

@router.get("/assignments/{assignment_id}/progress",response_model=AssignmentProgressResponse)
async def assignment_progress(assignment_id:str,learner_id:str|None=None,user=Depends(get_current_user)):
    doc=await get_assignment(assignment_id); course=await course_for(doc); target=oid(learner_id) if learner_id else user["_id"]
    if target!=user["_id"]: await require_course_permission(user,"submissions.view",course)
    p=await db.assignment_progress.find_one({"assignment_id":doc["_id"],"learner_id":target}); now=datetime.now(timezone.utc)
    if not p:return AssignmentProgressResponse(assignment_id=assignment_id,learner_id=str(target),status="not_started",latest_submission_id=None,attempts_used=0,score=None,percentage=None,passed=None,updated_at=now)
    return AssignmentProgressResponse(assignment_id=assignment_id,learner_id=str(target),status=p.get("status","not_started"),latest_submission_id=str(p["latest_submission_id"]) if p.get("latest_submission_id") else None,attempts_used=p.get("attempts_used",0),score=p.get("score"),percentage=p.get("percentage"),passed=p.get("passed"),updated_at=p["updated_at"])
