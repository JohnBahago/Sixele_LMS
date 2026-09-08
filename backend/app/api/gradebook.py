from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.auth import get_current_user
from app.database.mongodb import db
from app.services.authorization import require_permission, require_course_permission

router = APIRouter(tags=['Gradebook'])

def oid(v):
    if not ObjectId.is_valid(v): raise HTTPException(400, 'Invalid ID')
    return ObjectId(v)

def pct(score, maximum):
    return round((float(score) / float(maximum)) * 100, 2) if maximum else None

async def course_access(course_id, user, permission='reports.view'):
    course = await db.courses.find_one({'_id': oid(course_id)})
    if not course: raise HTTPException(404, 'Course not found')
    await require_course_permission(user, permission, course)
    return course

async def item_catalog(course_id):
    cid=oid(course_id)
    activities=await db.activities.find({'course_id':cid, 'status': {'$ne':'archived'}}).sort('order',1).to_list(length=1000)
    assignments=await db.assignments.find({'course_id':cid, 'status': {'$ne':'archived'}}).sort('order',1).to_list(length=1000)
    quizzes=await db.quizzes.find({'course_id':cid, 'status': {'$ne':'archived'}}).sort('order',1).to_list(length=1000)
    return activities, assignments, quizzes

async def learner_item_grades(learner_id, activities, assignments, quizzes):
    lid=oid(learner_id); rows=[]
    for a in activities:
        subs=await db.submissions.find({'activity_id':a['_id'],'learner_id':lid}).sort('attempt_number',-1).to_list(length=100)
        graded=next((s for s in subs if s.get('score') is not None), None)
        rows.append({'id':str(a['_id']),'title':a['title'],'category':'activity','max_score':a.get('max_score',100),'pass_mark':a.get('pass_mark',50),'attempts':len(subs),'score':graded.get('score') if graded else None,'percentage':graded.get('percentage') if graded else None,'passed':graded.get('passed') if graded else None,'status':graded.get('status') if graded else ('submitted' if subs else 'not_started'),'graded_at':graded.get('graded_at') if graded else None})
    for a in assignments:
        subs=await db.assignment_submissions.find({'assignment_id':a['_id'],'learner_id':lid}).sort('attempt_number',-1).to_list(length=100)
        graded=next((s for s in subs if s.get('score') is not None), None)
        rows.append({'id':str(a['_id']),'title':a['title'],'category':'assignment','max_score':a.get('max_score',100),'pass_mark':a.get('pass_mark',50),'attempts':len(subs),'score':graded.get('score') if graded else None,'percentage':graded.get('percentage') if graded else None,'passed':graded.get('passed') if graded else None,'status':graded.get('status') if graded else ('submitted' if subs else 'not_started'),'graded_at':graded.get('graded_at') if graded else None})
    for q in quizzes:
        attempts=await db.quiz_attempts.find({'quiz_id':q['_id'],'learner_id':lid}).sort('attempt_number',-1).to_list(length=100)
        graded=next((s for s in attempts if s.get('score') is not None), None)
        total=graded.get('total_points',0) if graded else 0
        rows.append({'id':str(q['_id']),'title':q['title'],'category':'quiz','max_score':total or 0,'pass_mark':q.get('pass_mark',50),'attempts':len(attempts),'score':graded.get('score') if graded else None,'percentage':graded.get('percentage') if graded else None,'passed':graded.get('passed') if graded else None,'status':graded.get('status') if graded else ('submitted' if attempts else 'not_started'),'graded_at':graded.get('graded_at') if graded else None})
    return rows

def summarize(rows, weights):
    cats={k:[r['percentage'] for r in rows if r['category']==k and r['percentage'] is not None] for k in weights}
    available={k:v for k,v in cats.items() if v}
    total_weight=sum(weights[k] for k in available)
    category_scores={k:round(sum(v)/len(v),2) for k,v in available.items()}
    overall=round(sum(category_scores[k]*weights[k] for k in available)/total_weight,2) if total_weight else None
    return category_scores, overall

