from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user
from app.schemas.jobs import JobRunResponse, JobStatusResponse
from app.services.authorization import require_permission
from app.services.jobs import JOB_DEFINITIONS, list_job_statuses, run_job

router = APIRouter(prefix="/jobs", tags=["Background Jobs"])


@router.get("", response_model=list[JobStatusResponse])
async def job_status(user=Depends(get_current_user)):
    await require_permission(user, "jobs.view")
    return await list_job_statuses()


@router.post("/{job_name}/run", response_model=JobRunResponse)
async def run_job_now(job_name: str, user=Depends(get_current_user)):
    await require_permission(user, "jobs.manage")
    if job_name not in JOB_DEFINITIONS:
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    try:
        return await run_job(job_name, force=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Job failed: {str(exc)[:500]}")
