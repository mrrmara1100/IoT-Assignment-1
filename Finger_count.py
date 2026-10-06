import os
import time

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

# Model file downloaded from Google's MediaPipe model storage
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "hand_landmarker.task")

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


def draw_landmarks(frame, landmarks):
    """Draw the hand skeleton (lines + joints) onto the BGR frame."""
    h, w = frame.shape[:2]
    points = [(int(p.x * w), int(p.y * h)) for p in landmarks]

    for conn in HAND_CONNECTIONS:
        cv2.line(frame, points[conn.start], points[conn.end], (255, 255, 255), 2)
    for x, y in points:
        cv2.circle(frame, (x, y), 4, (0, 0, 255), -1)


def main():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model file not found: {MODEL_PATH}")

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    options = vision.HandLandmarkerOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    start = time.monotonic()

    with vision.HandLandmarker.create_from_options(options) as landmarker:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            # VIDEO mode needs a steadily increasing timestamp in milliseconds
            timestamp_ms = int((time.monotonic() - start) * 1000)
            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            for landmarks, handedness in zip(result.hand_landmarks, result.handedness):
                draw_landmarks(frame, landmarks)

                label = handedness[0].category_name
                num_fingers = count_fingers(landmarks, label)

                print(f"Hand: {label}, Fingers up: {num_fingers}")

                cv2.putText(
                    frame,
                    f"{label}: {num_fingers}",
                    (10, 60 if label == "Right" else 120),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.5,
                    (0, 255, 0),
                    3,
                )

            cv2.imshow("Finger Count (0-5)", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
