# IoT Assignment 1 – Finger Detection and Counting

Real-time hand tracking and finger counting with **MediaPipe** and **OpenCV**, using a laptop
webcam, an **ESP32-CAM** over Wi‑Fi, or a DJI Osmo Pocket 3 over USB.

The program finds up to two hands in each camera image, draws the hand skeleton, and shows how
many fingers are raised on each hand (0–5), with a Left/Right label.

**Contents**

1. [Features and status](#1-features-and-status)
2. [Quick start (webcam)](#2-quick-start-webcam)
3. [Using the ESP32-CAM](#3-using-the-esp32-cam)
4. [Using the DJI Osmo Pocket 3](#4-using-the-dji-osmo-pocket-3)
5. [Controls and settings](#5-controls-and-settings)
6. [How finger counting works](#6-how-finger-counting-works)
7. [Known issue: ESP32-CAM connection](#7-known-issue-esp32-cam-connection)
8. [Troubleshooting](#8-troubleshooting)
9. [Requirements](#9-requirements)
10. [Project structure](#10-project-structure)
11. [Future work](#11-future-work)
12. [Notes](#12-notes)

---

## 1. Features and status

Finger counting is the current project scope.

| Part | Status |
|---|---|
| **Finger counting** (0–5 per hand, up to 2 hands, Left/Right) | ✅ Works |
| **Laptop webcam** | ✅ Works |
| **ESP32-CAM over Wi‑Fi** | ✅ Works, with a weak connection ([Section 7](#7-known-issue-esp32-cam-connection)) |
| **Upside-down ESP32 picture** | ✅ Fixed with `--rotate 180` |
| **Camera choice** (`--source`, `config.json`) and camera finder (`--list-cameras`) | ✅ Works |
| **On-screen info:** frames per second, camera name, key bar | ✅ Works |
| **DJI Osmo Pocket 3** | Supported in the code, not tested yet |
| Face expressions, head direction, hand gestures, posture matching, GIF pop-ups | ⏸️ Built but postponed, switched off ([Section 11](#11-future-work)) |

**Not possible / not included**

| Item | Reason |
|---|---|
| Running the detection on the ESP32 itself | The ESP32 has far too little memory for Python or MediaPipe. It only acts as the camera; the laptop does the detection. |
| Recognizing **who** a person is | Not part of this project; MediaPipe does not do identity recognition. |

---

## 2. Quick start (webcam)

Windows, PowerShell. Python 3.13 is required ([Section 9](#9-requirements)).

1. Get the project:

   ```
   git clone https://github.com/mrrmara1100/IoT-Assignment-1.git
   ```

   ```
   cd IoT-Assignment-1
   ```

2. Create and activate a virtual environment (note: `Scripts`, with an **s**):

   ```
   python -m venv myenv
   ```

   ```
   .\myenv\Scripts\activate
   ```

   The prompt now starts with `(myenv)`. Activate it again each time you open a new terminal.

3. Install the libraries:

   ```
   pip install -r requirements.txt
   ```

4. Run:

   ```
   python main.py
   ```

Hold your hand(s) up with the palm facing the camera. The count appears at the top-left
(`Right: 3`, `Left: 5`). Press **Q** to quit.

A few `INFO` / `WARNING` lines from MediaPipe at start-up are normal. The model file
(`models/hand_landmarker.task`) is included in the repository; no download is needed.

---

## 3. Using the ESP32-CAM

The ESP32-CAM (AI Thinker) only sends pictures over Wi‑Fi; the laptop does the finger counting.

### 3.1 One-time: install ESP32 support in the Arduino IDE

1. **File → Preferences → Additional boards manager URLs**, add:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
2. **Boards Manager** (left sidebar) → search **esp32** → install **"esp32 by Espressif Systems"**.

### 3.2 One-time: upload the camera program

1. **Tools → Board → esp32 → AI Thinker ESP32-CAM**.
2. **File → Examples → ESP32 → Camera → CameraWebServer**.
3. In the `board_config.h` tab, enable only `#define CAMERA_MODEL_AI_THINKER`.
4. In the main `.ino` tab, enter your Wi‑Fi name (`ssid`) and `password`. It must be a **2.4 GHz**
   network on the same router as the laptop.
5. **Tools → Partition Scheme → "Huge APP (3MB No OTA/1MB SPIFFS)"**, select the COM port, and
   click **Upload**. If it gets stuck at `Connecting.....`, hold **IO0** on the programmer board,
   tap **RST**, then release IO0.

### 3.3 Each time

1. Power the board and open **Serial Monitor** (115200 baud). Press **RST** on the board; it
   prints `Camera Ready! Use 'http://192.168.1.15' to connect` (your address may differ).
2. Optional: open that address in a browser, set **Resolution** to **VGA** or lower, then **close
   the tab**. The board can only stream to one viewer at a time.
3. Start the program with the board's stream address. The AI Thinker camera is mounted upside
   down, so add `--rotate 180`:

   ```
   python main.py --source http://192.168.1.15:81/stream --rotate 180
   ```

The top-right corner shows the board's address, picture size and frames per second. If pictures
stop, the last one stays on screen with a "Camera slow" or "Connection lost – reconnecting"
message, and the program reconnects by itself.

To avoid typing the options every time, set them in `config.json`:
`"source": "http://192.168.1.15:81/stream"` and `"rotate": 180`.

---

## 4. Using the DJI Osmo Pocket 3

Not tested yet.

1. Connect it by USB‑C (data cable, not charge-only) and choose webcam mode on its screen.
2. List the camera numbers. Run it once without and once with the Pocket 3 connected; the new
   number is the Pocket 3 (laptops often already have cameras 0 and 1):

   ```
   python main.py --list-cameras
   ```

3. Start with that number, for example:

   ```
   python main.py --source 2
   ```

The 1080p video is scaled down automatically for speed.

---

## 5. Controls and settings

### 5.1 Keys (in the video window)

| Key | Action |
|---|---|
| `H` | Finger counting on/off |
| `Q` / `Esc` | Quit (closing the window or pressing Ctrl+C in the terminal also works) |

The bottom bar also lists `F`, `G`, `P`, `C` and `D`. These belong to the postponed features
([Section 11](#11-future-work)) and can be ignored for now.

### 5.2 Command-line options

| Option | Meaning |
|---|---|
| `--source 1` | Camera number, or a stream URL such as `http://192.168.1.15:81/stream` |
| `--rotate 180` | Turn the picture clockwise by `0`, `90`, `180` or `270` degrees |
| `--list-cameras` | List the available camera numbers and exit |
| `--config file.json` | Use a different settings file |

### 5.3 Settings (`config.json`)

| Setting | Default | Meaning |
|---|---|---|
| `camera.source` | `0` | Camera number (`0`, `1`, …) or stream URL in quotes |
| `camera.rotate` | `0` | Turn the picture clockwise: `0`, `90`, `180`, `270` (`180` for the ESP32-CAM) |
| `camera.mirror` | `true` | Mirror view. Keep `true`: the Left/Right hand labels depend on it. |
| `camera.width` / `height` | `1280` / `720` | Resolution requested from a webcam (it may give a different one) |
| `camera.backend` | `"auto"` | `"auto"`, `"dshow"` or `"msmf"`; try `"dshow"` if a webcam opens slowly or shows black |
| `display.width` | `960` | Window width; larger pictures are shrunk |
| `processing.width` | `640` | Picture width used for detection; smaller = faster |
| `features.fingers` | `true` | Finger counting on at start |
| `features.face` / `gestures` / `posture` | `false` | Postponed features, off |

Command-line options override `config.json`. The other sections (`popups`, `face`, `gestures`,
`posture`) are for the postponed features.

---

## 6. How finger counting works

MediaPipe finds **21 points** on each hand: the wrist, knuckles, joints and fingertips. Picture
coordinates grow downward (y) and to the right (x).

```
            8   12  16  20      ← fingertips
            |   |   |   |
            7   11  15  19
   4        |   |   |   |
   |        6   10  14  18      ← middle knuckles (PIP)
   3 (IP)   |   |   |   |
   |        5---9---13--17      ← base knuckles
   2         \           /
    \         \         /
     1--------- 0 (WRIST)
  THUMB  INDEX MIDDLE RING PINKY
```

- **Index to pinky:** a finger is up if its tip is higher than its middle knuckle:
  `tip.y < pip.y`.
- **Thumb:** it bends sideways, so the tip (4) and the joint below it (3) are compared
  horizontally. The direction is reversed for Left and Right hands.
- **Left/Right:** MediaPipe decides which hand it is; the picture is mirrored first so the labels
  match your real hands.
- **Each frame:** camera picture → rotate (if set) → mirror → shrink to 640 px wide → hand model →
  count → draw on screen.

**Limitations**

- The hand should be upright with the palm facing the camera. A sideways hand or the back of the
  hand can be miscounted.
- A thumb folded across the palm can sometimes be counted as up.
- With the ESP32-CAM, the count only updates when a new picture arrives
  ([Section 7](#7-known-issue-esp32-cam-connection)).

---

## 7. Known issue: ESP32-CAM connection

**Status: accepted for the current stage.**

The ESP32-CAM's Wi‑Fi link to the router is weak. The laptop's own Wi‑Fi was fine (1 ms to the
router), but the board measured:

| Measurement | ESP32-CAM | Good connection |
|---|---|---|
| Ping | ~130–410 ms, 5–10% packets lost | under 30 ms, no loss |
| Video | a few pictures per second or less | 10–20 pictures per second |

**Effect:** the video can be slow or freeze for a moment. The program keeps the last picture on
screen, shows "Camera slow" or "Connection lost – reconnecting", and reconnects by itself. Finger
counting continues as soon as new pictures arrive.

**How to improve it (in order of effect):**

1. Move the board closer to the router, with nothing metal in between. Its built-in antenna is
   small.
2. Give it stable power (a short cable, a different USB port, or a 5 V / 2 A charger).
3. Keep the resolution low (QVGA or VGA) on the board's web page.
4. Close any browser tab showing the stream while the program runs.

---

## 8. Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'cv2'` | Virtual environment not active | `.\myenv\Scripts\activate`, or run `.\myenv\Scripts\python.exe main.py` |
| ESP32 not in the Arduino IDE / no CameraWebServer example | ESP32 board package missing, or no ESP32 board selected | [Section 3.1](#31-one-time-install-esp32-support-in-the-arduino-ide), then select **AI Thinker ESP32-CAM** |
| ESP32 picture upside down | The AI Thinker camera is mounted rotated | Add `--rotate 180` (or `"rotate": 180` in `config.json`) |
| "Waiting for camera…" with the ESP32 | Board offline, wrong address, or a browser tab is using the stream | Check the Serial Monitor for the address, close the browser tab, and ping the board |
| "Camera slow" / "Connection lost – reconnecting" | Weak ESP32 Wi‑Fi | [Section 7](#7-known-issue-esp32-cam-connection) |
| `Destination host unreachable` when pinging the board | The board is not on the network (restarted, lost power or out of range) | Press RST and check the Serial Monitor; the address may have changed |
| `Brownout detector was triggered` in the Serial Monitor | Not enough power for the board | Another USB port, a short cable, or a 5 V / 2 A charger |
| Wrong count | Hand sideways or back of hand to the camera | Hold the hand upright, palm to the camera |

**Checking the ESP32 connection:**

```
ping 192.168.1.15
```

- Good: `Reply from 192.168.1.15: ... time=8ms`, with replies coming **from the board's own
  address** in under ~30 ms.
- Bad: times in the hundreds of ms, `Request timed out`, or `Reply from <laptop address>:
  Destination host unreachable` (the laptop saying it can't find the board). Windows still counts
  these as "Received", so ignore that number.

---

## 9. Requirements

### 9.1 Software

| Item | Version | Purpose |
|---|---|---|
| Python | 3.13 | Runtime |
| `mediapipe` | 1.0.1 | Hand model (and the postponed features' models) |
| `opencv-python` | 5.0.0 | Camera, drawing, windows, picture decoding |
| `Pillow` | 12.3.0 | Only needed for the postponed pop-up feature |
| `numpy` | comes with mediapipe | Image arrays |
| Arduino IDE + ESP32 board package | 2.x / "esp32 by Espressif Systems" | Uploading the camera program to the ESP32-CAM |

The Python libraries are listed in `requirements.txt`.

### 9.2 Model file

Finger counting needs only `models/hand_landmarker.task` (7.5 MB, included). If it goes missing,
download it into `models/` from:
https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task

### 9.3 Hardware

| Device | Requirement |
|---|---|
| Laptop webcam | None |
| **ESP32-CAM** (AI Thinker) | ESP32-CAM-MB programmer board or USB-to-serial adapter (for uploading); 2.4 GHz Wi‑Fi on the same router as the laptop; stable 5 V power |
| DJI Osmo Pocket 3 (optional) | USB‑C data cable; webcam mode on the Pocket 3 |

---

## 10. Project structure

```
IoT-Assignment-1/
├── main.py                 # main program: camera loop, keys, on-screen info
├── camera.py               # webcam / Pocket 3 / ESP32 stream reader (auto-reconnect)
├── config.json             # settings (camera, rotation, which features are on)
├── modules/
│   ├── base.py             # shared shape every feature follows
│   ├── fingers.py          # ✅ finger counting (current scope)
│   ├── face.py             # ⏸️ expressions + head direction (later)
│   ├── gestures.py         # ⏸️ hand gestures (later)
│   └── posture.py          # ⏸️ posture matching (later)
├── popup.py                # ⏸️ GIF/photo pop-ups (later)
├── models/
│   ├── hand_landmarker.task         # ✅ used for finger counting
│   ├── face_landmarker.task         # ⏸️ later
│   ├── gesture_recognizer.task      # ⏸️ later
│   └── pose_landmarker_full.task    # ⏸️ later
├── media/                  # ⏸️ GIFs/photos for pop-ups (later; see media/README.txt)
├── Finger_count.py         # original standalone finger counter (webcam only)
├── requirements.txt
└── README.md
```

Created locally and not in the repository: `myenv/` (virtual environment) and `cache/`
(created by posture matching).

---

## 11. Future work

Face expressions, head direction, hand gestures, posture matching and GIF/photo pop-ups are
already written and were tested on sample photos, but have **not been tested live**. They are
postponed and switched off in `config.json`.

| Feature | What it will do | Key |
|---|---|---|
| **Face expressions** | Detect smile, surprise, wink, kiss, angry, sad | `F` |
| **Head direction** | Detect look left/right/up/down and tilt left/right | `F` |
| **Hand gestures** | Detect 👍 👎 ✌️ ✊ 🖐 ☝️ 🤟 | `G` |
| **Posture matching** | Match your body pose to photos in `media/postures/`; `C` captures a new one | `P`, `C` |
| **Pop-ups** | Show a matching GIF/photo from `media/` when any of the above is held for 0.5 s | – |
| **Debug view** | Show raw scores and angles for tuning | `D` |

**To try them:** press the key while the program runs, or set the feature to `true` under
`features` in `config.json`.

**What is still needed to finish them:**

1. **GIFs/photos** in the `media/` folders (`media/README.txt` lists every folder). Without them,
   a text card such as "SMILE – add files to media/expressions/smile/" pops up instead. The six
   expression folders already have one image each.
2. **Posture photos** in `media/postures/`, or captured with `C`.
3. **Live testing and tuning** with a real person. Press `D` to see the live values, and adjust the
   thresholds in `config.json` (`face.thresholds`, `face.head`, `gestures.min_score`,
   `posture.match_threshold`).
4. A **better ESP32 connection**, or the webcam / Pocket 3. Expressions and gestures need a
   steady stream of pictures to feel responsive.

**Sample-photo test results so far:** smile detected on a portrait; head tilt direction correct;
thumbs up 74%, victory 77%, fist 90%; a yoga pose matched itself 100% and a different pose only
63%. Pop-ups appeared after the hold time and GIFs animated correctly. With all features on, the
program ran at ~16 frames per second on the development laptop.

---

## 12. Notes

**MediaPipe version.** The original tutorial uses `mediapipe==0.10.11` and the older
`mp.solutions.hands` API. That version does not support Python 3.13, and newer MediaPipe releases
removed `mp.solutions`. This project therefore uses the current **Tasks API** (`HandLandmarker`),
which loads the `hand_landmarker.task` model file. The 21 hand points and the finger-counting
logic are the same as in the tutorial.

**Original program.** `Finger_count.py` is the first, standalone version (webcam only). It still
works: `python Finger_count.py` (press **q** to quit).
