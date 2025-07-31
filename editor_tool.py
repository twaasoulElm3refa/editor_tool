from fastapi import FastAPI, Request
from dotenv import load_dotenv 
from openai import OpenAI
from fastapi.middleware.cors import CORSMiddleware
from tasks import process_tool
#from fastapi.responses import JSONResponse
#from database import fetch_profile_data ,insert_generated_profile
#import os
#import uvicorn 

# تحميل متغيرات البيئة
load_dotenv()
app = FastAPI()

# Allow CORS from WP domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://11ai.ellevensa.com"],  # change to your WP domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/editor_process")
async def process_request(request: Request):
    data = await request.json()
    row_id = data.get("id")
    tool_name = data.get("tool_name")
    date=data.get("date")
    journal_name=data.get("journal_name")

    if not row_id or not tool_name:
        return {"error": "Missing required fields."}

    process_tool.delay(row_id, tool_name,date,journal_name)  # send to Celery queue
    return {"status": "queued", "row_id": row_id}

