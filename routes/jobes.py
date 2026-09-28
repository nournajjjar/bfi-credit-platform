"""Job tracking routes"""
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from services.job_service import job_service

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])

@router.get("/")
async def list_jobs():
    return {"jobs": job_service.list_jobs()}

@router.get("/{job_id}")
async def get_job(job_id: str):
    job = job_service.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job

@router.get("/{job_id}/download")
async def download_report(job_id: str):
    job = job_service.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != "completed":
        raise HTTPException(400, "Report not ready yet")
    result = job.result or {}
    path = result.get("docx_path") if isinstance(result, dict) else None
    if not path or not os.path.isfile(path):
        raise HTTPException(404, "Report file not found on server")
    filename = os.path.basename(path)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename
    )

@router.delete("/{job_id}")
async def delete_job(job_id: str):
    ok = job_service.delete_job(job_id)
    if not ok:
        raise HTTPException(404, "Job not found")
    return {"success": True}