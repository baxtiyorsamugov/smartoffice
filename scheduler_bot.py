from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from fpdf import FPDF

from app_config import (
    MONTHLY_REPORT_DAY,
    MONTHLY_REPORT_HOUR,
    MONTHLY_REPORT_MINUTE,
    TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN,
    WEEKLY_REPORT_DAY,
    WEEKLY_REPORT_HOUR,
    WEEKLY_REPORT_MINUTE,
)
from database import get_connection


REPORTS_DIR = Path(__file__).resolve().parent / "reports"


def send_pdf_to_telegram(file_path, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    with open(file_path, "rb") as file_handle:
        response = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
            files={"document": file_handle},
            timeout=60,
        )
    response.raise_for_status()
    print(f"Report sent to Telegram: {Path(file_path).name}")


def _period_bounds(report_type, now=None):
    now = now or datetime.now()
    today = now.date()

    if report_type.lower() == "weekly":
        start = today - timedelta(days=7)
        return start, today

    if report_type.lower() == "monthly":
        first_day_this_month = today.replace(day=1)
        last_day_prev_month = first_day_this_month - timedelta(days=1)
        start = last_day_prev_month.replace(day=1)
        end = first_day_this_month
        return start, end

    start = today - timedelta(days=1)
    return start, today


def _load_attendance_df(start_date, end_date):
    conn = get_connection()
    try:
        query = """
        SELECT name, log_date, log_time
        FROM attendance
        WHERE log_date >= %s AND log_date < %s
        ORDER BY log_date, name, log_time
        """
        return pd.read_sql(query, conn, params=(start_date, end_date))
    finally:
        conn.close()


def _format_timedelta(td):
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _build_report_df(df):
    if df.empty:
        return df

    df = df.copy()
    df["log_time"] = pd.to_timedelta(df["log_time"].astype(str))
    report_df = df.groupby(["log_date", "name"]).agg(
        Arrival=("log_time", "min"),
        Departure=("log_time", "max"),
    ).reset_index()
    report_df["Work_Duration"] = report_df["Departure"] - report_df["Arrival"]
    return report_df


def _render_report_pdf(report_df, report_type, start_date, end_date):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    file_path = REPORTS_DIR / f"{report_type.lower()}_report_{timestamp}.pdf"

    pdf = FPDF()
    pdf.add_page()
    font_path = "C:/Windows/Fonts/arial.ttf"
    pdf.add_font("ArialCustom", "", font_path, uni=True)
    pdf.set_font("ArialCustom", "", 14)
    pdf.cell(190, 10, f"{report_type} attendance report", ln=True, align="C")
    pdf.ln(2)
    pdf.set_font("ArialCustom", "", 10)
    pdf.cell(190, 8, f"Period: {start_date} to {end_date - timedelta(days=1)}", ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("ArialCustom", "", 9)
    pdf.set_fill_color(200, 220, 255)
    headers = [
        (25, "Date"),
        (55, "Employee"),
        (30, "Arrival"),
        (30, "Departure"),
        (50, "Worked"),
    ]
    for width, text in headers[:-1]:
        pdf.cell(width, 10, text, 1, 0, "C", True)
    pdf.cell(headers[-1][0], 10, headers[-1][1], 1, 1, "C", True)

    for _, row in report_df.iterrows():
        pdf.cell(25, 10, str(row["log_date"]), 1)
        pdf.cell(55, 10, str(row["name"]), 1)
        pdf.cell(30, 10, _format_timedelta(row["Arrival"]), 1)
        pdf.cell(30, 10, _format_timedelta(row["Departure"]), 1)
        pdf.cell(50, 10, _format_timedelta(row["Work_Duration"]), 1, 1)

    pdf.output(str(file_path))
    return file_path


def generate_and_send_report(report_type="Weekly"):
    start_date, end_date = _period_bounds(report_type)
    df = _load_attendance_df(start_date, end_date)

    if df.empty:
        print(f"No attendance data for {report_type.lower()} report.")
        return None

    report_df = _build_report_df(df)
    if report_df.empty:
        print(f"No grouped attendance rows for {report_type.lower()} report.")
        return None

    pdf_path = _render_report_pdf(report_df, report_type, start_date, end_date)
    send_pdf_to_telegram(pdf_path, f"{report_type} report is ready.")
    return pdf_path


def job_weekly():
    print("Starting weekly report job...")
    generate_and_send_report("Weekly")


def job_monthly():
    print("Starting monthly report job...")
    generate_and_send_report("Monthly")


def start_report_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        job_weekly,
        "cron",
        day_of_week=WEEKLY_REPORT_DAY,
        hour=WEEKLY_REPORT_HOUR,
        minute=WEEKLY_REPORT_MINUTE,
    )
    scheduler.add_job(
        job_monthly,
        "cron",
        day=MONTHLY_REPORT_DAY,
        hour=MONTHLY_REPORT_HOUR,
        minute=MONTHLY_REPORT_MINUTE,
    )
    scheduler.start()
    print("Report scheduler started.")
    return scheduler
