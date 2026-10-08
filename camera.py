import threading
import time
import urllib.request
from urllib.parse import urlparse

import cv2
import numpy as np

BACKENDS = {
    "auto": cv2.CAP_ANY,
    "dshow": cv2.CAP_DSHOW,
    "msmf": cv2.CAP_MSMF,
    "ffmpeg": cv2.CAP_FFMPEG,
}

JPEG_START = b"\xff\xd8"
JPEG_END = b"\xff\xd9"
MAX_BUFFER = 4 * 1024 * 1024
STREAM_TIMEOUT = 5.0   # seconds without any data before reconnecting


def parse_source(value):
    """Turn "1" into the camera number 1; leave URLs as text."""
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return value


def _set_opencv_log_level(level_name):
    """Quiet OpenCV's own log output (it prints errors while probing missing cameras)."""
    try:
        logging = cv2.utils.logging
        previous = logging.getLogLevel()
        logging.setLogLevel(getattr(logging, level_name))
        return previous
    except AttributeError:
        return None


def list_cameras(max_index=6, backend="auto"):
    """Return [(number, width, height), ...] for every camera that opens and gives a frame."""
    previous = _set_opencv_log_level("LOG_LEVEL_SILENT")
    found = []
    try:
        for index in range(max_index):
            cap = cv2.VideoCapture(index, BACKENDS.get(backend, cv2.CAP_ANY))
            if cap.isOpened():
                ok, frame = cap.read()
                if ok:
                    h, w = frame.shape[:2]
                    found.append((index, w, h))
            cap.release()
    finally:
        if previous is not None:
            cv2.utils.logging.setLogLevel(previous)
    return found


class Camera:
    def __init__(self, source=0, width=None, height=None, backend="auto"):
        self.source = parse_source(source)
        self.width = width
        self.height = height
        self.backend = BACKENDS.get(backend, cv2.CAP_ANY)
        self.is_stream = isinstance(self.source, str)
        self.is_http = self.is_stream and self.source.lower().startswith(("http://", "https://"))

        self.cap = None
        self.failed = False
        self.connected = False
        self.reconnects = 0
        self.last_error = ""
        self.fps = 0.0
        self.last_frame_time = None

        self._frame = None
        self._frame_id = 0
        self._last_read_id = 0
        self._cond = threading.Condition()
        self._running = False
        self._thread = None
        self._response = None

    @property
    def description(self):
        size = ""
        if self._frame is not None:
            h, w = self._frame.shape[:2]
            size = f" {w}x{h}"
        if self.is_http:
            host = urlparse(self.source).hostname
            if not self.connected:
                return f"ESP32 {host} (connecting)"
            return f"ESP32 {host}{size} {self.fps:.0f} fps"
        if self.is_stream:
            return f"Stream{size}"
        return f"Camera {self.source}{size}"

    @property
    def seconds_since_frame(self):
        if self.last_frame_time is None:
            return None
        return time.monotonic() - self.last_frame_time

    # ---- starting ----

    def _open(self):
        cap = cv2.VideoCapture(self.source, self.backend)
        if not self.is_stream:
            if self.width:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            if self.height:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def start(self):
        self._running = True
        if self.is_http:
            # The board may still be starting up; the reader keeps trying in the background.
            self._thread = threading.Thread(target=self._http_reader, daemon=True)
        else:
            self.cap = self._open()
            if not self.cap.isOpened():
                self._running = False
                raise RuntimeError(
                    f"Could not open camera source {self.source!r}. "
                    "Run 'python main.py --list-cameras' to see available camera numbers."
                )
            self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        return self

    def _publish(self, frame):
        now = time.monotonic()
        if self.last_frame_time is not None:
            dt = now - self.last_frame_time
            if dt > 0:
                self.fps = 1.0 / dt if self.fps == 0 else 0.8 * self.fps + 0.2 / dt
        self.last_frame_time = now
        with self._cond:
            self._frame = frame
            self._frame_id += 1
            self._cond.notify_all()

    # ---- readers ----

    def _reader(self):
        """Webcams, the Pocket 3 and other OpenCV sources."""
        failures = 0
        while self._running:
            ok, frame = self.cap.read()
            if ok:
                failures = 0
                self.connected = True
                self._publish(frame)
                continue

            failures += 1
            if self.is_stream and failures % 10 == 0:
                self.cap.release()
                time.sleep(1.0)
                self.cap = self._open()
            elif not self.is_stream and failures >= 50:
                with self._cond:
                    self.failed = True
                    self._cond.notify_all()
                return
            time.sleep(0.02)

    def _http_reader(self):
        """ESP32-CAM style MJPEG stream: a never-ending series of JPEG pictures."""
        while self._running:
            try:
                self._response = urllib.request.urlopen(self.source, timeout=STREAM_TIMEOUT)
                self.connected = True
                buffer = bytearray()
                while self._running:
                    chunk = self._response.read1(65536)
                    if not chunk:
                        raise ConnectionError("board closed the stream")
                    buffer += chunk
                    self._extract_frames(buffer)
            except Exception as exc:
                if self._running:
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    self.reconnects += 1
            finally:
                self.connected = False
                if self._response is not None:
                    try:
                        self._response.close()
                    except Exception:
                        pass
                    self._response = None
            if self._running:
                time.sleep(0.5)

    def _extract_frames(self, buffer):
        """Cut complete JPEG pictures out of the buffer; keep only the newest one."""
        newest = None
        while True:
            start = buffer.find(JPEG_START)
            if start < 0:
                del buffer[:-1]  # keep a possible half marker
                break
            end = buffer.find(JPEG_END, start + 2)
            if end < 0:
                del buffer[:start]
                if len(buffer) > MAX_BUFFER:
                    buffer.clear()
                break
            newest = bytes(buffer[start:end + 2])
            del buffer[:end + 2]
        if newest is not None:
            frame = cv2.imdecode(np.frombuffer(newest, np.uint8), cv2.IMREAD_COLOR)
            if frame is not None:  # broken pictures (cut off by Wi-Fi) are skipped
                self._publish(frame)

    # ---- reading ----

    def read(self, timeout=2.0):
        """Wait for a frame newer than the last one returned. Returns None on timeout or failure."""
        with self._cond:
            self._cond.wait_for(
                lambda: self._frame_id != self._last_read_id or self.failed or not self._running,
                timeout=timeout,
            )
            if self._frame_id == self._last_read_id:
                return None
            self._last_read_id = self._frame_id
            return self._frame

    def release(self):
        self._running = False
        with self._cond:
            self._cond.notify_all()
        response = self._response
        if response is not None:
            try:
                response.close()  # unblocks the reader if it is waiting for data
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)
        if self.cap:
            self.cap.release()
