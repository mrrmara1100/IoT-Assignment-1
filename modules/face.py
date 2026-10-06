"""Face expressions (smile, surprise, wink, kiss, angry, sad) and head direction.

Expressions come from the face model's 52 expression scores ("blendshapes", 0-1),
turned into labels with simple threshold rules. Head direction is measured from the
3D face points: how much nearer one side of the face is to the camera than the other.
All thresholds can be tuned in config.json -> "face" (press D to see the live values).
"""

import math

import cv2
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

from modules.base import Feature

FACE_CONTOURS = getattr(vision.FaceLandmarksConnections, "FACE_LANDMARKS_CONTOURS", [])

# Face point numbers used for head direction
FACE_EDGE_A, FACE_EDGE_B = 234, 454     # sides of the face (near the ears)
FOREHEAD, CHIN = 10, 152
EYE_CORNER_A, EYE_CORNER_B = 33, 263    # outer eye corners

DEFAULT_THRESHOLDS = {
    "smile": 0.6,          # mouthSmile (average of both sides)
    "surprise_jaw": 0.4,   # jawOpen
    "surprise_brow": 0.4,  # browInnerUp or eyeWide
    "kiss": 0.6,           # mouthPucker
    "wink_closed": 0.6,    # eyeBlink of the closed eye
    "wink_open": 0.35,     # eyeBlink of the open eye must stay below this
    "angry": 0.6,          # browDown (average); often high even on calm faces, so keep this high
    "sad": 0.35,           # mouthFrown (average)
}

DEFAULT_HEAD = {
    "turn_degrees": 25,    # look left / right
    "nod_degrees": 18,     # look up / down
    "tilt_degrees": 20,    # tilt left / right
}


def classify_expression(bs, t):
    """bs: {blendshape name: score}. Returns an expression label or None."""
    def avg(a, b):
        return (bs.get(a, 0.0) + bs.get(b, 0.0)) / 2

    smile = avg("mouthSmileLeft", "mouthSmileRight")
    jaw = bs.get("jawOpen", 0.0)
    brow_up = max(bs.get("browInnerUp", 0.0), avg("eyeWideLeft", "eyeWideRight"))
    blink_a, blink_b = bs.get("eyeBlinkLeft", 0.0), bs.get("eyeBlinkRight", 0.0)
    pucker = bs.get("mouthPucker", 0.0)
    brow_down = avg("browDownLeft", "browDownRight")
    frown = avg("mouthFrownLeft", "mouthFrownRight")

    if jaw > t["surprise_jaw"] and brow_up > t["surprise_brow"] and smile < t["smile"]:
        return "surprise"
    if pucker > t["kiss"] and jaw < t["surprise_jaw"] and smile < t["smile"]:
        return "kiss"
    if max(blink_a, blink_b) > t["wink_closed"] and min(blink_a, blink_b) < t["wink_open"]:
        return "wink"
    if smile > t["smile"]:
        return "smile"
    if brow_down > t["angry"]:
        return "angry"
    if frown > t["sad"]:
        return "sad"
    return None


def head_angles(landmarks, width, height):
    """
    Returns (turn, nod, tilt) in degrees, as seen in the image:
      turn > 0: face points toward the image's right side
      nod  > 0: face points up
      tilt > 0: head leans toward the image's right side
    """
    def p(i):
        lm = landmarks[i]
        return lm.x * width, lm.y * height, lm.z * width  # z uses the same scale as x

    a, b = p(FACE_EDGE_A), p(FACE_EDGE_B)
    left, right = (a, b) if a[0] <= b[0] else (b, a)
    # Face turned toward the right: the left edge comes nearer the camera (smaller z)
    turn = math.degrees(math.atan2(right[2] - left[2], right[0] - left[0]))

    top, bottom = p(FOREHEAD), p(CHIN)
    # Looking up: the chin comes nearer the camera than the forehead
    nod = math.degrees(math.atan2(top[2] - bottom[2], bottom[1] - top[1]))

    a, b = p(EYE_CORNER_A), p(EYE_CORNER_B)
    left, right = (a, b) if a[0] <= b[0] else (b, a)
    tilt = math.degrees(math.atan2(right[1] - left[1], right[0] - left[0]))

    return turn, nod, tilt


