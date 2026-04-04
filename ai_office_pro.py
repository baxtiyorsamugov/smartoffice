import json
import queue
import threading
import time
from datetime import datetime
from itertools import count

import cv2
import mysql.connector
import numpy as np
import torch
from ultralytics import YOLO

from app_config import (
    DETECT_CONF,
    DETECT_HEIGHT,
    DETECT_WIDTH,
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    FACE_MARGIN,
    FACE_QUEUE_SIZE,
    FRAME_QUEUE_SIZE,
    LOG_COOLDOWN_SECONDS,
    MAX_NEW_RECOGNITIONS_PER_FRAME,
    MATCH_THRESHOLD,
    MIN_FACE_SIZE,
    MODEL_PATH,
    RECOGNITION_WORKERS,
    RTSP_URL,
    TRACK_RECHECK_SECONDS,
    TRACK_TTL_SECONDS,
)
from database import db_config
from face_runtime import build_face_app, configure_runtime

DISPLAY_SIZE = (DISPLAY_WIDTH, DISPLAY_HEIGHT)

frame_queue = queue.Queue(maxsize=FRAME_QUEUE_SIZE)
face_task_queue = queue.PriorityQueue(maxsize=FACE_QUEUE_SIZE)
tracker_memory = {}
memory_lock = threading.Lock()
task_sequence = count()


def l2_normalize(vec):
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def load_known_faces():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    cursor.execute("SELECT name, enc_front, enc_left, enc_right, enc_up, enc_down FROM staff_embeddings")

    known_names = []
    known_encodings = []

    for row in cursor.fetchall():
        name = row[0]
        for raw_embedding in row[1:]:
            if raw_embedding:
                embedding = np.array(json.loads(raw_embedding), dtype=np.float32)
                if embedding.ndim != 1 or embedding.shape[0] != 512:
                    continue
                known_names.append(name)
                known_encodings.append(l2_normalize(embedding))

    cursor.close()
    conn.close()

    if known_encodings:
        known_encodings = np.vstack(known_encodings).astype(np.float32)
    else:
        known_encodings = np.empty((0, 512), dtype=np.float32)

    print(f"Loaded {len(known_names)} InsightFace embeddings for {len(set(known_names))} employees.")
    return known_names, known_encodings


def make_detector():
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    model = YOLO(MODEL_PATH)
    model.to(device)
    try:
        model.fuse()
    except Exception:
        pass
    if device.startswith("cuda"):
        try:
            model.model.half()
        except Exception:
            pass
        print(f"YOLO detector ready on GPU: {torch.cuda.get_device_name(0)}")
    else:
        print("YOLO detector ready on CPU.")
    return model, device


def connect_db():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    return conn, cursor


def log_attendance(cursor, conn, name):
    now = time.localtime()
    cursor.execute(
        "INSERT INTO attendance (name, log_date, log_time) VALUES (%s, %s, %s)",
        (name, time.strftime("%Y-%m-%d", now), time.strftime("%H:%M:%S", now)),
    )
    conn.commit()


def ensure_track(track_id):
    with memory_lock:
        state = tracker_memory.get(track_id)
        if state is None:
            state = {
                "name": "Searching...",
                "last_seen": 0.0,
                "last_attempt": 0.0,
                "last_logged": 0.0,
                "score": 0.0,
                "pending": False,
                "attempts": 0,
            }
            tracker_memory[track_id] = state
        return dict(state)


def update_track(track_id, **updates):
    with memory_lock:
        state = tracker_memory.setdefault(
            track_id,
            {
                "name": "Searching...",
                "last_seen": 0.0,
                "last_attempt": 0.0,
                "last_logged": 0.0,
                "score": 0.0,
                "pending": False,
                "attempts": 0,
            },
        )
        state.update(updates)
        return dict(state)


def cleanup_tracks():
    now = time.time()
    with memory_lock:
        stale = [track_id for track_id, state in tracker_memory.items() if now - state["last_seen"] > TRACK_TTL_SECONDS]
        for track_id in stale:
            tracker_memory.pop(track_id, None)


