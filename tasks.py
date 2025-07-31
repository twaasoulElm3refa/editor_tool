from celery import Celery
from database import get_db_connection
from openai import OpenAI

celery = Celery("tasks", broker="redis://localhost:6379/0")


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

#1
def notes_into_publishable_material(report, date,journal_name=None ):
  
    prompt=f'''{report}انت صحفي عربي محترف وموضعي تقوم بتحويل ملاحظات المراسل الميداني إلى مادة قابلة للنشر
    مع تكوين عنون قوى بيوضح الاحداث المتضمنة فى المدخل 
    و {date} {journal_name} مع توضيح تاريخ و مكان الحدث واسم الجريدة اذا ذٌكرت فى المدخلات تحت العنوان الرئيسي مباشرة 
    مع استيفاء كل فقرة المعلومات بشكل مرتب ومحترف وغير مختصر  
    '''
   
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": prompt}
        ],
        
    )
    return response.choices[0].message.content

#2
def generate_report(data, date):
  
    prompt=f'''اقراء المعلومات والبيان جيدا {data}
     لاستخراج المعلومات لتكوين تقرير صحفي احترافي حول اهذا الحدث بدقة واتقان  :
   مع ذكر تاريخ اليوم{date} بعد العنوان الرئيسي مباشرة 
    اكتب تقريرًا صحفيًا احترافيًا حول الحدث المحلي التالي:

✅ الأسلوب: صحفي سعودي احترافي، موضوعي، يشمل فقرات متماسكة، ولا يحتوي على مبالغة أو كلمات عامية.
  '''
   
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": prompt}
        ],
        
    )
    return response.choices[0].message.content

#3
def re_edit_report(report):
  
    prompt=f'''{report}أعد تحرير هذا الخبر بصياغة افتتاحية أقوى وأسلوب صحفي واضح
 '''
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": prompt}
        ],
        
    )
    return response.choices[0].message.content

#4
def summarizing_report(report):
  
    prompt=f'''{report} لخص هذا التقرير وعدّله ليكون مناسبًا للنشر في صحيفة سعودية
    '''

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": prompt}
        ],
        
    )
    return response.choices[0].message.content


@celery.task
def process_tool(row_id, tool_name,date,journal_name):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT entered_data FROM wpl3_editor_tool WHERE id = %s", (row_id,))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        db.close()
        return

    text = row["entered_data"]

    # Simulated processing
    if tool_name == "notes_into_publishable_material":
        result = notes_into_publishable_material(text, date, journal_name)
    elif tool_name == "generate_report":
        result = generate_report(text,date)
    elif tool_name == "re_edit_report":
        result =re_edit_report(text)
    elif tool_name == "summarizing_report":
        result = summarizing_report(text)

    cursor.execute("UPDATE wpl3_editor_tool SET result = %s WHERE id = %s", (result, row_id))
    db.commit()
    cursor.close()
    db.close()
