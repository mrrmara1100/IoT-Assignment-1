"""Pop-up GIFs and pictures for detected expressions, head directions, gestures and postures.

Features report what they currently see every frame, e.g. {"expression": ("smile", "expressions/smile")}.
A pop-up is shown only after the same thing has been seen for `hold_seconds` (no flicker),
and the same pop-up is not repeated until `cooldown_seconds` have passed.

Media lookup:
    "expressions/smile"     -> a random file from media/expressions/smile/
    "postures/warrior.jpg"  -> exactly that file
If a folder is empty, a text card is shown instead, telling you where to put files.
"""

import glob
import os
import random
import time

import cv2
import numpy as np
from PIL import Image, ImageSequence

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(PROJECT_DIR, "media")
MEDIA_EXTENSIONS = (".gif", ".png", ".jpg", ".jpeg", ".webp", ".bmp")
POPUP_WINDOW = "Pop-up"
MAX_GIF_FRAMES = 300

DEFAULTS = {
    "mode": "window",          # "window" = separate window, "overlay" = corner of the camera view
    "size": 360,               # longest side of the pop-up, in pixels
    "hold_seconds": 0.5,       # how long something must be seen before its pop-up appears
    "show_seconds": 3.0,       # how long a pop-up stays
    "cooldown_seconds": 4.0,   # minimum time before the same pop-up can appear again
    "repeat_while_held": True, # keep showing new pop-ups while the pose is held
}


def list_media(folder):
    return sorted(
        p for p in glob.glob(os.path.join(folder, "*"))
        if p.lower().endswith(MEDIA_EXTENSIONS)
    )


def fit_box(img, size):
    """Scale an image so its longest side equals `size`."""
    h, w = img.shape[:2]
    scale = size / max(h, w)
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    return cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=interp)


def load_frames(path, size):
    """Read a GIF or still image into [(bgr_image, seconds), ...]."""
    frames = []
    with Image.open(path) as im:
        for frame in ImageSequence.Iterator(im):
            seconds = max(frame.info.get("duration", 100) or 100, 20) / 1000.0
            rgba = frame.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
            background.alpha_composite(rgba)
            bgr = cv2.cvtColor(np.array(background.convert("RGB")), cv2.COLOR_RGB2BGR)
            frames.append((fit_box(bgr, size), seconds))
            if len(frames) >= MAX_GIF_FRAMES:
                break
    return frames


def pretty(label):
    return os.path.splitext(label)[0].replace("_", " ").title()


