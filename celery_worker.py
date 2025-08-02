from celery import Celery
import os

# Initialize Celery app with Redis broker
celery = Celery("tasks", broker=os.getenv("REDIS_URL"))

# Import tasks from tasks.py (task functions)
from tasks import process_tool
