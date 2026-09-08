import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, Clock3, FileCheck2, Send, RotateCcw, Trophy, XCircle } from 'lucide-react'
import { api } from '../../services/api'

const keyFor = (e, q) => `sixele.quiz.${e}.${q}.answers`
const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2,'0')}:${String(s % 60).padStart(2,'0')}`

function ResultBanner({ passed, percentage, status, feedback }) {
  const good = passed === true
  return <div className={`rounded-2xl border p-5 ${good ? 'six-primary-soft' : passed === false ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'}`}>
    <div className="flex gap-4 items-start">
      {good ? <CheckCircle2 className="six-primary-text"/> : passed === false ? <XCircle className="text-red-600"/> : <Trophy className="text-amber-600"/>}
      <div className="flex-1"><div className="font-bold">{good ? 'Assessment passed' : passed === false ? 'Assessment not passed' : 'Assessment submitted'}</div>
      <div className="text-sm six-muted mt-1">{status === 'needs_manual_grading' ? 'Your written responses are awaiting instructor grading.' : percentage != null ? `Score: ${Number(percentage).toFixed(1)}%` : 'Your result will appear here when grading is complete.'}</div>
      {feedback && <div className="mt-3 text-sm whitespace-pre-wrap">{feedback}</div>}</div>
    </div>
  </div>
}

