import mysql.connector
from datetime import datetime
from database import db_config # Используем твои настройки подключения

def init_violations_db():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS violations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255),
            violation_type VARCHAR(100),
            violation_date DATE,
            violation_time TIME,
            screenshot_path VARCHAR(255)
        )
    """)
    conn.commit()
    conn.close()

def log_violation(name, v_type, photo_path):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        now = datetime.now()
        query = "INSERT INTO violations (name, violation_type, violation_date, violation_time, screenshot_path) VALUES (%s, %s, %s, %s, %s)"
        cursor.execute(query, (name, v_type, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), photo_path))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Ошибка БД Штрафов: {e}")