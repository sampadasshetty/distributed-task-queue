from sqlalchemy import Column, String, Integer, JSON, DateTime, Enum, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from .database import Base
import enum
import uuid


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DEAD = "DEAD"


class JobPriority(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    payload = Column(JSON, nullable=False, default={})
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.PENDING)
    priority = Column(Enum(JobPriority), nullable=False, default=JobPriority.MEDIUM)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    timeout = Column(Integer, default=300)
    dependencies = Column(ARRAY(UUID(as_uuid=True)), default=[])
    worker_id = Column(String(100), nullable=True)
    error_message = Column(String(1000), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)