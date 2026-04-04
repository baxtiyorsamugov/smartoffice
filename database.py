from datetime import datetime

import mysql.connector

from app_config import DB_CONFIG


db_config = DB_CONFIG


def get_connection():
    return mysql.connector.connect(**db_config)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS greeting_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                greeted_date DATE NOT NULL,
                greeted_time TIME NOT NULL,
                audio_key VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_name_date (name, greeted_date)
            )
            """
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def insert_attendance(name, when=None):
    when = when or datetime.now()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO attendance (name, log_date, log_time) VALUES (%s, %s, %s)",
            (name, when.strftime("%Y-%m-%d"), when.strftime("%H:%M:%S")),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def log_to_mysql(name):
    insert_attendance(name)


def log_violation(name, violation_type, screenshot_path, when=None):
    when = when or datetime.now()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO violations (name, violation_type, violation_date, violation_time, screenshot_path)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                name,
                violation_type,
                when.strftime("%Y-%m-%d"),
                when.strftime("%H:%M:%S"),
                screenshot_path,
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_greeted_names_for_date(target_date):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT name FROM greeting_logs WHERE greeted_date = %s",
            (target_date.strftime("%Y-%m-%d"),),
        )
        return {row[0] for row in cursor.fetchall()}
    finally:
        cursor.close()
        conn.close()


def record_greeting(name, when=None, audio_key=None):
    when = when or datetime.now()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO greeting_logs (name, greeted_date, greeted_time, audio_key)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                greeted_time = VALUES(greeted_time),
                audio_key = VALUES(audio_key)
            """,
            (
                name,
                when.strftime("%Y-%m-%d"),
                when.strftime("%H:%M:%S"),
                audio_key,
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
