from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
from database import get_db_connection , get_data_by_request_id , update_editor_result 
from openai import OpenAI

# Load environment variables
load_dotenv()
app = FastAPI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Allow CORS from WP domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this with your WP domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Task functions
#1
def notes_into_publishable_material(report, date, journal_name=None):
    prompt = f'''{report}انت صحفي عربي محترف وموضعي تقوم بتحويل ملاحظات المراسل الميداني إلى مادة قابلة للنشر
        مع تكوين عنون قوى بيوضح الاحداث المتضمنة فى المدخل 
        و {date} {journal_name} مع توضيح تاريخ و مكان الحدث واسم الجريدة اذا ذٌكرت فى المدخلات تحت العنوان الرئيسي مباشرة 
        مع استيفاء كل فقرة المعلومات بشكل مرتب ومحترف وغير مختصر'''

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content
#2
def generate_report(data, date):
    prompt = f'''اقراء المعلومات والبيان جيدا {data}
        لاستخراج المعلومات لتكوين تقرير صحفي احترافي حول هذا الحدث بدقة واتقان:
        مع ذكر تاريخ اليوم{date} بعد العنوان الرئيسي مباشرة
        اكتب تقريرًا صحفيًا احترافيًا حول الحدث المحلي التالي:'''
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content
#3
def re_edit_report(report):
    prompt = f'''{report}أعد تحرير هذا الخبر بصياغة افتتاحية أقوى وأسلوب صحفي واضح'''

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content
#4
def summarizing_report(report):
    prompt = f'''{report} لخص هذا التقرير وعدّله ليكون مناسبًا للنشر في صحيفة سعودية'''

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content


@app.post("/editor_process")
async def process_request(request: Request):
    try:
        data = await request.json()

        # Validate required fields
        if not all([data.get("id"), data.get("tool_name"), data.get("date"), data.get("journal_name")]):
            return JSONResponse(status_code=400, content={"error": "Missing required fields"})
        
        row_id = data.get("id")
        tool_name = data.get("tool_name")
        date = data.get("date")
        journal_name = data.get("journal_name")
        
        # Fetch data from the database
        input_data = get_data_by_request_id(row_id)
        if not input_data:
            return JSONResponse(status_code=404, content={"error": "لم يتم العثور على البيانات"})

        text = input_data["entered_data"]

        # Process based on the tool name
        if tool_name == "notes_into_publishable_material":
            result = notes_into_publishable_material(text, date, journal_name)
        elif tool_name == "generate_report":
            result = generate_report(text, date)
        elif tool_name == "re_edit_report":
            result = re_edit_report(text)
        elif tool_name == "summarizing_report":
            result = summarizing_report(text)

        # Update the result in the database
        saved_result = update_editor_result(row_id, result)
        
        return {"status": "completed", "result": result}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