@router.get('/reports/gradebook')
async def gradebook(course_id: str = Query(...), activity_weight: float = Query(.30, ge=0, le=1), assignment_weight: float = Query(.40, ge=0, le=1), quiz_weight: float = Query(.30, ge=0, le=1), user=Depends(get_current_user)):
    await require_permission(user,'reports.view')
    course=await course_access(course_id,user,'reports.view')
    weights={'activity':activity_weight,'assignment':assignment_weight,'quiz':quiz_weight}
    if sum(weights.values()) <= 0: raise HTTPException(400,'At least one grade category must have a weight')
    activities,assignments,quizzes=await item_catalog(course_id)
    enrollments=await db.enrollments.find({'course_id':oid(course_id),'status':{'$ne':'cancelled'}}).sort('enrolled_at',1).to_list(length=5000)
    learner_ids=[e['learner_id'] for e in enrollments]
    users=await db.users.find({'_id':{'$in':learner_ids}}).to_list(length=5000) if learner_ids else []
    um={str(u['_id']):u for u in users}; learners=[]
    for e in enrollments:
        lid=str(e['learner_id']); rows=await learner_item_grades(lid,activities,assignments,quizzes); cats,overall=summarize(rows,weights)
        learners.append({'learner_id':lid,'learner_name':um.get(lid,{}).get('full_name') or um.get(lid,{}).get('name') or um.get(lid,{}).get('email') or lid,'email':um.get(lid,{}).get('email',''),'enrollment_id':str(e['_id']),'overall_percentage':overall,'category_scores':cats,'items':rows})
    return {'course_id':course_id,'course_title':course.get('title',''),'weights':weights,'categories':{'activity':len(activities),'assignment':len(assignments),'quiz':len(quizzes)},'learners':learners}

@router.get('/learner/grades')
async def learner_grades(course_id: str|None=None, user=Depends(get_current_user)):
    await require_permission(user,'assessments.view')
    enroll_q={'learner_id':user['_id'],'status':{'$ne':'cancelled'}}
    if course_id: enroll_q['course_id']=oid(course_id)
    enrollments=await db.enrollments.find(enroll_q).to_list(length=500)
    result=[]
    for e in enrollments:
        course=await db.courses.find_one({'_id':e['course_id']})
        if not course: continue
        activities,assignments,quizzes=await item_catalog(str(e['course_id']))
        rows=await learner_item_grades(str(user['_id']),activities,assignments,quizzes)
        cats,overall=summarize(rows,{'activity':.30,'assignment':.40,'quiz':.30})
        result.append({'course_id':str(e['course_id']),'course_title':course.get('title',''),'enrollment_id':str(e['_id']),'overall_percentage':overall,'category_scores':cats,'items':rows})
    return result

@router.get('/reports/gradebook/{course_id}/learner/{learner_id}/history')
async def grade_history(course_id:str, learner_id:str, user=Depends(get_current_user)):
    await require_permission(user,'assessments.grade')
    await course_access(course_id,user,'assessments.grade')
    lid=oid(learner_id); cid=oid(course_id); history=[]
    activities,assignments,quizzes=await item_catalog(course_id)
    for a in activities:
        for s in await db.submissions.find({'activity_id':a['_id'],'learner_id':lid}).sort('attempt_number',1).to_list(length=500):
            history.append({'item_id':str(a['_id']),'title':a['title'],'category':'activity','attempt':s.get('attempt_number',1),'score':s.get('score'),'percentage':s.get('percentage'),'status':s.get('status'),'feedback':s.get('feedback',''),'submitted_at':s.get('submitted_at'),'graded_at':s.get('graded_at')})
    for a in assignments:
        for s in await db.assignment_submissions.find({'assignment_id':a['_id'],'learner_id':lid}).sort('attempt_number',1).to_list(length=500):
            history.append({'item_id':str(a['_id']),'title':a['title'],'category':'assignment','attempt':s.get('attempt_number',1),'score':s.get('score'),'percentage':s.get('percentage'),'status':s.get('status'),'feedback':s.get('feedback',''),'submitted_at':s.get('submitted_at'),'graded_at':s.get('graded_at')})
    for q in quizzes:
        for s in await db.quiz_attempts.find({'quiz_id':q['_id'],'learner_id':lid}).sort('attempt_number',1).to_list(length=500):
            history.append({'item_id':str(q['_id']),'title':q['title'],'category':'quiz','attempt':s.get('attempt_number',1),'score':s.get('score'),'percentage':s.get('percentage'),'status':s.get('status'),'feedback':s.get('feedback',''),'submitted_at':s.get('submitted_at'),'graded_at':s.get('graded_at')})
    history.sort(key=lambda x:x.get('submitted_at') or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return {'course_id':course_id,'learner_id':learner_id,'history':history}
