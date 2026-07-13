"""Download dos modelos MediaPipe Tasks (executado na primeira execução)."""

from __future__ import annotations

import urllib.request
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

MODELS = {
    "face_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
        "face_landmarker/float16/1/face_landmarker.task"
    ),
    "pose_landmarker_lite.task": (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
    ),
    "efficientdet_lite0.tflite": (
        "https://storage.googleapis.com/mediapipe-models/object_detector/"
        "efficientdet_lite0/float16/1/efficientdet_lite0.tflite"
    ),
    "hand_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
        "hand_landmarker/float16/1/hand_landmarker.task"
    ),
}


def ensure_models() -> dict[str, Path]:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for filename, url in MODELS.items():
        dest = MODELS_DIR / filename
        if not dest.is_file():
            print(f"Baixando modelo {filename}...")
            urllib.request.urlretrieve(url, dest)
        paths[filename] = dest
    return paths
