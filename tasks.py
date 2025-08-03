from celery import Celery

import os

import logging

# Celery configuration with results backend
celery = Celery("tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Set up logging for Celery
logger = logging.getLogger(__name__)



# Celery task that will be triggered by FastAPI
@celery.task
def process_tool(row_id, tool_name, date, journal_name):
    logger.info(f"Processing task for {row_id} using tool {tool_name} on {date} for journal {journal_name}")

    
    logger.info(f"Task for row_id {row_id} completed successfully.")
    return result
