"""Posture matching: compares your body pose with the photos in media/postures/.

How it works:
  1. On start, the body model is run once on every photo in media/postures/ and the
     33 body points are saved to cache/pose_refs.json (photos are only re-measured if
     they change).
  2. Every frame, the direction of each limb (upper arm, forearm, thigh, shin, torso,
     head) is compared with each photo. Directions don't depend on where you stand or
     how big you are in the picture, and limbs that are out of view are skipped.
  3. The best photo above the match threshold pops up.

Press C while posture is on to save the current camera image as a new reference photo.
"""

import json
import math
import os
import time

import cv2
import numpy as np
from PIL import Image
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

from modules.base import Feature, MEDIA_DIR, PROJECT_DIR

POSTURE_DIR = os.path.join(MEDIA_DIR, "postures")
CACHE_PATH = os.path.join(PROJECT_DIR, "cache", "pose_refs.json")
PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
POSE_CONNECTIONS = vision.PoseLandmarksConnections.POSE_LANDMARKS

# Limb segments compared between you and the photos (pairs of body point numbers)
SEGMENTS = [
    (11, 13), (13, 15),   # left upper arm, forearm
    (12, 14), (14, 16),   # right upper arm, forearm
    (11, 23), (12, 24),   # left / right side of torso
    (23, 25), (25, 27),   # left thigh, shin
    (24, 26), (26, 28),   # right thigh, shin
    (11, 0), (12, 0),     # shoulders to nose (head position)
]

# Left/right body point pairs, used to compare against a mirrored version of each photo
LEFT_RIGHT = [(1, 4), (2, 5), (3, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16), (17, 18),
              (19, 20), (21, 22), (23, 24), (25, 26), (27, 28), (29, 30), (31, 32)]

DEFAULTS = {
    "match_threshold": 0.88,   # 0-1, higher = stricter
    "min_segments": 4,         # limbs that must be visible in both you and the photo
    "min_visibility": 0.5,     # how sure the model must be that a body point is visible
    "allow_mirrored": True,    # also accept the photo's pose done with the other side
}


def to_points(landmarks, width, height):
    """Body points in pixel units: [[x, y, visibility], ...]."""
    return [[lm.x * width, lm.y * height, lm.visibility if lm.visibility is not None else 1.0]
            for lm in landmarks]


def mirror_points(points):
    """The same pose seen in a mirror: flip x and swap left/right body points."""
    flipped = [[-x, y, v] for x, y, v in points]
    for a, b in LEFT_RIGHT:
        flipped[a], flipped[b] = flipped[b], flipped[a]
    return flipped


def segment_directions(points, min_visibility):
    """Unit direction of each segment, or None when it is not visible."""
    dirs = []
    for a, b in SEGMENTS:
        pa, pb = points[a], points[b]
        if min(pa[2], pb[2]) < min_visibility:
            dirs.append(None)
            continue
        dx, dy = pb[0] - pa[0], pb[1] - pa[1]
        length = math.hypot(dx, dy)
        dirs.append((dx / length, dy / length) if length > 1e-6 else None)
    return dirs


def similarity(live_dirs, ref_dirs, min_segments):
    """0-1 score: 1 = every shared limb points the same way. None if too few shared limbs."""
    scores = [
        (1 + a[0] * b[0] + a[1] * b[1]) / 2
        for a, b in zip(live_dirs, ref_dirs)
        if a is not None and b is not None
    ]
    if len(scores) < min_segments:
        return None
    return sum(scores) / len(scores)


def read_rgb(path):
    with Image.open(path) as im:
        return np.array(im.convert("RGB"))  # first frame for GIFs


