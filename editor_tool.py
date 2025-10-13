from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import Optional, List

import os, time, uuid, re, requests, jwt

# Optional DB helper (fallback only). Safe if you don't ship this file.
try:
    from database import get_data_by_request_id  # noqa: F401
except Exception:
    get_data_by_request_id = None  # if not available, we won't use it

from openai import OpenAI

# -----------------------------------------------------------------------------
# Environment / Setup
# -----------------------------------------------------------------------------
load_dotenv()

OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL  = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")        # used by /editor_process
OPENAI_CHAT_FAST   = os.getenv("OPENAI_CHAT_FAST",  "gpt-4o-mini")   # used by /chat (streaming)
JWT_SECRET         = os.getenv("JWT_SECRET", "CHANGE_ME_DEV_SECRET") # set a strong secret in prod
NEWS_API_KEY       = os.getenv("NEWS_API_KEY", "")                   # NewsAPI.org key (optional)
AUTO_NEWS_SEARCH   = os.getenv("AUTO_NEWS_SEARCH", "0") == "1"       # 1 => search every chat
DEFAULT_NEWS_LANG  = os.getenv("NEWS_LANG", "ar")                    # news language

app = FastAPI()
client = OpenAI(api_key=OPENAI_API_KEY)

# CORS — restrict to your WP origin in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Editor tasks
# -----------------------------------------------------------------------------
def notes_into_publishable_material(report: str, date: str, journal_name: Optional[str] = None) -> str:
    prompt = (
        f"{report}\n"
        "انت صحفي عربي محترف وموضعي تقوم بتحويل ملاحظات المراسل الميداني إلى مادة قابلة للنشر "
        "مع تكوين عنوان قوي يوضح الأحداث المتضمنة في المدخل. "
        f"اذكر {date} واسم الجريدة إن وُجد ({journal_name}) تحت العنوان مباشرة. "
        "اجعل الفقرات مرتبة وواضحة وغير مختصرة."
    )
    r = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content

def generate_report(data: str, date: str) -> str:
    prompt = (
        f"اقرأ المعلومات التالية بعناية ثم اكتب تقريرًا صحفيًا احترافيًا حول الحدث:\n{data}\n\n"
        f"ضع تاريخ اليوم {date} أسفل العنوان مباشرة. اجعل العرض دقيقًا وواضحًا."
    )
    r = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content

def re_edit_report(report: str) -> str:
    prompt = f"{report}\n\nأعد تحرير هذا الخبر بصياغة افتتاحية أقوى وأسلوب صحفي واضح."
    r = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content

def summarizing_report(report: str) -> str:
    prompt = f"{report}\n\nلخص هذا التقرير وعدّله ليكون مناسبًا للنشر في صحيفة سعودية."
    r = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.choices[0].message.content

# -----------------------------------------------------------------------------
# /editor_process — called by WP to generate the article
# -----------------------------------------------------------------------------
@app.post("/editor_process")
async def process_request(request: Request):
    """
    Body JSON:
      { id, tool_name, date, journal_name?, text? }
    Prefer 'text' sent from WordPress. If missing and a DB helper exists,
    we fallback to get_data_by_request_id(id).
    """
    try:
        data = await request.json()

        if not all([data.get("id"), data.get("tool_name"), data.get("date")]):
            return JSONResponse(status_code=400, content={"error": "Missing required fields"})

        row_id       = data.get("id")
        tool_name    = data.get("tool_name")
        date         = data.get("date")
        journal_name = data.get("journal_name")
        text         = (data.get("text") or "").strip()

        # Optional fallback via DB helper
        if not text and get_data_by_request_id:
            rec = get_data_by_request_id(row_id)
            if not rec:
                return JSONResponse(status_code=404, content={"error": "لم يتم العثور على البيانات"})
            text = (rec.get("entered_data") or "").strip()

        if not text:
            return JSONResponse(status_code=400, content={"error": "لا يوجد نص لمعالجته"})

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

        return JSONResponse(status_code=200, content={"status": "completed", "result": result})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# -----------------------------------------------------------------------------
# Chat session + streaming chat (with on-demand / automatic news search)
# -----------------------------------------------------------------------------
class SessionIn(BaseModel):
    user_id: int
    wp_nonce: Optional[str] = None

class SessionOut(BaseModel):
    session_id: str
    token: str

class VisibleValue(BaseModel):
    id: Optional[int] = None
    organization_name: Optional[str] = None  # journal_name in WP
    about_press: Optional[str] = None        # entered_data in WP
    press_date: Optional[str] = None         # date in WP
    article: Optional[str] = None            # last article (localStorage)
    result: Optional[str] = None             # saved/edited result

class ChatIn(BaseModel):
    session_id: str
    user_id: int
    message: str
    visible_values: List[VisibleValue] = Field(default_factory=list)

# --- JWT helpers ---
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

