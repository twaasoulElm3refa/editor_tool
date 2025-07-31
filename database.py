import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
import os

load_dotenv()  # يبحث عن .env في مجلد المشروع الحالي

api_key = os.getenv("OPENAI_API_KEY")
db_name = os.getenv("DB_NAME")
db_host = os.getenv("DB_HOST")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_port = os.getenv("DB_PORT")

def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password,
            port=db_port
        )
        if connection.is_connected():
            print("Connected to MySQL successfully!")
            return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

'''def get_data_by_request_id(request_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT * FROM wpl3_editor_tool
            WHERE id = %s
        """
        cursor.execute(query, (request_id,))
        result = cursor.fetchone()
        return result if result else None
        
    except Exception as e:
        print(f"❌ Error fetching data for ID {request_id}: {e}")
        return None
        
    finally:
        cursor.close()
        connection.close()

def update_editor_result(record_id, result):
    connection = get_db_connection()
    if connection is None:
        print("Failed to establish database connection")
        return False
    try:
        if not result:
            result = "لا توجد نتيجة تم إنشاؤها"
        cursor = connection.cursor()
        query = """
        "UPDATE wpl3_editor_tool SET result = %s WHERE id = %s",
        VALUES (%s, %s)
        """
        cursor.execute(query, (result, record_id))
        connection.commit()
        print("✅ Data inserted successfully into wpl3_editor_tool")
        return True
    except Error as e:
        print(f"❌ Error updating data: {e}")
        return False
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()'''

'''def insert_full_record(user_id, file_path, url, questions_number, custom_questions, faq_result):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            INSERT INTO wpl3_FAQ (user_id, file_path, url, questions_number, custom_questions, FAQ_result,updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (user_id, file_path, url, questions_number, custom_questions, faq_result))
        connection.commit()
        return True
    finally:
         if connection.is_connected():
            cursor.close()
            connection.close()'''