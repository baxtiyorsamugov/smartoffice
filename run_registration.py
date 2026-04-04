import json
import os

import cv2
import mysql.connector
import numpy as np

from database import db_config
from face_runtime import build_face_app, configure_runtime


def l2_normalize(vec):
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def extract_embedding(face_app, image_path):
    image = cv2.imread(image_path)
    if image is None:
        return None

    faces = face_app.get(image)
    if not faces:
        return None

    best_face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    embedding = l2_normalize(best_face.normed_embedding.astype(np.float32))
    return embedding.tolist()


def register_smart():
    configure_runtime()
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    face_app = build_face_app(det_size=(320, 320))

    side_to_column = {
        "front": "enc_front",
        "left": "enc_left",
        "right": "enc_right",
        "up": "enc_up",
        "down": "enc_down",
    }

    print("--- Smart registration with InsightFace ---")

    for file_name in os.listdir("faces"):
        if not file_name.lower().endswith((".jpg", ".jpeg", ".png")):
            continue

        name_part = file_name.rsplit(".", 1)[0]
        parts = name_part.split("_")
        name = parts[0]
        side = parts[1].lower() if len(parts) > 1 else "front"
        column = side_to_column.get(side, "enc_front")

        image_path = os.path.join("faces", file_name)
        embedding = extract_embedding(face_app, image_path)
        if embedding is None:
            print(f"Skip: no face found in {file_name}")
            continue

        query = f"""
            INSERT INTO staff_embeddings (name, {column})
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE {column} = VALUES({column})
        """
        cursor.execute(query, (name, json.dumps(embedding)))
        print(f"Saved {name} [{side}]")

    conn.commit()
    cursor.close()
    conn.close()
    print("--- Registration finished ---")


if __name__ == "__main__":
    register_smart()