def crop_with_margin(frame, x1, y1, x2, y2, margin):
    h, w = frame.shape[:2]
    x1 = max(0, x1 - margin)
    y1 = max(0, y1 - margin)
    x2 = min(w, x2 + margin)
    y2 = min(h, y2 + margin)
    return frame[y1:y2, x1:x2], x1, y1, x2, y2


def video_capture_worker():
    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        print("Camera connection failed.")
        return

    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05)
            continue

        if frame_queue.full():
            try:
                frame_queue.get_nowait()
            except queue.Empty:
                pass
        frame_queue.put(frame)


def recognize_face(face_app, face_img, known_names, known_encodings):
    if known_encodings.size == 0:
        return "Unknown", 0.0

    candidates = [face_img]
    h, w = face_img.shape[:2]
    if max(h, w) < 220:
        scale = 220 / max(h, w)
        upscaled = cv2.resize(
            face_img,
            (max(1, int(w * scale)), max(1, int(h * scale))),
            interpolation=cv2.INTER_CUBIC,
        )
        candidates.append(upscaled)

    best_name = "Unknown"
    best_score = 0.0

    for candidate in candidates:
        faces = face_app.get(candidate)
        if not faces:
            continue

        best_face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        embedding = l2_normalize(best_face.normed_embedding.astype(np.float32))
        similarities = known_encodings @ embedding
        best_idx = int(np.argmax(similarities))
        score = float(similarities[best_idx])

        if score > best_score:
            best_score = score
            best_name = known_names[best_idx]

    if best_score >= MATCH_THRESHOLD:
        return best_name, best_score
    return "Unknown", best_score


def face_recognition_worker(known_names, known_encodings, greeter=None):
    face_app = build_face_app()
    db_conn, db_cursor = connect_db()

    while True:
        task = face_task_queue.get()
        if task is None:
            break

        _, _, track_id, face_img = task
        try:
            name, score = recognize_face(face_app, face_img, known_names, known_encodings)
            current_state = ensure_track(track_id)
            attempts = current_state.get("attempts", 0) + 1
            next_name = name
            if name == "Unknown" and current_state.get("name") not in {"Searching...", "Analyzing...", "Unknown"}:
                next_name = current_state["name"]
            track_state = update_track(track_id, name=next_name, score=score, pending=False, attempts=attempts)

            if name != "Unknown":
                now = time.time()
                if now - track_state["last_logged"] >= LOG_COOLDOWN_SECONDS:
                    try:
                        log_attendance(db_cursor, db_conn, name)
                    except mysql.connector.Error:
                        try:
                            db_cursor.close()
                            db_conn.close()
                        except Exception:
                            pass
                        db_conn, db_cursor = connect_db()
                        log_attendance(db_cursor, db_conn, name)
                    update_track(track_id, last_logged=now, attempts=0)
                    if greeter is not None:
                        greeter.on_recognized(name, recognized_at=datetime.fromtimestamp(now))
                    print(f"Recognized: {name} ({score:.3f})")
                elif greeter is not None:
                    greeter.on_recognized(name, recognized_at=datetime.now())
        except Exception as exc:
            print(f"Recognition error: {exc}")
            update_track(track_id, name="Unknown", score=0.0, pending=False)
        finally:
            face_task_queue.task_done()


