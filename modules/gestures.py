"""Hand gestures with MediaPipe's built-in gesture recognizer.

Recognized out of the box: thumbs up, thumbs down, victory, fist, open palm,
pointing up and "I love you". Each one pops up media from media/gestures/<name>/.
"""

import cv2
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

from modules.base import Feature
from modules.fingers import draw_hand

# Model's gesture name -> media folder name
GESTURE_FOLDERS = {
    "Thumb_Up": "thumbs_up",
    "Thumb_Down": "thumbs_down",
    "Victory": "victory",
    "Closed_Fist": "fist",
    "Open_Palm": "open_palm",
    "Pointing_Up": "pointing_up",
    "ILoveYou": "i_love_you",
}

WRIST = 0


class GestureTracker(Feature):
    name = "Gestures"
    key = "g"
    model_file = "gesture_recognizer.task"

    def __init__(self, config=None):
        super().__init__(config)
        self.min_score = self.config.get("gestures", {}).get("min_score", 0.6)
        self.recognizer = None
        self.hands = []      # [(landmarks, gesture folder or None, score), ...]
        self.best = None     # (folder, score) of the most confident gesture this frame

    def start(self):
        self.check_model()
        options = vision.GestureRecognizerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=self.model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
        )
        self.recognizer = vision.GestureRecognizer.create_from_options(options)
        super().start()

    def process(self, mp_image, timestamp_ms):
        result = self.recognizer.recognize_for_video(mp_image, timestamp_ms)
        self.analyze(result)

    def analyze(self, result):
        self.hands = []
        self.best = None
        for landmarks, gestures in zip(result.hand_landmarks, result.gestures):
            top = gestures[0] if gestures else None
            folder = GESTURE_FOLDERS.get(top.category_name) if top else None
            score = top.score if top else 0.0
            if folder and score < self.min_score:
                folder = None
            self.hands.append((landmarks, folder, score))
            if folder and (self.best is None or score > self.best[1]):
                self.best = (folder, score)

    def draw(self, frame):
        h, w = frame.shape[:2]
        for landmarks, folder, score in self.hands:
            draw_hand(frame, landmarks)
            if folder:
                x, y = int(landmarks[WRIST].x * w), int(landmarks[WRIST].y * h)
                text = folder.replace("_", " ")
                cv2.putText(frame, text, (x - 40, min(h - 50, y + 30)), cv2.FONT_HERSHEY_SIMPLEX,
                            0.8, (255, 0, 255), 2, cv2.LINE_AA)

    def detections(self):
        if self.best is None:
            return {"gesture": None}
        folder = self.best[0]
        return {"gesture": (folder, f"gestures/{folder}")}

    def status(self):
        if not self.hands:
            return ["Gesture: no hand"]
        if self.best is None:
            return ["Gesture: none"]
        return [f"Gesture: {self.best[0].replace('_', ' ')} ({self.best[1]:.0%})"]

    def debug(self):
        return [f"hand {i + 1}: {folder or '-'} {score:.2f}" for i, (_, folder, score) in enumerate(self.hands)]

    def stop(self):
        if self.recognizer:
            self.recognizer.close()
            self.recognizer = None
        self.hands = []
        self.best = None
        super().stop()