# --- Visible values → compact Arabic context ---
def _values_to_context(values: List[VisibleValue]) -> str:
    if not values:
        return "لا توجد بيانات مرئية حالياً لهذا المستخدم."
    v = values[0]
    parts = []
    if v.organization_name:
        parts.append(f"اسم الجريدة/المنظمة: {v.organization_name}")
    if v.press_date:
        parts.append(f"تاريخ البيان/التقرير: {v.press_date}")
    if v.about_press:
        snippet = (v.about_press[:600] + "…") if len(v.about_press) > 600 else v.about_press
        parts.append(f"ملخص المدخلات: {snippet}")
    draft = v.article or v.result
    if draft:
        snippet2 = (draft[:800] + "…") if len(draft) > 800 else draft
        parts.append(f"أحدث مسودة/نص محفوظ: {snippet2}")
    return " | ".join(parts) if parts else "لا توجد تفاصيل كافية."

# --- News search (NewsAPI.org adapter). Swap this if you prefer Bing/Tavily/GNews. ---
def search_news(query: str, lang: str = DEFAULT_NEWS_LANG, max_items: int = 6) -> str:
    """
    Returns a compact Arabic block of recent headlines/descriptions/URLs.
    If NEWS_API_KEY is missing, returns '' (no-op).
    """
    if not NEWS_API_KEY or not query:
        return ""

    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "language": lang,
                "sortBy": "publishedAt",
                "pageSize": max_items,
                "apiKey": NEWS_API_KEY,
            },
            timeout=15,
        )
        j = r.json()
        arts = (j.get("articles") or [])[:max_items]
        if not arts:
            return ""
        lines = []
        for a in arts:
            title = (a.get("title") or "").strip()
            src   = ((a.get("source") or {}).get("name") or "").strip()
            date  = (a.get("publishedAt") or "")[:10]
            desc  = (a.get("description") or "").strip()
            url   = (a.get("url") or "").strip()
            if title:
                lines.append(f"- {title} — {src} ({date})")
            if desc:
                lines.append(f"  {desc}")
            if url:
                lines.append(f"  {url}")
        return "\n".join(lines)
    except Exception:
        return ""

def extract_query(msg: str) -> str:
    """Arabic heuristics to derive a search query from user text."""
    if not msg:
        return ""
    s = msg.strip()

    # Commands like "/بحث غزة" or "بحث: غزة"
    m = re.match(r"^/?(?:بحث|ابحث)\s*[:\-]?\s*(.+)$", s, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # Generic “latest” requests
    if re.search(r"(آخر|أحدث|اليوم|خبر حقيقي|تحديث|مصادر حديثة)", s):
        s = re.sub(r"^(?:اكتب|أنشئ|اعمل|قدّم|لخص|حلّل|تحدّث|حدث)\s+", "", s)
        s = re.sub(r"(من فضلك|رجاءً|لو سمحت)\s*", "", s)
        return s.strip()

    return ""

# --- Routes ---
@app.post("/session", response_model=SessionOut)
def create_session(body: SessionIn):
    sid = str(uuid.uuid4())
    token = _make_jwt(sid, body.user_id or 0)
    return SessionOut(session_id=sid, token=token)

@app.post("/chat")
def chat(body: ChatIn, authorization: Optional[str] = Header(None)):
    _verify_jwt(authorization)

    context  = _values_to_context(body.visible_values)
    user_msg = (body.message or "").strip()

    # 1) Decide whether to fetch fresh news
    manual_trigger = bool(
        re.search(r"(?:^|[\s/])(بحث|ابحث)\b", user_msg) or
        re.search(r"(آخر|أحدث|اليوم|خبر حقيقي|تحديث|مصادر حديثة)", user_msg)
    )
    wants_search = AUTO_NEWS_SEARCH or manual_trigger

    news_block = ""
    if wants_search:
        q = extract_query(user_msg)

        # If auto and no explicit query, derive from visible values or user text
        if AUTO_NEWS_SEARCH and not q:
            if body.visible_values:
                v = body.visible_values[0]
                q = (v.organization_name or v.about_press or v.result or "").strip()
            if not q:
                q = user_msg
            q = (q or "").split("\n")[0][:120]

        news_block = search_news(q)

    # 2) Build system prompt
    sys_prompt = (
        "أنت مساعد تحرير عربي موثوق.\n"
        "• لا تذكر قيود التدريب أو عدم القدرة على التصفح صراحةً.\n"
        "• إن كانت الحقائق غير كافية، اطلب تفاصيل محددة أو مصادر إضافية.\n"
        "• إن تلقيت (نتائج بحث)، فاعتمد عليها كمصدر حديث للوقائع واذكر أنها مستندة إلى هذه النتائج عند اللزوم.\n\n"
        f"البيانات المرئية الحالية: {context}\n"
    )
    if news_block:
        sys_prompt += "\nنتائج بحث حديثة ذات صلة:\n" + news_block + "\n"

    # 3) Stream reply
    def stream():
        try:
            resp = client.chat.completions.create(
                model=OPENAI_CHAT_FAST,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user",   "content": user_msg},
                ],
                stream=True,
            )
            for chunk in resp:
                delta = None
                if chunk.choices and hasattr(chunk.choices[0], "delta"):
                    delta = getattr(chunk.choices[0].delta, "content", None)
                if delta:
                    yield delta
        except Exception as e:
            yield f"\n[خطأ]: {str(e)}"

    return StreamingResponse(stream(), media_type="text/plain")

# Optional manual testing endpoint
@app.get("/news_search")
def news_search(q: str):
    return {"q": q, "results": search_news(q)}
