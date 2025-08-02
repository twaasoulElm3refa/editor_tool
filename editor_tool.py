from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from tasks import process_tool
from celery.result import AsyncResult
import os
import asyncio

# Load environment variables
load_dotenv()
app = FastAPI()

# Allow CORS from WP domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this with your WP domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/editor_process")
async def process_request(request: Request):
    try:
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
        
        # Poll for task completion
        while not task.ready():
            await asyncio.sleep(1)  # Wait for the task to complete
        
        if task.successful():
            return {"status": "completed", "result": task.result}
        else:
            return {"status": "failed", "error": task.result}
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
