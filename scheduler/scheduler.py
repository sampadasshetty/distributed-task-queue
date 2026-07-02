import sys
import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apscheduler.schedulers.background import BackgroundScheduler
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

from api.database import SessionLocal
from api.models import Job, JobStatus
from api.redis_client import redis_client, QUEUE_KEY, PRIORITY_SCORES

dag_jobs_queued_total = Counter('scheduler_dag_jobs_queued_total', 'Jobs queued by scheduler after dependency resolution')


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
    print(f"[Metrics] Scheduler metrics server started on port {port}")


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
                dag_jobs_queued_total.inc()
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
    metrics_port = int(os.getenv("METRICS_PORT", 9200))
    start_metrics_server(metrics_port)

    scheduler = start_scheduler()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Scheduler] Shutting down.")
        scheduler.shutdown()