def text_card(title, lines, size):
    """A plain card with a big title and small hint lines (used when no media file exists)."""
    card = np.full((size, size, 3), 40, dtype=np.uint8)
    scale = 1.6
    while scale > 0.5:
        (tw, th), _ = cv2.getTextSize(title, cv2.FONT_HERSHEY_DUPLEX, scale, 2)
        if tw <= size - 30:
            break
        scale -= 0.1
    cv2.putText(card, title, ((size - tw) // 2, size // 2 - 10), cv2.FONT_HERSHEY_DUPLEX,
                scale, (0, 220, 255), 2, cv2.LINE_AA)
    y = size // 2 + 30
    for line in lines:
        (lw, _), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
        cv2.putText(card, line, (max(8, (size - lw) // 2), y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.42, (200, 200, 200), 1, cv2.LINE_AA)
        y += 20
    return card


def add_caption(img, caption):
    out = img.copy()
    h, w = out.shape[:2]
    cv2.rectangle(out, (0, h - 30), (w, h), (0, 0, 0), -1)
    (tw, _), _ = cv2.getTextSize(caption, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
    cv2.putText(out, caption, ((w - tw) // 2, h - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255), 1, cv2.LINE_AA)
    return out


class PopupManager:
    def __init__(self, config=None):
        cfg = dict(DEFAULTS)
        cfg.update((config or {}).get("popups", {}))
        self.mode = cfg["mode"]
        self.size = int(cfg["size"])
        self.hold = float(cfg["hold_seconds"])
        self.show_seconds = float(cfg["show_seconds"])
        self.cooldown = float(cfg["cooldown_seconds"])
        self.repeat = bool(cfg["repeat_while_held"])
        self.grace = 0.25  # short detection drop-outs (a missed frame) don't reset the hold timer

        self.cache = {}        # file path -> frames
        self.candidates = {}   # source -> {"label", "media", "since", "last_seen", "fired"}
        self.cooldowns = {}    # (source, label) -> time when it may show again
        self.last_file = {}    # media -> last file shown (to avoid repeating the same GIF)
        self.current = None    # the pop-up being shown
        self.window_open = False

    # ---- deciding when to show ----

    def update(self, detections, now=None):
        """detections: {source: (label, media) or None} for every active source this frame."""
        now = time.monotonic() if now is None else now

        for source in list(self.candidates):
            if source not in detections:
                del self.candidates[source]  # feature switched off

        for source, detection in detections.items():
            cand = self.candidates.get(source)
            if detection is None:
                if cand and now - cand["last_seen"] > self.grace:
                    del self.candidates[source]
                continue

            label, media = detection
            if cand is None or cand["label"] != label:
                self.candidates[source] = {"label": label, "media": media, "since": now,
                                           "last_seen": now, "fired": False}
                continue

            cand["last_seen"] = now
            if now - cand["since"] < self.hold:
                continue
            if cand["fired"] and not self.repeat:
                continue
            if now < self.cooldowns.get((source, label), 0):
                continue

            self.show(label, media, now)
            cand["fired"] = True
            self.cooldowns[(source, label)] = now + max(self.cooldown, self.show_seconds)

    def show(self, label, media, now=None):
        now = time.monotonic() if now is None else now
        path = os.path.join(MEDIA_DIR, media)
        caption = pretty(label)

        if os.path.isdir(path) or not os.path.splitext(path)[1]:
            files = list_media(path)
        else:
            files = [path] if os.path.exists(path) else []

        frames = None
        if files:
            choices = [f for f in files if f != self.last_file.get(media)] or files
            chosen = random.choice(choices)
            self.last_file[media] = chosen
            try:
                if chosen not in self.cache:
                    self.cache[chosen] = load_frames(chosen, self.size)
                frames = self.cache[chosen]
            except Exception as exc:
                print(f"Could not read {chosen}: {exc}")
        if not frames:
            hint = media.replace("\\", "/")
            frames = [(text_card(caption.upper(), ["No GIF/photo yet. Add files to:", f"media/{hint}/"],
                                 self.size), 1.0)]

        self.current = {"frames": frames, "start": now, "until": now + self.show_seconds,
                        "caption": caption, "total": sum(s for _, s in frames)}

    # ---- drawing ----

    def render(self, now=None):
        """The current pop-up image (animated), or None when nothing is showing."""
        now = time.monotonic() if now is None else now
        cur = self.current
        if cur is None or now > cur["until"]:
            self.current = None
            return None
        t = (now - cur["start"]) % cur["total"] if cur["total"] > 0 else 0
        for img, seconds in cur["frames"]:
            if t < seconds:
                return add_caption(img, cur["caption"])
            t -= seconds
        return add_caption(cur["frames"][-1][0], cur["caption"])

    def draw_overlay(self, frame, now=None):
        """Overlay mode: put the pop-up in the top-right corner of the camera view."""
        img = self.render(now)
        if img is None:
            return
        fh, fw = frame.shape[:2]
        img = fit_box(img, min(self.size, fh // 2, fw // 2))
        h, w = img.shape[:2]
        x, y = fw - w - 10, 40
        frame[y:y + h, x:x + w] = img
        cv2.rectangle(frame, (x - 1, y - 1), (x + w, y + h), (255, 255, 255), 1)

    def show_window(self, now=None, position=None):
        """Window mode: draw the pop-up (or an idle card) in its own window."""
        img = self.render(now)
        if img is None:
            img = text_card("Pop-ups", ["Hold an expression, head turn,", "gesture or posture."], self.size)
        cv2.imshow(POPUP_WINDOW, img)
        if not self.window_open:
            self.window_open = True
            if position:
                cv2.moveWindow(POPUP_WINDOW, *position)
