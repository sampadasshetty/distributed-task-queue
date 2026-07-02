import sys
import os
import time
import random
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from api.database import SessionLocal
from api.models import Job, JobStatus
from api.redis_client import redis_client, QUEUE_KEY, PRIORITY_SCORES

DEAD_LETTER_KEY = "dead_letter_queue"

jobs_processed_total = Counter('worker_jobs_processed_total', 'Total jobs processed', ['worker_id', 'status'])
job_duration_seconds = Histogram('worker_job_duration_seconds', 'Job execution duration in seconds', ['worker_id'])
jobs_retried_total = Counter('worker_jobs_retried_total', 'Total job retries', ['worker_id'])
jobs_dead_total = Counter('worker_jobs_dead_total', 'Total jobs moved to dead letter queue', ['worker_id'])


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-Type', CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(generate_latest())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_metrics_server(port):
    server = HTTPServer(('0.0.0.0', port), MetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[Metrics] Worker metrics server started on port {port}")


class Worker(threading.Thread):
    def __init__(self, worker_id):
        super().__init__()
        self.worker_id = worker_id
        self.daemon = True
        self.running = True

    def run(self):
        print(f"[Worker {self.worker_id}] Started.")
        while self.running:
            job_id = self.fetch_job()
            if job_id:
                self.process_job(job_id)
            else:
                time.sleep(1)

    def fetch_job(self):
        result = redis_client.zpopmin(QUEUE_KEY, 1)
        if result:
            job_id, score = result[0]
            return job_id
        return None

    def process_job(self, job_id):
        db = SessionLocal()
        start_time = time.time()
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
            duration = time.time() - start_time
            job_duration_seconds.labels(worker_id=self.worker_id).observe(duration)

            if success:
                job.status = JobStatus.SUCCESS
                job.finished_at = datetime.now(timezone.utc)
                jobs_processed_total.labels(worker_id=self.worker_id, status='success').inc()
                print(f"[Worker {self.worker_id}] Job {job.name} SUCCESS.")
            else:
                self.handle_failure(job, db)

            db.commit()

        except Exception as e:
            print(f"[Worker {self.worker_id}] Error processing job {job_id}: {e}")
        finally:
            db.close()

    def execute_task(self, job):
        time.sleep(random.uniform(1, 3))
        return random.random() > 0.2

    def handle_failure(self, job, db):
        job.retry_count += 1

        if job.retry_count <= job.max_retries:
            job.status = JobStatus.PENDING
            job.error_message = f"Attempt {job.retry_count} failed, retrying."
            jobs_retried_total.labels(worker_id=self.worker_id).inc()
            print(f"[Worker {self.worker_id}] Job {job.name} FAILED. Retry {job.retry_count}/{job.max_retries}")

            priority_score = PRIORITY_SCORES[job.priority.value]
            redis_client.zadd(QUEUE_KEY, {str(job.id): priority_score})
        else:
            job.status = JobStatus.DEAD
            job.error_message = "Max retries exceeded."
            job.finished_at = datetime.now(timezone.utc)
            jobs_processed_total.labels(worker_id=self.worker_id, status='dead').inc()
            jobs_dead_total.labels(worker_id=self.worker_id).inc()
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
    metrics_port = int(os.getenv("METRICS_PORT", 9100))
    start_metrics_server(metrics_port)

    pool = WorkerPool(num_workers=3)
    pool.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down worker pool...")
        pool.stop()