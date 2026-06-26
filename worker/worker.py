import sys
import os
import time
import random
import threading
from datetime import datetime,timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.database import SessionLocal
from api.models import Job, JobStatus
from api.redis_client import redis_client, QUEUE_KEY, PRIORITY_SCORES

DEAD_LETTER_KEY = "dead_letter_queue"


class Worker(threading.Thread):
    def __init__(self, worker_id):
        super().__init__()
        self.worker_id = worker_id
        self.daemon = True   # thread dies when main program exits
        self.running = True

    def run(self):
        print(f"[Worker {self.worker_id}] Started.")
        while self.running:
            job_id = self.fetch_job()
            if job_id:
                self.process_job(job_id)
            else:
                time.sleep(1)  # nothing in queue, wait before checking again

    def fetch_job(self):
        
        result = redis_client.zpopmin(QUEUE_KEY, 1)
        if result:
            job_id, score = result[0]
            return job_id
        return None

    def process_job(self, job_id):
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                print(f"[Worker {self.worker_id}] Job {job_id} not found in DB.")
                return

            print(f"[Worker {self.worker_id}] Picked up job: {job.name} ({job_id})")

            
            job.status = JobStatus.RUNNING
            job.worker_id = self.worker_id
            job.started_at = datetime.now(timezone.utc)
            db.commit()

            
            success = self.execute_task(job)

            if success:
                job.status = JobStatus.SUCCESS
                job.finished_at = datetime.now(timezone.utc)
                print(f"[Worker {self.worker_id}] Job {job.name} SUCCESS.")
            else:
                self.handle_failure(job, db)

            db.commit()

        except Exception as e:
            print(f"[Worker {self.worker_id}] Error processing job {job_id}: {e}")
        finally:
            db.close()

    def execute_task(self, job):
        
        time.sleep(random.uniform(1, 3))  # simulate work taking 1-3 seconds
        
        
        return random.random() > 0.2

    def handle_failure(self, job, db):
        job.retry_count += 1
        
        if job.retry_count <= job.max_retries:
            job.status = JobStatus.PENDING
            job.error_message = f"Attempt {job.retry_count} failed, retrying."
            print(f"[Worker {self.worker_id}] Job {job.name} FAILED. "
                  f"Retry {job.retry_count}/{job.max_retries}")
            
            
            priority_score = PRIORITY_SCORES[job.priority.value]
            redis_client.zadd(QUEUE_KEY, {str(job.id): priority_score})
        else:
            job.status = JobStatus.DEAD
            job.error_message = "Max retries exceeded."
            job.finished_at = datetime.now(timezone.utc)
            print(f"[Worker {self.worker_id}] Job {job.name} DEAD. Max retries exceeded.")
            
            
            redis_client.lpush(DEAD_LETTER_KEY, str(job.id))

    def stop(self):
        self.running = False


class WorkerPool:
    def __init__(self, num_workers=3):
        self.num_workers = num_workers
        self.workers = []

    def start(self):
        print(f"Starting worker pool with {self.num_workers} workers...")
        for i in range(self.num_workers):
            worker = Worker(worker_id=f"worker-{i+1}")
            worker.start()
            self.workers.append(worker)

    def stop(self):
        for worker in self.workers:
            worker.stop()


if __name__ == "__main__":
    pool = WorkerPool(num_workers=3)
    pool.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down worker pool...")
        pool.stop()