def classify_head(turn, nod, tilt, h, mirrored=True):
    """Pick the strongest head movement past its threshold. Labels are from the user's point of view."""
    if not mirrored:
        # Without mirroring, the image's right is the user's left
        turn, tilt = -turn, -tilt
    options = [
        (abs(turn) / h["turn_degrees"], "look_right" if turn > 0 else "look_left"),
        (abs(nod) / h["nod_degrees"], "look_up" if nod > 0 else "look_down"),
        (abs(tilt) / h["tilt_degrees"], "tilt_right" if tilt > 0 else "tilt_left"),
    ]
    strength, label = max(options)
    return label if strength >= 1.0 else None


class FaceTracker(Feature):
    name = "Face"
    key = "f"
    model_file = "face_landmarker.task"

    def __init__(self, config=None):
        super().__init__(config)
        face_cfg = self.config.get("face", {})
        self.thresholds = {**DEFAULT_THRESHOLDS, **face_cfg.get("thresholds", {})}
        self.head_cfg = {**DEFAULT_HEAD, **face_cfg.get("head", {})}
        self.num_faces = face_cfg.get("num_faces", 1)
        self.mirrored = self.config.get("camera", {}).get("mirror", True)
        self.landmarker = None
        self._reset()

    def _reset(self):
        self.landmarks = None
        self.blendshapes = {}
        self.expression = None
        self.head = None
        self.angles = (0.0, 0.0, 0.0)

    def start(self):
        self.check_model()
        options = vision.FaceLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=self.model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=self.num_faces,
            output_face_blendshapes=True,
        )
        self.landmarker = vision.FaceLandmarker.create_from_options(options)
        super().start()

    def process(self, mp_image, timestamp_ms):
        result = self.landmarker.detect_for_video(mp_image, timestamp_ms)
        self.analyze(result, mp_image.width, mp_image.height)

    def analyze(self, result, width, height):
        if not result.face_landmarks:
            self._reset()
            return
        # Use the first (largest/most confident) face
        self.landmarks = result.face_landmarks[0]
        self.blendshapes = {c.category_name: c.score for c in result.face_blendshapes[0]}
        self.expression = classify_expression(self.blendshapes, self.thresholds)
        self.angles = head_angles(self.landmarks, width, height)
        self.head = classify_head(*self.angles, self.head_cfg, self.mirrored)

    def draw(self, frame):
        if self.landmarks is None:
            return
        h, w = frame.shape[:2]
        pts = [(int(p.x * w), int(p.y * h)) for p in self.landmarks]
        if FACE_CONTOURS:
            for conn in FACE_CONTOURS:
                cv2.line(frame, pts[conn.start], pts[conn.end], (255, 200, 80), 1, cv2.LINE_AA)
        else:
            for x, y in pts[::4]:
                cv2.circle(frame, (x, y), 1, (255, 200, 80), -1)

    def detections(self):
        return {
            "expression": (self.expression, f"expressions/{self.expression}") if self.expression else None,
            "head": (self.head, f"head/{self.head}") if self.head else None,
        }

    def status(self):
        if self.landmarks is None:
            return ["Face: no face"]
        expr = self.expression.replace("_", " ") if self.expression else "neutral"
        head = self.head.replace("_", " ") if self.head else "straight"
        return [f"Face: {expr}  |  Head: {head}"]

    def debug(self):
        if self.landmarks is None:
            return []
        bs = self.blendshapes

        def avg(a, b):
            return (bs.get(a, 0) + bs.get(b, 0)) / 2

        turn, nod, tilt = self.angles
        return [
            f"turn {turn:+5.1f}  nod {nod:+5.1f}  tilt {tilt:+5.1f} deg",
            f"smile {avg('mouthSmileLeft', 'mouthSmileRight'):.2f}  jawOpen {bs.get('jawOpen', 0):.2f}"
            f"  browUp {bs.get('browInnerUp', 0):.2f}",
            f"blink L {bs.get('eyeBlinkLeft', 0):.2f} R {bs.get('eyeBlinkRight', 0):.2f}"
            f"  pucker {bs.get('mouthPucker', 0):.2f}",
            f"browDown {avg('browDownLeft', 'browDownRight'):.2f}"
            f"  frown {avg('mouthFrownLeft', 'mouthFrownRight'):.2f}",
        ]

    def stop(self):
        if self.landmarker:
            self.landmarker.close()
            self.landmarker = None
        self._reset()
        super().stop()
