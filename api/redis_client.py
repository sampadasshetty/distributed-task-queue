import redis
import os
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Priority → score mapping
# Lower score = higher priority = popped first
PRIORITY_SCORES = {
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3
}

QUEUE_KEY = "task_queue"  # name of our Redis sorted set