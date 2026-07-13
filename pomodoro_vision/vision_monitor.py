"""Monitor de visao computacional: olhos, postura, presenca, celular e olhar."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Iterable

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.vision import drawing_utils, drawing_styles
from PIL import Image, ImageDraw, ImageFont

from pomodoro_vision.models import ensure_models

LEFT_EYE = (33, 160, 158, 133, 153, 144)
RIGHT_EYE = (362, 385, 387, 263, 373, 380)
PHONE_LABELS = {"cell phone", "mobile phone", "phone"}


class ViolationType(Enum):
    EYES_CLOSED = auto()
    LOOKING_AWAY = auto()
    BAD_POSTURE = auto()
    LEFT_FRAME = auto()
    PHONE_DETECTED = auto()


@dataclass
class VisionStatus:
    face_detected: bool = False
    pose_detected: bool = False
    phone_detected: bool = False
    eyes_open: bool = True
    looking_forward: bool = True
    good_posture: bool = True
    in_frame: bool = True
    ear_avg: float = 0.0
    head_yaw: float = 0.0
    active_violations: list[ViolationType] = field(default_factory=list)
    violation_message: str = "Tudo certo por aqui"
    focus_score: int = 100


class VisionMonitor:
    EYE_CLOSED_THRESHOLD = 0.185
    FOCUS_LOST_DURATION_SEC = 10.0
    LOOK_AWAY_YAW_THRESHOLD = 0.25
    ALARM_COOLDOWN_SEC = 6.0

    def __init__(self) -> None:
        model_paths = ensure_models()

        face_options = vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(model_paths["face_landmarker.task"])
            ),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        pose_options = vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(model_paths["pose_landmarker_lite.task"])
            ),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        hand_options = vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(model_paths["hand_landmarker.task"])
            ),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.45,
            min_hand_presence_confidence=0.45,
            min_tracking_confidence=0.45,
        )
        object_options = vision.ObjectDetectorOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(model_paths["efficientdet_lite0.tflite"])
            ),
            running_mode=vision.RunningMode.VIDEO,
            max_results=5,
            score_threshold=0.35,
        )

        self._face_landmarker = vision.FaceLandmarker.create_from_options(face_options)
        self._pose_landmarker = vision.PoseLandmarker.create_from_options(pose_options)
        self._hand_landmarker = vision.HandLandmarker.create_from_options(hand_options)
        self._object_detector = vision.ObjectDetector.create_from_options(object_options)
        self._frame_timestamp_ms = 0

        self._eyes_closed_since: float | None = None
        self._absent_since: float | None = None
        self._look_away_since: float | None = None
        self._bad_posture_since: float | None = None
        self._phone_since: float | None = None
        self._last_alarm_at = 0.0
        self._last_posture_warning_at = 0.0

        self._ear_history: list[float] = []
        self._yaw_history: list[float] = []

        self._font = self._load_font(18)
        self._font_sm = self._load_font(14)

    @staticmethod
    def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    def close(self) -> None:
        self._face_landmarker.close()
        self._pose_landmarker.close()
        self._hand_landmarker.close()
        self._object_detector.close()

    def reset_violation_timers(self) -> None:
        self._eyes_closed_since = None
        self._absent_since = None
        self._look_away_since = None
        self._bad_posture_since = None
        self._phone_since = None

    @staticmethod
    def _landmark_xy(landmark, width: int, height: int) -> tuple[float, float]:
        return landmark.x * width, landmark.y * height

    @staticmethod
    def _eye_aspect_ratio(landmarks, eye_indices: Iterable[int], w: int, h: int) -> float:
        pts = [VisionMonitor._landmark_xy(landmarks[i], w, h) for i in eye_indices]
        p1, p2, p3, p4, p5, p6 = pts
        vertical = np.linalg.norm(np.array(p2) - np.array(p6)) + np.linalg.norm(
            np.array(p3) - np.array(p5)
        )
        horizontal = np.linalg.norm(np.array(p1) - np.array(p4))
        if horizontal < 1e-6:
            return 0.0
        return float(vertical / (2.0 * horizontal))

    @staticmethod
    def _estimate_head_yaw(landmarks) -> float:
        # Landmarks 33 (canto externo esquerdo do olho) e 263 (canto externo direito)
        left_eye = landmarks[33]
        right_eye = landmarks[263]
        dx = right_eye.x - left_eye.x
        dz = right_eye.z - left_eye.z
        return float(np.arctan2(dz, dx))

    @staticmethod
    def _check_posture(pose_landmarks) -> tuple[bool, str]:
        lm = pose_landmarks
        needed = (
            vision.PoseLandmark.NOSE,
            vision.PoseLandmark.LEFT_SHOULDER,
            vision.PoseLandmark.RIGHT_SHOULDER,
        )
        for idx in needed:
            if lm[idx].visibility < 0.5:
                return True, ""

        nose_y = lm[vision.PoseLandmark.NOSE].y
        l_sh_y = lm[vision.PoseLandmark.LEFT_SHOULDER].y
        r_sh_y = lm[vision.PoseLandmark.RIGHT_SHOULDER].y
        
        l_sh_x = lm[vision.PoseLandmark.LEFT_SHOULDER].x
        r_sh_x = lm[vision.PoseLandmark.RIGHT_SHOULDER].x

        shoulder_y = (l_sh_y + r_sh_y) / 2.0
        shoulder_width = float(np.hypot(l_sh_x - r_sh_x, l_sh_y - r_sh_y))
        
        if shoulder_width < 1e-5:
            return True, ""
            
        head_height = shoulder_y - nose_y
        ratio = head_height / shoulder_width
        
        # Se ratio < 0.45, a cabeça está muito afundada em relação aos ombros (curvado)
        if ratio < 0.45:
            return False, "Postura curvada. Endireite as costas"

        # Inclinação lateral dos ombros normalizada
        shoulder_tilt_ratio = abs(l_sh_y - r_sh_y) / shoulder_width
        if shoulder_tilt_ratio > 0.15:
            return False, "Ombros desalinhados. Ajuste a postura"

        return True, ""

    @staticmethod
    def _detect_phone_object(object_result) -> bool:
        if not object_result.detections:
            return False
        for detection in object_result.detections:
            for category in detection.categories:
                name = category.category_name.lower()
                if name in PHONE_LABELS and category.score >= 0.35:
                    return True
        return False

    @staticmethod
    def _is_finger_extended(hand_landmarks, tip_idx: int, mcp_idx: int) -> bool:
        wrist = hand_landmarks[0]
        mcp = hand_landmarks[mcp_idx]
        tip = hand_landmarks[tip_idx]
        
        dist_wrist_tip = float(np.hypot(tip.x - wrist.x, tip.y - wrist.y))
        dist_wrist_mcp = float(np.hypot(mcp.x - wrist.x, mcp.y - wrist.y))
        return dist_wrist_tip > dist_wrist_mcp

    @staticmethod
    def _detect_phone_hands(
        hand_result,
        face_landmarks,
        w: int,
        h: int,
    ) -> bool:
        if not hand_result.hand_landmarks or face_landmarks is None:
            return False

        nose_x, nose_y = VisionMonitor._landmark_xy(face_landmarks[1], w, h)
        chin_x, chin_y = VisionMonitor._landmark_xy(face_landmarks[152], w, h)
        ref_x = (nose_x + chin_x) / 2.0
        ref_y = (nose_y + chin_y) / 2.0

        for hand in hand_result.hand_landmarks:
            wrist_x, wrist_y = VisionMonitor._landmark_xy(hand[0], w, h)
            dist = float(np.hypot(wrist_x - ref_x, wrist_y - ref_y))
            if dist < w * 0.35:
                # Conta dedos estendidos (Index, Middle, Ring, Pinky)
                extended_count = 0
                for tip, mcp in [(8, 5), (12, 9), (16, 13), (20, 17)]:
                    if VisionMonitor._is_finger_extended(hand, tip, mcp):
                        extended_count += 1
                
                # Se <= 2 dedos estendidos, a mão está fechada/segurando (grip)
                if extended_count <= 2:
                    return True
        return False

    def process(
        self,
        frame_bgr: np.ndarray,
        monitoring: bool,
    ) -> tuple[np.ndarray, VisionStatus, bool, bool]:
        frame_bgr = cv2.flip(frame_bgr, 1)

        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        self._frame_timestamp_ms += 33
        ts = self._frame_timestamp_ms
        face_result = self._face_landmarker.detect_for_video(mp_image, ts)
        pose_result = self._pose_landmarker.detect_for_video(mp_image, ts)
        hand_result = self._hand_landmarker.detect_for_video(mp_image, ts)
        object_result = self._object_detector.detect_for_video(mp_image, ts)

        now = time.monotonic()
        status = VisionStatus()
        trigger_alarm = False
        trigger_posture_warning = False

        face_landmarks = (
            face_result.face_landmarks[0] if face_result.face_landmarks else None
        )
        pose_landmarks = (
            pose_result.pose_landmarks[0] if pose_result.pose_landmarks else None
        )

        face_detected = face_landmarks is not None
        status.face_detected = face_detected
        status.pose_detected = pose_landmarks is not None

        phone_object = self._detect_phone_object(object_result)
        phone_hands = self._detect_phone_hands(hand_result, face_landmarks, w, h)
        status.phone_detected = phone_object or phone_hands

        if face_detected:
            left_ear = self._eye_aspect_ratio(face_landmarks, LEFT_EYE, w, h)
            right_ear = self._eye_aspect_ratio(face_landmarks, RIGHT_EYE, w, h)
            ear_val = (left_ear + right_ear) / 2.0
            
            # Suavização temporal do EAR
            self._ear_history.append(ear_val)
            if len(self._ear_history) > 5:
                self._ear_history.pop(0)
            status.ear_avg = sum(self._ear_history) / len(self._ear_history)
            status.eyes_open = status.ear_avg >= self.EYE_CLOSED_THRESHOLD

            # Suavização temporal do Yaw
            raw_yaw = self._estimate_head_yaw(face_landmarks)
            self._yaw_history.append(raw_yaw)
            if len(self._yaw_history) > 5:
                self._yaw_history.pop(0)
            status.head_yaw = sum(self._yaw_history) / len(self._yaw_history)
            status.looking_forward = abs(status.head_yaw) < self.LOOK_AWAY_YAW_THRESHOLD
            
            self._absent_since = None
            status.in_frame = True
        else:
            status.eyes_open = False
            status.looking_forward = False
            status.in_frame = False
            self._ear_history.clear()
            self._yaw_history.clear()

        if pose_landmarks is not None:
            good, posture_msg = self._check_posture(pose_landmarks)
            status.good_posture = good
            if not good and posture_msg:
                status.violation_message = posture_msg
        elif face_detected:
            status.good_posture = True
        else:
            status.good_posture = False

        if monitoring:
            trigger_alarm, trigger_posture_warning = self._evaluate_violations(status, now)
        else:
            self.reset_violation_timers()

        status.focus_score = self._compute_focus_score(status)

        annotated = self._draw_overlay(
            frame_bgr,
            face_landmarks,
            pose_landmarks,
            hand_result,
            object_result,
            status,
            monitoring,
        )
        return annotated, status, trigger_alarm, trigger_posture_warning

    def _compute_focus_score(self, status: VisionStatus) -> int:
        score = 100
        if not status.face_detected:
            score -= 35
        if not status.eyes_open:
            score -= 25
        if not status.looking_forward:
            score -= 15
        if not status.good_posture:
            score -= 15
        if status.phone_detected:
            score -= 30
        return max(0, score)

    def _evaluate_violations(self, status: VisionStatus, now: float) -> tuple[bool, bool]:
        violations: list[ViolationType] = []

        if not status.face_detected:
            if self._absent_since is None:
                self._absent_since = now
            elif now - self._absent_since >= self.FOCUS_LOST_DURATION_SEC:
                violations.append(ViolationType.LEFT_FRAME)
                status.in_frame = False
        else:
            self._absent_since = None

        if status.face_detected and not status.eyes_open:
            if self._eyes_closed_since is None:
                self._eyes_closed_since = now
            elif now - self._eyes_closed_since >= self.FOCUS_LOST_DURATION_SEC:
                violations.append(ViolationType.EYES_CLOSED)
        else:
            self._eyes_closed_since = None

        if status.face_detected and not status.looking_forward:
            if self._look_away_since is None:
                self._look_away_since = now
            elif now - self._look_away_since >= self.FOCUS_LOST_DURATION_SEC:
                violations.append(ViolationType.LOOKING_AWAY)
        else:
            self._look_away_since = None

        if status.pose_detected and not status.good_posture:
            if self._bad_posture_since is None:
                self._bad_posture_since = now
            elif now - self._bad_posture_since >= self.FOCUS_LOST_DURATION_SEC:
                violations.append(ViolationType.BAD_POSTURE)
        else:
            self._bad_posture_since = None

        if status.phone_detected:
            if self._phone_since is None:
                self._phone_since = now
            elif now - self._phone_since >= self.FOCUS_LOST_DURATION_SEC:
                violations.append(ViolationType.PHONE_DETECTED)
        else:
            self._phone_since = None

        status.active_violations = violations

        trigger_alarm = False
        trigger_posture_warning = False

        # Filtra infrações do alarme principal (excluindo postura incorreta)
        alarm_violations = [v for v in violations if v != ViolationType.BAD_POSTURE]

        if alarm_violations:
            status.violation_message = self._violation_text(alarm_violations)
            if now - self._last_alarm_at >= self.ALARM_COOLDOWN_SEC:
                self._last_alarm_at = now
                trigger_alarm = True
        elif ViolationType.BAD_POSTURE in violations:
            status.violation_message = self._violation_text([ViolationType.BAD_POSTURE])
            if now - self._last_posture_warning_at >= 15.0:
                self._last_posture_warning_at = now
                trigger_posture_warning = True
        else:
            status.violation_message = "Você está focado. Continue assim."

        return trigger_alarm, trigger_posture_warning

    @staticmethod
    def _violation_text(violations: list[ViolationType]) -> str:
        messages = {
            ViolationType.EYES_CLOSED: "Você fechou os olhos por muito tempo",
            ViolationType.LOOKING_AWAY: "Você desviou o olhar da tela",
            ViolationType.BAD_POSTURE: "Sua postura saiu do ideal",
            ViolationType.LEFT_FRAME: "Você saiu da frente da câmera",
            ViolationType.PHONE_DETECTED: "Celular detectado. Guarde o aparelho",
        }
        return ". ".join(messages[v] for v in violations)

    def _draw_overlay(
        self,
        frame: np.ndarray,
        face_landmarks,
        pose_landmarks,
        hand_result,
        object_result,
        status: VisionStatus,
        monitoring: bool,
    ) -> np.ndarray:
        out = frame.copy()

        if pose_landmarks is not None:
            drawing_utils.draw_landmarks(
                out,
                pose_landmarks,
                vision.PoseLandmarksConnections.POSE_LANDMARKS,
                drawing_styles.get_default_pose_landmarks_style(),
            )

        if face_landmarks is not None:
            drawing_utils.draw_landmarks(
                out,
                face_landmarks,
                vision.FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION,
                None,
                drawing_styles.get_default_face_mesh_tesselation_style(),
            )

        if hand_result.hand_landmarks:
            for hand in hand_result.hand_landmarks:
                drawing_utils.draw_landmarks(
                    out,
                    hand,
                    vision.HandLandmarksConnections.HAND_CONNECTIONS,
                    drawing_styles.get_default_hand_landmarks_style(),
                    drawing_styles.get_default_hand_connections_style(),
                )

        if object_result.detections:
            for detection in object_result.detections:
                for category in detection.categories:
                    if category.category_name.lower() in PHONE_LABELS:
                        bbox = detection.bounding_box
                        cv2.rectangle(
                            out,
                            (bbox.origin_x, bbox.origin_y),
                            (bbox.origin_x + bbox.width, bbox.origin_y + bbox.height),
                            (0, 80, 255),
                            2,
                        )

        return self._draw_text_overlay(out, status, monitoring)

    def _draw_text_overlay(
        self,
        frame_bgr: np.ndarray,
        status: VisionStatus,
        monitoring: bool,
    ) -> np.ndarray:
        img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img)
        w, _ = img.size

        if status.active_violations:
            bar_color = (220, 70, 70)
        elif monitoring:
            bar_color = (40, 170, 110)
        else:
            bar_color = (90, 95, 110)

        draw.rectangle((0, 0, w, 42), fill=bar_color)
        mode = "Monitorando foco" if monitoring else "Pausa ou aguardando"
        draw.text((12, 10), f"{mode}  |  {status.violation_message}", fill=(255, 255, 255), font=self._font)

        lines = [
            f"Olhos: {'abertos' if status.eyes_open else 'fechados'}",
            f"Olhar: {'na tela' if status.looking_forward else 'desviado'}",
            f"Postura: {'ok' if status.good_posture else 'ajustar'}",
            f"Celular: {'detectado' if status.phone_detected else 'não detectado'}",
            f"Presença: {'sim' if status.in_frame and status.face_detected else 'não'}",
            f"Foco: {status.focus_score}%",
        ]
        y = 54
        for line in lines:
            draw.text((12, y), line, fill=(235, 235, 235), font=self._font_sm)
            y += 22

        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
