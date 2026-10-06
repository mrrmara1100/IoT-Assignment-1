"""Common shape for every detection feature (fingers, face, gestures, posture).

main.py only talks to features through these methods, so new features can be
added without touching the camera loop:

    start()                         load the model (called when switched on)
    process(mp_image, timestamp_ms) run detection on one frame
    draw(frame)                     draw results onto the display frame
    detections()                    what to show pop-ups for: {source: (label, media) or None}
    status()                        short text lines shown on screen
    debug()                         raw numbers shown when debug view is on (key D)
    stop()                          free the model (called when switched off)
"""

import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(PROJECT_DIR, "models")
MEDIA_DIR = os.path.join(PROJECT_DIR, "media")


class Feature:
    name = "Feature"   # shown on screen
    key = ""           # keyboard key that switches it on/off
    model_file = ""    # file name inside models/

    def __init__(self, config=None):
        self.config = config or {}
        self.running = False

    @property
    def model_path(self):
        return os.path.join(MODELS_DIR, self.model_file)

    def check_model(self):
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"{self.name}: model file missing: models/{self.model_file} (see README, section 3.3)"
            )

    def start(self):
        self.running = True

    def process(self, mp_image, timestamp_ms):
        pass

    def draw(self, frame):
        pass

    def detections(self):
        return {}

    def status(self):
        return []

    def debug(self):
        return []

    def stop(self):
        self.running = False
