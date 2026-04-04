from ai_office_pro import main as run_face_monitor
from database import init_db
from scheduler_bot import start_report_scheduler
from voice_greeter import VoiceGreeter


if __name__ == "__main__":
    init_db()
    start_report_scheduler()
    greeter = VoiceGreeter()
    run_face_monitor(greeter=greeter)
