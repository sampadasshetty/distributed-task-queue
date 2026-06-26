from pydantic import BaseModel, Field, validator
from typing import Optional, List
from enum import Enum
from uuid import UUID
from datetime import datetime


class JobPriority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DEAD = "DEAD"


class JobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    payload: dict = Field(default={})
    priority: JobPriority = Field(default=JobPriority.MEDIUM)
    max_retries: int = Field(default=3, ge=0, le=10)
    timeout: int = Field(default=300, ge=10, le=3600)
    dependencies: List[UUID] = Field(default=[])

    @validator('name')
    def name_must_be_valid(cls, v):
        if ' ' in v:
            raise ValueError('Job name cannot have spaces, use underscores')
        return v.lower()

    class Config:
        json_schema_extra = {
            "example": {
                "name": "send_welcome_email",
                "payload": {"user_id": 123, "email": "user@example.com"},
                "priority": "HIGH",
                "max_retries": 3,
                "timeout": 60,
                "dependencies": []
            }
        }


class JobResponse(BaseModel):
    id: UUID
    name: str
    payload: dict
    status: JobStatus
    priority: JobPriority
    retry_count: int
    max_retries: int
    timeout: int
    dependencies: List[UUID]
    worker_id: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True


class JobListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int
    page: int
    per_page: int