import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apscheduler.schedulers.background import BackgroundScheduler
from api.database import SessionLocal
from api.models import Job, JobStatus
from api.redis_client import redis_client, QUEUE_KEY, PRIORITY_SCORES


def check_dependent_jobs():
    db = SessionLocal()
    try:
        pending_jobs = db.query(Job).filter(
            Job.status == JobStatus.PENDING,
            Job.dependencies != []
        ).all()

        for job in pending_jobs:
            if is_already_queued(job.id):
                continue

            deps_done = all(
                is_dependency_successful(db, dep_id)
                for dep_id in job.dependencies
            )

            if deps_done:
                priority_score = PRIORITY_SCORES[job.priority.value]
                redis_client.zadd(QUEUE_KEY, {str(job.id): priority_score})
                print(f"[Scheduler] Job {job.name} ({job.id}) dependencies met. Queued.")

    finally:
        db.close()


def is_dependency_successful(db, dep_id):
    dep_job = db.query(Job).filter(Job.id == dep_id).first()
    return dep_job is not None and dep_job.status == JobStatus.SUCCESS


def is_already_queued(job_id):
    score = redis_client.zscore(QUEUE_KEY, str(job_id))
    return score is not None


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_dependent_jobs, 'interval', seconds=5)
    scheduler.start()
    print("[Scheduler] Started. Checking dependencies every 5 seconds.")
    return scheduler


if __name__ == "__main__":
    scheduler = start_scheduler()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Scheduler] Shutting down.")
        scheduler.shutdown()