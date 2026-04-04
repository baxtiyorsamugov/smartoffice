import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from database import get_connection
from face_runtime import build_face_app, configure_runtime
from run_registration import extract_embedding
from scheduler_bot import generate_and_send_report


st.set_page_config(page_title="Smart Office Dashboard", layout="wide")
configure_runtime()

FACE_SIDES = ["front", "left", "right", "up", "down"]


@st.cache_resource
def get_face_app():
    return build_face_app(det_size=(320, 320))


def fetch_df(query, params=None):
    conn = get_connection()
    try:
        return pd.read_sql(query, conn, params=params)
    finally:
        conn.close()


def fetch_employees():
    return fetch_df(
        """
        SELECT
            name,
            CASE WHEN enc_front IS NOT NULL THEN 1 ELSE 0 END AS has_front,
            CASE WHEN enc_left IS NOT NULL THEN 1 ELSE 0 END AS has_left,
            CASE WHEN enc_right IS NOT NULL THEN 1 ELSE 0 END AS has_right,
            CASE WHEN enc_up IS NOT NULL THEN 1 ELSE 0 END AS has_up,
            CASE WHEN enc_down IS NOT NULL THEN 1 ELSE 0 END AS has_down
        FROM staff_embeddings
        ORDER BY name
        """
    )


def fetch_attendance(days=7):
    start_date = date.today() - timedelta(days=days)
    return fetch_df(
        """
        SELECT name, log_date, log_time
        FROM attendance
        WHERE log_date >= %s
        ORDER BY log_date DESC, log_time DESC
        """,
        params=(start_date,),
    )


def fetch_violations(limit=50):
    return fetch_df(
        """
        SELECT name, violation_type, violation_date, violation_time, screenshot_path
        FROM violations
        ORDER BY violation_date DESC, violation_time DESC
        LIMIT %s
        """,
        params=(limit,),
    )


def save_employee_embeddings(employee_name, embeddings):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        query = """
        INSERT INTO staff_embeddings (name, enc_front, enc_left, enc_right, enc_up, enc_down)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            enc_front = VALUES(enc_front),
            enc_left = VALUES(enc_left),
            enc_right = VALUES(enc_right),
            enc_up = VALUES(enc_up),
            enc_down = VALUES(enc_down)
        """
        payload = (
            employee_name,
            embeddings.get("front"),
            embeddings.get("left"),
            embeddings.get("right"),
            embeddings.get("up"),
            embeddings.get("down"),
        )
        cursor.execute(query, payload)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def process_uploaded_face(face_app, uploaded_file):
    temp_dir = Path("faces")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / uploaded_file.name
    temp_path.write_bytes(uploaded_file.getbuffer())
    try:
        embedding = extract_embedding(face_app, str(temp_path))
        return embedding
    finally:
        if temp_path.exists():
            temp_path.unlink()


def render_overview():
    employees = fetch_employees()
    attendance = fetch_attendance(days=7)
    violations = fetch_violations(limit=10)

    col1, col2, col3 = st.columns(3)
    col1.metric("Employees", len(employees))
    col2.metric("Attendance logs (7d)", len(attendance))
    col3.metric("Violations", len(violations))

    st.subheader("Recent Attendance")
    st.dataframe(attendance, use_container_width=True, hide_index=True)

    st.subheader("Recent Violations")
    st.dataframe(violations, use_container_width=True, hide_index=True)


def render_employees():
    employees = fetch_employees()
    if employees.empty:
        st.info("No employees registered yet.")
        return

    for side in FACE_SIDES:
        employees[side] = employees[f"has_{side}"].map({1: "Yes", 0: "No"})

    st.dataframe(
        employees[["name", "front", "left", "right", "up", "down"]],
        use_container_width=True,
        hide_index=True,
    )


def render_registration():
    st.subheader("Register or update employee faces")
    employee_name = st.text_input("Employee name")
    uploads = {
        side: st.file_uploader(f"{side.title()} photo", type=["jpg", "jpeg", "png"], key=f"upload_{side}")
        for side in FACE_SIDES
    }

    if st.button("Save employee profile", type="primary"):
        if not employee_name.strip():
            st.error("Enter employee name.")
            return

        face_app = get_face_app()
        prepared = {}
        missing = []

        for side, upload in uploads.items():
            if upload is None:
                prepared[side] = None
                continue

            embedding = process_uploaded_face(face_app, upload)
            if embedding is None:
                missing.append(side)
            else:
                prepared[side] = json.dumps(embedding)

        if missing:
            st.error(f"Face not detected in: {', '.join(missing)}")
            return

        if not any(prepared.values()):
            st.error("Upload at least one photo.")
            return

        save_employee_embeddings(employee_name.strip(), prepared)
        st.success(f"{employee_name.strip()} saved successfully.")


def render_reports():
    st.subheader("Reports")
    report_type = st.selectbox("Report type", ["Weekly", "Monthly"])

    if st.button("Generate and send report", type="primary"):
        try:
            pdf_path = generate_and_send_report(report_type)
            if pdf_path:
                st.success(f"Report sent: {Path(pdf_path).name}")
            else:
                st.warning("No data for this report period.")
        except Exception as exc:
            st.error(f"Report failed: {exc}")


def main():
    st.title("Smart Office Dashboard")
    tab_overview, tab_employees, tab_registration, tab_reports = st.tabs(
        ["Overview", "Employees", "Registration", "Reports"]
    )

    with tab_overview:
        render_overview()

    with tab_employees:
        render_employees()

    with tab_registration:
        render_registration()

    with tab_reports:
        render_reports()


if __name__ == "__main__":
    main()
