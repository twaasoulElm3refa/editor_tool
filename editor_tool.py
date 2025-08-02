from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from celery.result import AsyncResult
from dotenv import load_dotenv
import os
import asyncio
import subprocess
import logging
from tasks import process_tool

# Load environment variables
load_dotenv()
app = FastAPI()

# Set up logging for FastAPI
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Allow CORS from WP domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this with your WP domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Check Redis connection
def check_redis():
    try:
        # Check Redis server version
        redis_version = subprocess.check_output(["redis-server", "--version"]).decode("utf-8")
        logger.info(f"Redis version: {redis_version}")

        # Ping Redis server to ensure it's running
        ping_response = subprocess.check_output(["redis-cli", "ping"]).decode("utf-8")
        if ping_response.strip() == "PONG":
            logger.info("Redis is running and responding.")
        else:
            logger.error("Redis did not respond correctly.")
            raise Exception("Redis server is not responding.")
    except Exception as e:
        logger.error(f"Error checking Redis: {str(e)}")
        raise

# FastAPI endpoint to process requests
@app.post("/editor_process")
async def process_request(request: Request):
    try:
        # Check if Redis is running
        check_redis()

        # Parse incoming JSON data
        data = await request.json()

        # Validate required fields
        if not all([data.get("id"), data.get("tool_name"), data.get("date"), data.get("journal_name")]):
            return JSONResponse(status_code=400, content={"error": "Missing required fields"})
        
        row_id = data.get("id")
        tool_name = data.get("tool_name")
        date = data.get("date")
        journal_name = data.get("journal_name")

        # Send task to Celery
        task = process_tool.delay(row_id, tool_name, date, journal_name)  # Send to Celery queue
        logger.info(f"Task {task.id} queued for processing.")
        
        # Poll for task completion
        while not task.ready():
            await asyncio.sleep(1)  # Wait for the task to complete
        
        if task.successful():
            logger.info(f"Task {task.id} completed successfully.")
            return {"status": "completed", "result": task.result}
        else:
            logger.error(f"Task {task.id} failed.")
            return {"status": "failed", "error": task.result}
    
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return JSONResponse(status_code=500, content={"error": str(e)})
