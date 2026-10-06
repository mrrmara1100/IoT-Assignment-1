"""Finger counting (0-5 per hand, up to 2 hands). Same logic as Finger_count.py."""

import cv2
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

from modules.base import Feature

HAND_CONNECTIONS = vision.HandLandmarksConnections.HAND_CONNECTIONS

# Landmark indices (same 21-point layout as mp.solutions.hands.HandLandmark)
THUMB_IP, THUMB_TIP = 3, 4
INDEX_FINGER_PIP, INDEX_FINGER_TIP = 6, 8
MIDDLE_FINGER_PIP, MIDDLE_FINGER_TIP = 10, 12
RING_FINGER_PIP, RING_FINGER_TIP = 14, 16
PINKY_PIP, PINKY_TIP = 18, 20


def count_fingers(landmarks, handedness):
    """
    Return how many fingers are up (0-5).
    landmarks: list of 21 normalized landmarks for one hand
    handedness: 'Left' or 'Right'
    """
    lm = landmarks
    fingers_up = 0

    # ---- Thumb ----
    thumb_tip = lm[THUMB_TIP]
    thumb_ip = lm[THUMB_IP]

    if handedness == "Right":
        if thumb_tip.x < thumb_ip.x:
            fingers_up += 1
    else:  # Left hand
        if thumb_tip.x > thumb_ip.x:
            fingers_up += 1

    # ---- Other fingers ----
    finger_tips = [INDEX_FINGER_TIP, MIDDLE_FINGER_TIP, RING_FINGER_TIP, PINKY_TIP]
    finger_pips = [INDEX_FINGER_PIP, MIDDLE_FINGER_PIP, RING_FINGER_PIP, PINKY_PIP]

    for tip_id, pip_id in zip(finger_tips, finger_pips):
        if lm[tip_id].y < lm[pip_id].y:
            fingers_up += 1

    return fingers_up


def draw_hand(frame, landmarks):
    """Draw the hand skeleton (lines + joints) onto the BGR frame."""
    h, w = frame.shape[:2]
    points = [(int(p.x * w), int(p.y * h)) for p in landmarks]

    for conn in HAND_CONNECTIONS:
        cv2.line(frame, points[conn.start], points[conn.end], (255, 255, 255), 2)
    for x, y in points:
        cv2.circle(frame, (x, y), 4, (0, 0, 255), -1)


class FingerCounter(Feature):
    name = "Fingers"
    key = "h"
    model_file = "hand_landmarker.task"

    def __init__(self, config=None):
        super().__init__(config)
        self.landmarker = None
        self.hands = []   # [(landmarks, label, count), ...] from the latest frame

    def start(self):
        self.check_model()
        options = vision.HandLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=self.model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.landmarker = vision.HandLandmarker.create_from_options(options)
        super().start()

    def process(self, mp_image, timestamp_ms):
        result = self.landmarker.detect_for_video(mp_image, timestamp_ms)
        self.hands = []
        for landmarks, handedness in zip(result.hand_landmarks, result.handedness):
            label = handedness[0].category_name
            self.hands.append((landmarks, label, count_fingers(landmarks, label)))

    def draw(self, frame):
        for landmarks, label, num_fingers in self.hands:
            draw_hand(frame, landmarks)
            cv2.putText(
                frame,
                f"{label}: {num_fingers}",
                (10, 60 if label == "Right" else 120),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.5,
                (0, 255, 0),
                3,
            )

    def stop(self):
        if self.landmarker:
            self.landmarker.close()
            self.landmarker = None
        self.hands = []
        super().stop()
