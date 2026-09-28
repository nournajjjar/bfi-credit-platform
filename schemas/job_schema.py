"""Job tracking schemas"""
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class JobType(str, Enum):
    COMPANY_SEARCH = "company_search"
    REPORT_GENERATION = "report_generation"

class JobResponse(BaseModel):
    job_id: str
    job_type: JobType
    status: JobStatus
    title: str
    progress: int = 0
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
