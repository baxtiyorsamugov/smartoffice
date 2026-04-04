# Smart Office

Smart Office is a face-based attendance and reporting system for office entry monitoring.

## What It Does

- Detects and tracks faces from an RTSP camera stream
- Recognizes employees with YOLO + InsightFace
- Stores attendance logs in MySQL
- Sends weekly and monthly PDF reports to Telegram
- Provides a Streamlit dashboard for overview, registration, and manual reports
- Plays a recorded morning greeting for recognized employees

## Main Files

- `main.py`: starts the report scheduler and the live face monitor
- `ai_office_pro.py`: live recognition pipeline
- `dashboard.py`: Streamlit admin dashboard
- `run_registration.py`: batch registration from `faces/`
- `scheduler_bot.py`: report generation and Telegram sending
- `app_config.py`: environment-based configuration
- Multi-person recognition is tuned with queue and worker settings in `.env`
- `voice_greeter.py`: recorded morning greeting worker

## Run

1. Create and activate the virtual environment.
2. Install dependencies:

```powershell
venv\Scripts\python.exe -m pip install -r requirements.txt
```

3. Configure values from `.env.example`.
4. Register employee photos if needed:

```powershell
venv\Scripts\python.exe run_registration.py
```

5. Start the system:

```powershell
venv\Scripts\python.exe main.py
```

## Dashboard

```powershell
venv\Scripts\python.exe -m streamlit run dashboard.py
```

## Greeting Test

```powershell
venv\Scripts\python.exe test_greeting.py
```

## Directory Notes

- `faces/`: employee source photos
- `violations/`: saved evidence images
- `reports/`: generated attendance PDFs
- `archive/`: reserved for manual old artifact storage
- `logs/`: reserved for runtime logs
- `audio/greetings/`: recorded greeting WAV files

## Recommended Cleanup

- Old generated PDFs in the project root can be moved into `archive/`
- Old test files such as `office_test.py` and `sheriff_test.py` can be kept for experiments or removed later
