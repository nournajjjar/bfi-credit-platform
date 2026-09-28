"""Job service"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from collections import OrderedDict
from schemas.job_schema import JobStatus, JobType, JobResponse
from core.logger import setup_logger

logger = setup_logger(__name__)

class JobService:
    def __init__(self, max_jobs: int = 1000):
        self._jobs: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._max_jobs = max_jobs

    def create_job(self, job_type: JobType, title: str, params: Optional[Dict] = None) -> str:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        self._jobs[job_id] = {
            "job_id": job_id,
            "job_type": job_type,
            "status": JobStatus.PENDING,
            "title": title,
            "params": params or {},
            "progress": 0,
            "message": "Job created",
            "result": None,
            "error": None,
            "created_at": datetime.now(),
            "started_at": None,
            "completed_at": None,
        }
        logger.info(f"Created job {job_id}")
        return job_id

    def get_job(self, job_id: str) -> Optional[JobResponse]:
        job_data = self._jobs.get(job_id)
        return JobResponse(**job_data) if job_data else None

    def update_job(self, job_id: str, status: Optional[JobStatus] = None,
                   progress: Optional[int] = None, message: Optional[str] = None,
                   result: Optional[Dict] = None, error: Optional[str] = None):
        if job_id not in self._jobs:
            return None

        job = self._jobs[job_id]
        if status: job["status"] = status
        if progress is not None: job["progress"] = progress
        if message: job["message"] = message
        if result: job["result"] = result
        if error: job["error"] = error

        if status == JobStatus.RUNNING and job["started_at"] is None:
            job["started_at"] = datetime.now()
        elif status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            job["completed_at"] = datetime.now()

        return JobResponse(**job)
    def list_jobs(self):
        return [JobResponse(**j) for j in self._jobs.values()]

    def delete_job(self, job_id: str) -> bool:
        if job_id not in self._jobs:
            return False
        del self._jobs[job_id]
        return True

job_service = JobService()