def main(greeter=None):
    configure_runtime()
    known_names, known_encodings = load_known_faces()
    detector, device = make_detector()

    threading.Thread(target=video_capture_worker, daemon=True).start()
    for _ in range(max(1, RECOGNITION_WORKERS)):
        threading.Thread(
            target=face_recognition_worker,
            args=(known_names, known_encodings, greeter),
            daemon=True,
        ).start()

    scale_x = None
    scale_y = None

    while True:
        try:
            frame = frame_queue.get(timeout=1.0)
        except queue.Empty:
            cleanup_tracks()
            continue

        if scale_x is None:
            scale_x = frame.shape[1] / DETECT_WIDTH
            scale_y = frame.shape[0] / DETECT_HEIGHT

        cleanup_tracks()
        small_frame = cv2.resize(frame, (DETECT_WIDTH, DETECT_HEIGHT), interpolation=cv2.INTER_LINEAR)
        results = detector.track(
            small_frame,
            persist=True,
            verbose=False,
            conf=DETECT_CONF,
            iou=0.5,
            imgsz=max(DETECT_WIDTH, DETECT_HEIGHT),
            device=device,
            tracker="bytetrack.yaml",
        )

        if results:
            result = results[0]
            if result.boxes is not None and result.boxes.id is not None:
                boxes = result.boxes.xyxy.detach().cpu().numpy()
                track_ids = result.boxes.id.int().detach().cpu().numpy()

                candidates = []
                for box, track_id in zip(boxes, track_ids):
                    track_id = int(track_id)
                    x1, y1, x2, y2 = map(int, box)

                    orig_x1 = max(0, int(x1 * scale_x))
                    orig_y1 = max(0, int(y1 * scale_y))
                    orig_x2 = min(frame.shape[1], int(x2 * scale_x))
                    orig_y2 = min(frame.shape[0], int(y2 * scale_y))

                    state = ensure_track(track_id)
                    update_track(track_id, last_seen=time.time())

                    face_w = orig_x2 - orig_x1
                    face_h = orig_y2 - orig_y1
                    draw_x1, draw_y1, draw_x2, draw_y2 = orig_x1, orig_y1, orig_x2, orig_y2
                    needs_check = (
                        state["name"] in {"Searching...", "Unknown"}
                        and not state.get("pending", False)
                        and time.time() - state["last_attempt"] >= max(0.35, TRACK_RECHECK_SECONDS / (1 + min(state.get("attempts", 0), 3)))
                        and face_w >= MIN_FACE_SIZE
                        and face_h >= MIN_FACE_SIZE
                    )

                    if needs_check:
                        candidates.append(
                            {
                                "track_id": track_id,
                                "area": face_w * face_h,
                                "coords": (orig_x1, orig_y1, orig_x2, orig_y2),
                            }
                        )
                    else:
                        state = ensure_track(track_id)

                    label = state["name"]
                    score = state.get("score", 0.0)
                    color = (0, 200, 0) if label not in {"Searching...", "Analyzing...", "Unknown"} else (0, 165, 255)
                    if label == "Unknown":
                        color = (0, 0, 255)

                    text = f"ID:{track_id} {label}"
                    if label not in {"Searching...", "Analyzing...", "Unknown"}:
                        text += f" {score:.2f}"

                    cv2.rectangle(frame, (draw_x1, draw_y1), (draw_x2, draw_y2), color, 2)
                    cv2.putText(
                        frame,
                        text,
                        (draw_x1, max(30, draw_y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.75,
                        color,
                        2,
                    )

                if candidates and not face_task_queue.full():
                    candidates.sort(key=lambda item: item["area"], reverse=True)
                    queued_now = 0
                    for candidate in candidates:
                        if queued_now >= MAX_NEW_RECOGNITIONS_PER_FRAME or face_task_queue.full():
                            break
                        track_id = candidate["track_id"]
                        x1, y1, x2, y2 = candidate["coords"]
                        face_crop, _, _, _, _ = crop_with_margin(frame, x1, y1, x2, y2, FACE_MARGIN)
                        if face_crop.size == 0:
                            continue
                        try:
                            priority = -candidate["area"]
                            task_id = next(task_sequence)
                            face_task_queue.put_nowait((priority, task_id, track_id, face_crop.copy()))
                            update_track(
                                track_id,
                                name="Analyzing...",
                                last_attempt=time.time(),
                                pending=True,
                            )
                            queued_now += 1
                        except queue.Full:
                            break

        cv2.imshow("Smart Office AI", cv2.resize(frame, DISPLAY_SIZE))
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