export default function AssessmentExperience(){
  const { enrollmentId, assessmentType, itemId } = useParams()
  const [detail,setDetail]=useState(null), [attempts,setAttempts]=useState([]), [answers,setAnswers]=useState({}), [remaining,setRemaining]=useState(null), [busy,setBusy]=useState(false), [error,setError]=useState(''), [submitted,setSubmitted]=useState(null)
  const quiz = assessmentType === 'quiz' || assessmentType === 'assessment'
  const load = async()=>{
    try {
      setError('')
      const d = quiz ? await api.learnerQuiz(enrollmentId,itemId) : assessmentType === 'assignment' ? await api.learnerAssignment(enrollmentId,itemId) : await api.learnerActivity(enrollmentId,itemId)
      setDetail(d)
      if(quiz){
        const a=await api.quizAttempts(itemId)
        setAttempts(a||[])
        const raw=localStorage.getItem(keyFor(enrollmentId,itemId)); if(raw) setAnswers(JSON.parse(raw))
      } else if(assessmentType==='assignment') setAttempts(await api.learnerAssignmentSubmissions(enrollmentId,itemId))
    } catch(e){setError(e.message)}
  }
  useEffect(()=>{load()},[enrollmentId,itemId,assessmentType])
  useEffect(()=>{if(quiz && Object.keys(answers).length) localStorage.setItem(keyFor(enrollmentId,itemId),JSON.stringify(answers))},[answers,enrollmentId,itemId,quiz])
  useEffect(()=>{
    if(!quiz || !detail?.time_limit_minutes || detail.attempts_used>=detail.attempts_allowed || submitted) return
    const startedKey=`sixele.quiz.${enrollmentId}.${itemId}.started`
    let started=Number(localStorage.getItem(startedKey)); if(!started){started=Date.now();localStorage.setItem(startedKey,String(started))}
    const tick=()=>setRemaining(Math.max(0,detail.time_limit_minutes*60-Math.floor((Date.now()-started)/1000)))
    tick(); const t=setInterval(tick,1000); return()=>clearInterval(t)
  },[quiz,detail,enrollmentId,itemId,submitted])
  useEffect(()=>{if(remaining===0 && detail && !submitted) submitQuiz(true)},[remaining])

  const answeredCount=useMemo(()=>Object.values(answers).filter(v=>Array.isArray(v)?v.length:v!==''&&v!=null).length,[answers])
  const canSubmit = detail && detail.attempts_used < detail.attempts_allowed && !busy && !submitted

  async function submitQuiz(auto=false){
    if(!detail || busy) return
    setBusy(true);setError('')
    try {
      const payload={answers:Object.entries(answers).map(([question_id,answer])=>({question_id,answer}))}
      const result=await api.submitQuiz(enrollmentId,itemId,payload); setSubmitted(result); localStorage.removeItem(keyFor(enrollmentId,itemId)); localStorage.removeItem(`sixele.quiz.${enrollmentId}.${itemId}.started`); await load()
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }

  async function submitAssignment(){
    setBusy(true);setError('');try{const result=await api.submitAssignment(enrollmentId,itemId,{text_response:answers.text||'',files:[],deliverable_notes:answers.notes||''});setSubmitted(result);await load()}catch(e){setError(e.message)}finally{setBusy(false)}
  }

  if(error) return <div className="six-surface border p-6 text-red-600">{error}</div>
  if(!detail) return <div className="six-muted">Loading assessment…</div>
  const latest = attempts?.length ? attempts[attempts.length-1] : null
  return <div className="max-w-5xl mx-auto space-y-5">
    <Link to={`/learn/${enrollmentId}`} className="six-muted text-sm inline-flex items-center gap-2"><ArrowLeft size={16}/> Back to course</Link>
    <div className="six-surface border p-6 md:p-8">
      <div className="flex flex-wrap justify-between gap-4 items-start"><div><div className="text-xs uppercase tracking-wide six-primary-text font-semibold">{quiz?'Assessment':assessmentType}</div><h1 className="text-3xl font-bold mt-2">{detail.title}</h1><p className="six-muted mt-2">{detail.description}</p></div>{quiz&&detail.time_limit_minutes&&<div className="border rounded-2xl px-4 py-3 flex items-center gap-2 font-semibold"><Clock3 size={18}/>{remaining!=null?fmt(remaining):`${detail.time_limit_minutes} min`}</div>}</div>
      {quiz && <div className="grid sm:grid-cols-3 gap-3 mt-6"><div className="border rounded-xl p-3"><div className="text-xs six-muted">Pass mark</div><b>{detail.pass_mark}%</b></div><div className="border rounded-xl p-3"><div className="text-xs six-muted">Attempts</div><b>{detail.attempts_used}/{detail.attempts_allowed}</b></div><div className="border rounded-xl p-3"><div className="text-xs six-muted">Questions answered</div><b>{answeredCount}/{detail.question_count}</b></div></div>}
      {submitted && <div className="mt-6"><ResultBanner passed={submitted.passed} percentage={submitted.percentage} status={submitted.status} feedback={submitted.message}/></div>}
      {!submitted && quiz && <>
        {detail.instructions&&<div className="mt-7 rounded-xl bg-[var(--hover)] p-4 whitespace-pre-wrap six-muted">{detail.instructions}</div>}
        <div className="mt-7 space-y-5">{detail.questions.map((q,i)=><div key={q.id} className="border rounded-2xl p-5"><div className="flex justify-between gap-4"><div className="font-semibold">{i+1}. {q.question_text}</div><span className="text-xs six-muted">{q.points} pt</span></div><div className="mt-4 space-y-2">{q.question_type==='essay'||q.question_type==='short_answer'?<textarea className="six-input rounded-xl w-full p-3 min-h-32" value={answers[q.id]||''} onChange={e=>setAnswers({...answers,[q.id]:e.target.value})} placeholder="Enter your answer…"/>:q.options.map((o,j)=><label key={j} className="flex gap-3 items-center border rounded-xl p-3 cursor-pointer"><input type={q.question_type==='multiple_choice'?'checkbox':'radio'} name={q.id} checked={q.question_type==='multiple_choice'?(answers[q.id]||[]).includes(o):(answers[q.id]||'')===o} onChange={e=>{if(q.question_type==='multiple_choice'){const a=answers[q.id]||[];setAnswers({...answers,[q.id]:e.target.checked?[...a,o]:a.filter(x=>x!==o)})}else setAnswers({...answers,[q.id]:o})}}/><span>{o}</span></label>)}</div></div>)}</div>
        <button disabled={!canSubmit} onClick={()=>submitQuiz(false)} className="six-button mt-7 px-5 py-3 rounded-xl inline-flex items-center gap-2"><Send size={17}/>{busy?'Submitting…':'Submit assessment'}</button>
      </>}
      {!submitted && !quiz && assessmentType==='assignment' && <>
        <div className="mt-7 grid lg:grid-cols-2 gap-5"><div><h3 className="font-semibold">Brief</h3><p className="six-muted mt-2 whitespace-pre-wrap">{detail.brief||detail.instructions||detail.description}</p><h3 className="font-semibold mt-6">Deliverables</h3><ul className="list-disc ml-5 six-muted mt-2 space-y-1">{(detail.deliverables||[]).map((d,i)=><li key={i}>{typeof d==='string'?d:d.label||d.title}</li>)}</ul></div><div><label className="font-semibold">Your submission</label><textarea className="six-input rounded-xl w-full p-3 min-h-48 mt-2" value={answers.text||''} onChange={e=>setAnswers({...answers,text:e.target.value})} placeholder="Write your response…"/><label className="font-semibold block mt-4">Deliverable notes</label><textarea className="six-input rounded-xl w-full p-3 min-h-28 mt-2" value={answers.notes||''} onChange={e=>setAnswers({...answers,notes:e.target.value})}/></div></div><button disabled={!canSubmit} onClick={submitAssignment} className="six-button mt-6 px-5 py-3 rounded-xl inline-flex items-center gap-2"><FileCheck2 size={17}/>{busy?'Submitting…':'Submit assignment'}</button>
      </>}
      {!submitted && !quiz && assessmentType==='activity' && <><div className="mt-7"><h3 className="font-semibold">Instructions</h3><p className="six-muted mt-2 whitespace-pre-wrap">{detail.instructions}</p><h3 className="font-semibold mt-6">Task</h3><p className="six-muted mt-2 whitespace-pre-wrap">{detail.task_description}</p><textarea className="six-input rounded-xl w-full p-3 min-h-44 mt-6" value={answers.text||''} onChange={e=>setAnswers({...answers,text:e.target.value})} placeholder="Enter your response or evidence notes…"/></div><button disabled={!canSubmit} onClick={async()=>{setBusy(true);try{const r=await api.submitActivity(enrollmentId,itemId,{text_response:answers.text||'',files:[],checklist:[],evidence_notes:''});setSubmitted(r);await load()}catch(e){setError(e.message)}finally{setBusy(false)}}} className="six-button mt-6 px-5 py-3 rounded-xl"><Send size={17}/> Submit activity</button></>}
      {(detail.percentage!=null || detail.score!=null || latest) && <div className="mt-8 border-t pt-6"><h2 className="font-bold">Your results</h2><div className="grid sm:grid-cols-3 gap-3 mt-4"><div className="border rounded-xl p-4"><div className="text-xs six-muted">Score</div><div className="text-xl font-bold">{detail.percentage!=null?`${Number(detail.percentage).toFixed(1)}%`:latest?.percentage!=null?`${Number(latest.percentage).toFixed(1)}%`:'Pending'}</div></div><div className="border rounded-xl p-4"><div className="text-xs six-muted">Status</div><div className="font-semibold mt-1">{detail.passed===true||latest?.passed===true?'Passed':detail.passed===false||latest?.passed===false?'Not passed':'Pending grading'}</div></div><div className="border rounded-xl p-4"><div className="text-xs six-muted">Attempts</div><div className="font-semibold mt-1">{detail.attempts_used}/{detail.attempts_allowed}</div></div></div></div>}
    </div>
  </div>
}
