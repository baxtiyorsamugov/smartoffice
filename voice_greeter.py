import json
import queue
import re
import threading
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Optional
import winsound

from app_config import (
    GREETING_AUDIO_DIR,
    GREETING_ENABLED,
    GREETING_MORNING_END_HOUR,
    GREETING_MORNING_START_HOUR,
)
from database import get_greeted_names_for_date, record_greeting


def _slugify(value):
    value = value.strip().lower()
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[-\s]+", "_", value, flags=re.UNICODE)
    return value


class VoiceGreeter:
    def __init__(self, base_dir: Optional[Path] = None):
        self.enabled = GREETING_ENABLED
        self.base_dir = Path(base_dir or GREETING_AUDIO_DIR)
        self.queue = queue.Queue(maxsize=32)
        self.lock = threading.Lock()
        self.today = datetime.now().date()
        self.greeted_today = set()
        self.queued_today = set()
        self.missing_today = set()
        self.name_map = self._load_name_map()
        self._ensure_dirs()
        self._load_today_state()

        if self.enabled:
            threading.Thread(target=self._worker, daemon=True).start()


    def _ensure_dirs(self):
        (self.base_dir / "full").mkdir(parents=True, exist_ok=True)
        (self.base_dir / "common").mkdir(parents=True, exist_ok=True)
        (self.base_dir / "names").mkdir(parents=True, exist_ok=True)


    def _load_name_map(self):
        mapping_path = self.base_dir / "name_map.json"
        if not mapping_path.exists():
            return {}
        try:
            return json.loads(mapping_path.read_text(encoding="utf-8"))
        except Exception:
            return {}


    def _load_today_state(self):
        try:
            self.greeted_today = get_greeted_names_for_date(self.today)
        except Exception as exc:
            print(f"Greeting state load failed: {exc}")
            self.greeted_today = set()


    def _morning_window(self):
        return (
            dt_time(hour=GREETING_MORNING_START_HOUR),
            dt_time(hour=GREETING_MORNING_END_HOUR, minute=59, second=59),
        )


    def _refresh_day_if_needed(self, now):
        if now.date() != self.today:
            with self.lock:
                if now.date() != self.today:
                    self.today = now.date()
                    self.greeted_today = set()
                    self.queued_today = set()
                    self.missing_today = set()
                    self._load_today_state()


    def _resolve_stem(self, name):
        mapped = self.name_map.get(name)
        if mapped:
            return mapped
        return name


    def _resolve_audio_sequence(self, name):
        stem = self._resolve_stem(name)
        candidates = [stem, _slugify(stem)]

        for candidate in candidates:
            full_path = self.base_dir / "full" / f"{candidate}.wav"
            if full_path.exists():
                return [full_path], candidate

        common_intro = self.base_dir / "common" / "intro.wav"
        common_outro = self.base_dir / "common" / "outro.wav"
        for candidate in candidates:
            name_clip = self.base_dir / "names" / f"{candidate}.wav"
            if common_intro.exists() and common_outro.exists() and name_clip.exists():
                return [common_intro, name_clip, common_outro], candidate

        return None, None


    def _play_sequence(self, sequence):
        for audio_file in sequence:
            winsound.PlaySound(str(audio_file), winsound.SND_FILENAME)


    def on_recognized(self, name, recognized_at=None):
        if not self.enabled or not name or name == "Unknown":
            return

        recognized_at = recognized_at or datetime.now()
        self._refresh_day_if_needed(recognized_at)

        morning_start, morning_end = self._morning_window()
        now_time = recognized_at.time()
        if now_time < morning_start or now_time > morning_end:
            return

        with self.lock:
            if name in self.greeted_today or name in self.queued_today or name in self.missing_today:
                return

            sequence, audio_key = self._resolve_audio_sequence(name)
            if not sequence:
                self.missing_today.add(name)
                return

            try:
                self.queue.put_nowait((name, recognized_at, sequence, audio_key))
                self.queued_today.add(name)
            except queue.Full:
                pass


    def _worker(self):
        while True:
            name, recognized_at, sequence, audio_key = self.queue.get()
            try:
                self._play_sequence(sequence)
                record_greeting(name, when=recognized_at, audio_key=audio_key)
                with self.lock:
                    self.greeted_today.add(name)
                    self.queued_today.discard(name)
                print(f"Greeting played: {name}")
            except Exception as exc:
                with self.lock:
                    self.queued_today.discard(name)
                print(f"Greeting playback failed for {name}: {exc}")
            finally:
                self.queue.task_done()
