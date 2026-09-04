import os

from redis import Redis
from rq import Queue

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

redis_conn = Redis.from_url(REDIS_URL)

# we name the queue rather than RQ'S unnamed default queue
letter_queue = Queue("letters", connection= redis_conn)