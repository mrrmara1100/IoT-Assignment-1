import argparse
import json
import os
import time

import cv2
import mediapipe as mp
import numpy as np

from camera import Camera, list_cameras, parse_source
from modules.face import FaceTracker
from modules.fingers import FingerCounter
from modules.gestures import GestureTracker
from modules.posture import PostureMatcher
from popup import PopupManager

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(PROJECT_DIR, "config.json")
WINDOW = "Expression & Posture Mirror"

# config name -> feature class (also the order shown in the bottom bar)
FEATURES = {
    "face": FaceTracker,
    "gestures": GestureTracker,
    "posture": PostureMatcher,
    "fingers": FingerCounter,
}

GREEN = (80, 220, 80)
GRAY = (150, 150, 150)
WHITE = (255, 255, 255)
YELLOW = (0, 220, 255)
CYAN = (255, 255, 0)
ORANGE = (0, 160, 255)

ROTATIONS = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}

# Show a "camera slow" warning when no new picture has arrived for this long
STALE_SECONDS = 1.0


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fit_width(frame, width):
    """Shrink a frame to the given width (keeping its shape). Never enlarges."""
    if not width or frame.shape[1] <= width:
        return frame
    h, w = frame.shape[:2]
    return cv2.resize(frame, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)


def draw_text_box(frame, text, org, color, scale=0.55, thickness=1):
    """Text on a dark box so it stays readable on any background."""
    (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    x, y = org
    cv2.rectangle(frame, (x - 6, y - th - 6), (x + tw + 6, y + base + 4), (0, 0, 0), -1)
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


class App:
    def __init__(self, config):
        self.config = config
        self.mirror = config.get("camera", {}).get("mirror", True)
        self.rotate = int(config.get("camera", {}).get("rotate", 0)) % 360
        self.display_width = config.get("display", {}).get("width", 960)
        self.processing_width = config.get("processing", {}).get("width", 640)

        self.features = {name: cls(config) for name, cls in FEATURES.items()}
        self.keys = {f.key: name for name, f in self.features.items()}
        self.popups = PopupManager(config)
        self.show_debug = False

        self.toast_text = ""
        self.toast_until = 0.0
        self.fps = 0.0
        self.last_frame_time = None
        self.start_time = time.monotonic()
        self.last_timestamp = -1
        self.source_label = ""
        self.clean_frame = None   # last camera image without drawings (for posture capture)
        self.last_display = None  # last finished frame, shown again while the camera is slow

        for name, enabled in config.get("features", {}).items():
            if enabled and name in self.features:
                self.toggle(name, quiet=True)

    # ---- feature switching ----

    def toast(self, text, seconds=2.5):
        self.toast_text = text
        self.toast_until = time.monotonic() + seconds
        print(text)

    def toggle(self, name, quiet=False):
        feature = self.features[name]
        if feature.running:
            feature.stop()
            self.toast(f"{feature.name}: OFF")
            return
        try:
            feature.start()
            if not quiet:
                self.toast(f"{feature.name}: ON")
        except Exception as exc:  # missing model file, etc.
            self.toast(str(exc), seconds=5)

    def handle_key(self, key):
        """Returns False when the app should quit."""
        if key in ("q", "\x1b"):
            return False
        if key == "d":
            self.show_debug = not self.show_debug
        elif key == "c":
            posture = self.features["posture"]
            if self.clean_frame is None:
                self.toast("Capture: no camera image yet")
            else:
                self.toast(posture.capture(self.clean_frame.copy()), seconds=4)
        elif key in self.keys:
            self.toggle(self.keys[key])
        return True

    # ---- per-frame work ----

    def next_timestamp(self):
        # MediaPipe VIDEO mode needs strictly increasing timestamps (milliseconds).
        ts = int((time.monotonic() - self.start_time) * 1000)
        ts = max(ts, self.last_timestamp + 1)
        self.last_timestamp = ts
        return ts

    def handle_frame(self, frame):
        """Run all active features on a camera frame and return the frame to display."""
        now = time.monotonic()
        if self.last_frame_time is not None:
            dt = now - self.last_frame_time
            if dt > 0:
                self.fps = 1.0 / dt if self.fps == 0 else 0.9 * self.fps + 0.1 / dt
        self.last_frame_time = now

        if self.rotate in ROTATIONS:
            frame = cv2.rotate(frame, ROTATIONS[self.rotate])
        if self.mirror:
            frame = cv2.flip(frame, 1)
        display = fit_width(frame, self.display_width)
        self.clean_frame = display

        active = [f for f in self.features.values() if f.running]
        display = display.copy()
        detections = {}
        if active:
            small = fit_width(display, self.processing_width)
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = self.next_timestamp()
            for feature in active:
                try:
                    feature.process(mp_image, timestamp_ms)
                except Exception as exc:
                    feature.stop()
                    self.toast(f"{feature.name} stopped: {exc}", seconds=5)
                    continue
                feature.draw(display)  # landmarks are 0-1 values, so they fit any frame size
                detections.update(feature.detections())

        self.popups.update(detections, now)
        if self.popups.mode == "overlay":
            self.popups.draw_overlay(display, now)

        self.draw_hud(display, active)
        self.last_display = display
        return display

    def stale_frame(self, message):
        """The last picture again, with a warning, while waiting for the camera."""
        frame = self.last_display.copy()
        (tw, _), _ = cv2.getTextSize(message, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        draw_text_box(frame, message, (max(10, (frame.shape[1] - tw) // 2), 30), ORANGE, scale=0.6)
        return frame

    def waiting_frame(self, message):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        cv2.putText(frame, message, (20, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, WHITE, 2, cv2.LINE_AA)
        self.draw_hud(frame, [])
        return frame

    def draw_hud(self, frame, active):
        h, w = frame.shape[:2]

        # Top-right: speed and camera
        info = f"{self.fps:4.1f} FPS  |  {self.source_label}"
        (tw, _), _ = cv2.getTextSize(info, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        draw_text_box(frame, info, (w - tw - 12, 24), WHITE, scale=0.5)

        # Bottom bar: every feature with its key (green = on)
        bar_h = 30
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, h - bar_h), (w, h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, dst=frame)

        items = [(f"[{f.key.upper()}] {f.name}", GREEN if f.running else GRAY) for f in self.features.values()]
        items += [("[C] Capture", GRAY), ("[D] Debug", GREEN if self.show_debug else GRAY), ("[Q] Quit", GRAY)]
        x = 10
        for text, color in items:
            cv2.putText(frame, text, (x, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
            (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            x += tw + 16

        # Status lines from each active feature, stacked above the bar
        y = h - bar_h - 12
        for feature in reversed(active):
            for line in reversed(feature.status()):
                draw_text_box(frame, line, (12, y), WHITE, scale=0.55)
                y -= 28

        # Debug values (key D)
        if self.show_debug:
            y = 160
            for feature in active:
                for line in feature.debug():
                    draw_text_box(frame, line, (12, y), CYAN, scale=0.45)
                    y += 22

        # Short messages (feature switched on/off, errors)
        if time.monotonic() < self.toast_until:
            (tw, _), _ = cv2.getTextSize(self.toast_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
            draw_text_box(frame, self.toast_text, (max(10, (w - tw) // 2), 60), YELLOW, scale=0.6)

    def close(self):
        for feature in self.features.values():
            if feature.running:
                feature.stop()


def run(config):
    cam_cfg = config.get("camera", {})
    camera = Camera(
        source=cam_cfg.get("source", 0),
        width=cam_cfg.get("width"),
        height=cam_cfg.get("height"),
        backend=cam_cfg.get("backend", "auto"),
    )
    print(f"Opening camera source: {camera.source!r}")
    camera.start()

    app = App(config)
    print("Keys: F face | G gestures | P posture | H fingers | C capture posture | D debug | Q quit")

    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    placed = False
    try:
        while True:
            frame = camera.read(timeout=0.1)
            app.source_label = camera.description
            if frame is not None:
                display = app.handle_frame(frame)
            elif camera.failed:
                print("Camera stopped sending frames.")
                break
            elif app.last_display is None:
                display = app.waiting_frame(f"Waiting for camera {camera.source!r} ...")
            else:
                # Keep the last picture on screen instead of flashing a waiting screen
                gap = camera.seconds_since_frame or 0
                if gap < STALE_SECONDS:
                    display = app.last_display
                elif camera.connected:
                    display = app.stale_frame(f"Camera slow: no new picture for {gap:.0f} s")
                else:
                    display = app.stale_frame(f"Camera connection lost {gap:.0f} s ago - reconnecting...")

            cv2.imshow(WINDOW, display)
            if not placed:
                cv2.moveWindow(WINDOW, 20, 20)
                placed = True
            if app.popups.mode == "window":
                app.popups.show_window(position=(display.shape[1] + 40, 20))

            key = cv2.waitKey(1) & 0xFF
            if key != 255 and not app.handle_key(chr(key).lower()):
                break
            # Closing the main window with its X button also quits
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        app.close()
        camera.release()
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="Expression & Posture Mirror")
    parser.add_argument("--source", help="camera number (0, 1, ...) or stream URL; overrides config.json")
    parser.add_argument("--rotate", type=int, choices=[0, 90, 180, 270],
                        help="turn the picture clockwise by this many degrees; overrides config.json")
    parser.add_argument("--list-cameras", action="store_true", help="list available camera numbers and exit")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="path to config file")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.list_cameras:
        backend = config.get("camera", {}).get("backend", "auto")
        cameras = list_cameras(backend=backend)
        if not cameras:
            print("No cameras found.")
        for index, w, h in cameras:
            print(f"Camera {index}: {w}x{h}")
        return

    if args.source is not None:
        config.setdefault("camera", {})["source"] = parse_source(args.source)
    if args.rotate is not None:
        config.setdefault("camera", {})["rotate"] = args.rotate

    try:
        run(config)
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
