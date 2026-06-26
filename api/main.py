from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from uuid import UUID
from . import models
from .database import engine, get_db
from .schemas import JobCreate, JobResponse, JobListResponse
from .models import JobStatus, JobPriority
from .redis_client import redis_client, PRIORITY_SCORES, QUEUE_KEY   
from fastapi.middleware.cors import CORSMiddleware

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Distributed Task Queue",
    description="A distributed job scheduling system",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "task-queue-api"}


@app.post("/jobs", response_model=JobResponse, status_code=201)
def create_job(job_data: JobCreate, db: Session = Depends(get_db)):
    for dep_id in job_data.dependencies:
        dep_job = db.query(models.Job).filter(models.Job.id == dep_id).first()
        if not dep_job:
            raise HTTPException(
                status_code=404,
                detail=f"Dependency job {dep_id} does not exist"
            )

    db_job = models.Job(
        name=job_data.name,
        payload=job_data.payload,
        priority=job_data.priority,
        max_retries=job_data.max_retries,
        timeout=job_data.timeout,
        dependencies=job_data.dependencies
    )

    db.add(db_job)
    db.commit()
    db.refresh(db_job)

    if not job_data.dependencies:
        priority_score = PRIORITY_SCORES[job_data.priority.value]
        redis_client.zadd(QUEUE_KEY, {str(db_job.id): priority_score})

    return db_job

@app.get("/jobs", response_model=JobListResponse)
def list_jobs(
    status: Optional[JobStatus] = None,
    priority: Optional[JobPriority] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    query = db.query(models.Job)

    if status:
        query = query.filter(models.Job.status == status)
    if priority:
        query = query.filter(models.Job.priority == priority)

    total = query.count()

    jobs = query.order_by(desc(models.Job.created_at))\
                .offset((page - 1) * per_page)\
                .limit(per_page)\
                .all()

    return JobListResponse(jobs=jobs, total=total, page=page, per_page=per_page)


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == JobStatus.RUNNING:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a running job. Wait for it to finish."
        )

    db.delete(job)
    db.commit()
    return None


@app.post("/jobs/{job_id}/retry", response_model=JobResponse)
def retry_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in [JobStatus.FAILED, JobStatus.DEAD]:
        raise HTTPException(
            status_code=400,
            detail=f"Can only retry FAILED or DEAD jobs. Current status: {job.status}"
        )

    job.status = JobStatus.PENDING
    job.retry_count = 0
    job.error_message = None
    job.worker_id = None
    db.commit()
    db.refresh(job)
    return job

@app.get("/queue/status")
def queue_status():
    
    queue_length = redis_client.zcard(QUEUE_KEY)
    jobs_in_queue = redis_client.zrange(QUEUE_KEY, 0, -1, withscores=True)
    
    return {
        "queue_length": queue_length,
        "jobs": [
            {"job_id": job_id, "priority_score": score} 
            for job_id, score in jobs_in_queue
        ]
    }

@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total = db.query(models.Job).count()
    pending = db.query(models.Job).filter(models.Job.status == JobStatus.PENDING).count()
    running = db.query(models.Job).filter(models.Job.status == JobStatus.RUNNING).count()
    success = db.query(models.Job).filter(models.Job.status == JobStatus.SUCCESS).count()
    failed = db.query(models.Job).filter(models.Job.status == JobStatus.FAILED).count()
    dead = db.query(models.Job).filter(models.Job.status == JobStatus.DEAD).count()

    queue_length = redis_client.zcard(QUEUE_KEY)
    dead_letter_length = redis_client.llen("dead_letter_queue")

    return {
        "total_jobs": total,
        "pending": pending,
        "running": running,
        "success": success,
        "failed": failed,
        "dead": dead,
        "queue_length": queue_length,
        "dead_letter_length": dead_letter_length
    }