class PostureMatcher(Feature):
    name = "Posture"
    key = "p"
    model_file = "pose_landmarker_full.task"

    def __init__(self, config=None):
        super().__init__(config)
        cfg = {**DEFAULTS, **self.config.get("posture", {})}
        self.threshold = cfg["match_threshold"]
        self.min_segments = cfg["min_segments"]
        self.min_visibility = cfg["min_visibility"]
        self.allow_mirrored = cfg["allow_mirrored"]
        self.landmarker = None
        self.refs = {}        # file name -> list of segment-direction lists (normal, mirrored)
        self.landmarks = None
        self.match = None     # (file name, score)
        self.ranking = []     # [(score, file name), ...] best first
        self.message = ""

    # ---- reference photos ----

    def _photo_landmarker(self):
        options = vision.PoseLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=self.model_path),
            running_mode=vision.RunningMode.IMAGE,
            num_poses=1,
        )
        return vision.PoseLandmarker.create_from_options(options)

    def _measure_photo(self, landmarker, path):
        rgb = read_rgb(path)
        result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)))
        if not result.pose_landmarks:
            return None
        h, w = rgb.shape[:2]
        return to_points(result.pose_landmarks[0], w, h)

    def _add_ref(self, name, points):
        variants = [segment_directions(points, self.min_visibility)]
        if self.allow_mirrored:
            variants.append(segment_directions(mirror_points(points), self.min_visibility))
        self.refs[name] = variants

    def load_references(self):
        os.makedirs(POSTURE_DIR, exist_ok=True)
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, ValueError):
            cache = {}

        files = sorted(f for f in os.listdir(POSTURE_DIR) if f.lower().endswith(PHOTO_EXTENSIONS))
        new_cache, skipped, landmarker = {}, [], None
        try:
            for name in files:
                path = os.path.join(POSTURE_DIR, name)
                stamp = [os.path.getmtime(path), os.path.getsize(path)]
                entry = cache.get(name)
                if not entry or entry.get("stamp") != stamp:
                    if landmarker is None:
                        landmarker = self._photo_landmarker()
                    try:
                        points = self._measure_photo(landmarker, path)
                    except Exception as exc:
                        print(f"Posture: could not read {name}: {exc}")
                        points = None
                    entry = {"stamp": stamp, "points": points}
                new_cache[name] = entry
                if entry["points"] is None:
                    skipped.append(name)
        finally:
            if landmarker is not None:
                landmarker.close()

        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(new_cache, f)

        self.refs = {}
        for name, entry in new_cache.items():
            if entry["points"] is not None:
                self._add_ref(name, entry["points"])

        if skipped:
            print(f"Posture: no body found in {', '.join(skipped)} (skipped)")
        if not self.refs:
            self.message = "no reference photos in media/postures/ (press C to capture one)"
        else:
            self.message = ""
        print(f"Posture: {len(self.refs)} reference photo(s) loaded")

    def capture(self, frame_bgr):
        """Save the current camera image as a new reference photo. Returns a message."""
        if not self.running:
            return "Turn posture on (P) before capturing"
        name = time.strftime("capture_%Y%m%d_%H%M%S.jpg")
        path = os.path.join(POSTURE_DIR, name)
        os.makedirs(POSTURE_DIR, exist_ok=True)
        cv2.imwrite(path, frame_bgr)
        landmarker = self._photo_landmarker()
        try:
            points = self._measure_photo(landmarker, path)
        finally:
            landmarker.close()
        if points is None:
            os.remove(path)
            return "Capture: no body found, nothing saved"
        self.load_references()
        return f"Captured posture: media/postures/{name}"

    # ---- live matching ----

    def start(self):
        self.check_model()
        self.load_references()
        options = vision.PoseLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=self.model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
        )
        self.landmarker = vision.PoseLandmarker.create_from_options(options)
        super().start()

    def process(self, mp_image, timestamp_ms):
        result = self.landmarker.detect_for_video(mp_image, timestamp_ms)
        self.analyze(result, mp_image.width, mp_image.height)

    def analyze(self, result, width, height):
        self.match = None
        self.ranking = []
        if not result.pose_landmarks:
            self.landmarks = None
            return
        self.landmarks = result.pose_landmarks[0]
        live = segment_directions(to_points(self.landmarks, width, height), self.min_visibility)

        for name, variants in self.refs.items():
            scores = [s for s in (similarity(live, ref, self.min_segments) for ref in variants) if s is not None]
            if scores:
                self.ranking.append((max(scores), name))
        self.ranking.sort(reverse=True)
        if self.ranking and self.ranking[0][0] >= self.threshold:
            score, name = self.ranking[0]
            self.match = (name, score)

    def draw(self, frame):
        if self.landmarks is None:
            return
        h, w = frame.shape[:2]
        pts = [(int(lm.x * w), int(lm.y * h)) for lm in self.landmarks]
        vis = [(lm.visibility or 0) >= self.min_visibility for lm in self.landmarks]
        for conn in POSE_CONNECTIONS:
            if vis[conn.start] and vis[conn.end]:
                cv2.line(frame, pts[conn.start], pts[conn.end], (0, 200, 255), 2, cv2.LINE_AA)
        for (x, y), v in zip(pts, vis):
            if v:
                cv2.circle(frame, (x, y), 3, (0, 120, 255), -1)

    def detections(self):
        if self.match is None:
            return {"posture": None}
        name = self.match[0]
        return {"posture": (name, f"postures/{name}")}

    def status(self):
        if self.message:
            return [f"Posture: {self.message}"]
        if self.landmarks is None:
            return ["Posture: no body"]
        if self.match:
            return [f"Posture: {os.path.splitext(self.match[0])[0]} ({self.match[1]:.0%})"]
        if self.ranking:
            return [f"Posture: no match (closest {self.ranking[0][0]:.0%})"]
        return ["Posture: not enough of the body visible"]

    def debug(self):
        return [f"{score:.0%}  {name}" for score, name in self.ranking[:4]]

    def stop(self):
        if self.landmarker:
            self.landmarker.close()
            self.landmarker = None
        self.landmarks = None
        self.match = None
        self.ranking = []
        super().stop()
