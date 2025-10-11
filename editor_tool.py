from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os, time, uuid, jwt
from typing import Optional, List
from pydantic import BaseModel, Field
from database import get_db_connection, get_data_by_request_id, update_editor_result
from openai import OpenAI

# -----------------------------------
# Setup
# -----------------------------------
load_dotenv()
app = FastAPI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_DEV_SECRET")  # set in production!

# CORS (tighten allow_origins in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # set to your WP origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------
# Task functions (existing)
# -----------------------------------
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

def re_edit_report(report):
    prompt = f'''{report}أعد تحرير هذا الخبر بصياغة افتتاحية أقوى وأسلوب صحفي واضح'''
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def summarizing_report(report):
    prompt = f'''{report} لخص هذا التقرير وعدّله ليكون مناسبًا للنشر في صحيفة سعودية'''
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# -----------------------------------
# Existing route (kept as-is)
# -----------------------------------
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
        else:
            return JSONResponse(status_code=400, content={"error": "أداة غير معروفة"})

        # Update the result in the database
        saved_result = update_editor_result(row_id, result)
        print(saved_result)
        
        # Return result in response
        return JSONResponse(status_code=200, content={"status": "completed", "result": result})
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# =================================================================
# NEW: Chat session + streaming chat — matches the WP plugin
# =================================================================

# ---- Models (aligned with your plugin JS) ----
class SessionIn(BaseModel):
    user_id: int
    wp_nonce: Optional[str] = None

class SessionOut(BaseModel):
    session_id: str
    token: str

class VisibleValue(BaseModel):
    id: Optional[int] = None
    organization_name: Optional[str] = None  # maps to journal_name (WP)
    about_press: Optional[str] = None        # maps to entered_data (WP)
    press_date: Optional[str] = None         # maps to date (WP)
    # Extras the plugin may include:
    article: Optional[str] = None            # last article from localStorage
    result: Optional[str] = None             # saved/edited result

class ChatIn(BaseModel):
    session_id: str
    user_id: int
    message: str
    visible_values: List[VisibleValue] = Field(default_factory=list)

# ---- Helpers ----
def _make_jwt(session_id: str, user_id: int) -> str:
    payload = {
        "sid": session_id,
        "uid": user_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + 60 * 60 * 2,  # 2 hours
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def _verify_jwt(bearer: Optional[str]):
    if not bearer or not bearer.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = bearer.split(" ", 1)[1]
    try:
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def _values_to_context(values: List[VisibleValue]) -> str:
    """Build Arabic context from the 1st visible record."""
    if not values:
        return "لا توجد بيانات مرئية حالياً لهذا المستخدم."
    v = values[0]
    parts = []
    if v.organization_name:
        parts.append(f"اسم الجريدة/المنظمة: {v.organization_name}")
    if v.press_date:
        parts.append(f"تاريخ البيان/التقرير: {v.press_date}")
    if v.about_press:
        snippet = (v.about_press[:600] + "…") if len(v.about_press or "") > 600 else (v.about_press or "")
        parts.append(f"ملخص المدخلات: {snippet}")
    # Prefer the freshest draft for grounding:
    draft = v.article or v.result
    if draft:
        snippet2 = (draft[:800] + "…") if len(draft) > 800 else draft
        parts.append(f"أحدث مسودة/نص محفوظ: {snippet2}")
    return " | ".join(parts) if parts else "لا توجد تفاصيل كافية."

# ---- Routes ----
@app.post("/session", response_model=SessionOut)
def create_session(body: SessionIn):
    sid = str(uuid.uuid4())
    token = _make_jwt(sid, body.user_id or 0)
    return SessionOut(session_id=sid, token=token)

@app.post("/chat")
def chat(body: ChatIn, authorization: Optional[str] = Header(None)):
    _verify_jwt(authorization)

    context = _values_to_context(body.visible_values)
    sys_prompt = (
        "أنت مساعد تحرير عربي موثوق. اعتمد على البيانات المرئية والدُروس المستفادة من النصوص السابقة. "
        "إذا كانت المعلومة غير متوفرة، صرّح بذلك واقترح ما يلزم للحصول عليها.\n\n"
        f"البيانات المرئية الحالية: {context}"
    )
    user_msg = body.message or ""

    def stream():
        try:
            # Use a small, fast model for chat streaming (adjust if you want gpt-4o)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.2,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user",   "content": user_msg}
                ],
                stream=True
            )
            for chunk in response:
                delta = None
                if chunk.choices and hasattr(chunk.choices[0], "delta"):
                    delta = getattr(chunk.choices[0].delta, "content", None)
                if delta:
                    yield delta
        except Exception as e:
            # Surface a readable error to the client without crashing the stream
            yield f"\n[خطأ]: {str(e)}"

    return StreamingResponse(stream(), media_type="text/plain"
