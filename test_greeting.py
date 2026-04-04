from datetime import datetime

from database import init_db
from voice_greeter import VoiceGreeter


def main():
    init_db()
    greeter = VoiceGreeter()

    employee_name = input("Employee name for greeting test: ").strip()
    if not employee_name:
        print("No employee name provided.")
        return

    sequence, audio_key = greeter._resolve_audio_sequence(employee_name)
    if not sequence:
        print(f"No greeting audio found for: {employee_name}")
        return

    print(f"Resolved audio key: {audio_key}")
    for item in sequence:
        print(f" - {item}")

    print("Playing greeting now...")
    greeter._play_sequence(sequence)
    print(f"Test greeting finished for {employee_name} at {datetime.now():%Y-%m-%d %H:%M:%S}")


if __name__ == "__main__":
    main()
