# Finger Detection and Counting (MediaPipe + OpenCV + ESP32-CAM)

Real-time hand tracking and finger counting. The program finds up to two hands in a camera image,
draws the hand skeleton, and shows how many fingers are raised on each hand (0–5), with a
Left/Right label. The camera can be the laptop webcam, an **ESP32-CAM** over Wi‑Fi, or a DJI
Osmo Pocket 3 over USB.

Finger counting is the current project scope. Face expressions, head direction, hand gestures and
posture matching are already in the code but postponed to a later stage
(see [Section 7](#7-future-work-postponed-features)).

---

## 1. Project status

### ✅ Current scope: finger counting

| Part | Status |
|---|---|
| **Finger counting** (0–5 per hand, up to 2 hands, Left/Right) | ✅ Works |
| **Laptop webcam** | ✅ Works |
| **ESP32-CAM over Wi‑Fi** | ✅ Works, with a weak connection (see below) |
| **Upside-down ESP32 picture** | ✅ Fixed with `--rotate 180` |
| **Camera choice** (`--source`, `config.json`) and camera finder (`--list-cameras`) | ✅ Works |
| **On-screen info:** frames per second, camera name, key bar | ✅ Works |
| **DJI Osmo Pocket 3** | Supported in the code, not tested yet |

### ⚠️ Known issue: ESP32-CAM connection (accepted)

The ESP32-CAM's Wi‑Fi link to the router is weak. The laptop's own Wi‑Fi is fine (1 ms to the
router), but the board measured:

| Measurement | ESP32-CAM | Good connection |
|---|---|---|
| Ping | ~130–410 ms, 5–10% packets lost | under 30 ms, no loss |
| Video | a few pictures per second or less | 10–20 pictures per second |

**Effect:** the video can be slow or freeze for a moment. The app keeps the last picture on
screen, shows "Camera slow" or "Connection lost – reconnecting", and reconnects by itself. Finger
counting continues as soon as new pictures arrive. This is acceptable for the current stage; ways
to improve it are in [Section 6](#6-troubleshooting).

### ⏸️ Postponed (built, finished later)

Face expressions, head direction, hand gestures, posture matching and GIF/photo pop-ups. They
are switched off by default. See [Section 7](#7-future-work-postponed-features).

### ❌ Not possible / not included

| Item | Reason |
|---|---|
| Running the detection on the ESP32 itself | The ESP32 has far too little memory for Python or MediaPipe. It only acts as the camera; the laptop does the detection. |
| Recognizing **who** a person is | Not part of this project; MediaPipe does not do identity recognition. |

---

## 2. Project structure

```
IoT Mini Project/
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
├── cache/                  # ⏸️ created automatically by posture matching
├── Finger_count.py         # original standalone finger counter (webcam only)
├── requirements.txt
├── README.md
└── myenv/                  # virtual environment
```

---

## 3. Requirements

### 3.1 Software (installed in `myenv`)

| Item | Version | Purpose |
|---|---|---|
| Python | 3.13 | Runtime |
| `mediapipe` | 1.0.1 | Hand model (and the later features' models) |
| `opencv-python` | 5.0.0 | Camera, drawing, windows, picture decoding |
| `Pillow` | 12.3.0 | Only needed for the later pop-up feature |
| `numpy` | comes with mediapipe | Image arrays |
| Arduino IDE + ESP32 board package | 2.x / "esp32 by Espressif Systems" | Uploading the camera program to the ESP32-CAM |

### 3.2 Model file

Finger counting needs only `models/hand_landmarker.task` (7.5 MB, already downloaded). If it goes
missing, download it into `models/` from:
https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task

### 3.3 Hardware

| Device | Requirement |
|---|---|
| Laptop webcam | None |
| **ESP32-CAM** (AI Thinker) | ESP32-CAM-MB programmer board or USB-to-serial adapter (for uploading); 2.4 GHz Wi‑Fi on the same router as the laptop; stable 5 V power |
| DJI Osmo Pocket 3 (optional) | USB‑C data cable; webcam mode on the Pocket 3 |

---

## 4. How to run

### 4.1 First-time setup (Windows, PowerShell)

Already done in this folder. Only repeat on a new computer.

```
python -m venv myenv
```

```
.\myenv\Scripts\activate
```

```
pip install -r requirements.txt
```

### 4.2 Run with the laptop webcam

Activate the virtual environment (the prompt should start with `(myenv)`):

```
.\myenv\Scripts\activate
```

Start:

```
python main.py
```

Hold your hand(s) up with the palm facing the camera. The count appears at the top-left
(`Right: 3`, `Left: 5`).

| Key | Action |
|---|---|
| `H` | Finger counting on/off |
| `Q` / `Esc` | Quit (closing the window or pressing Ctrl+C in the terminal also works) |

The bottom bar also lists `F`, `G`, `P`, `C` and `D`. These belong to the postponed features
([Section 7](#7-future-work-postponed-features)) and can be ignored for now.

A few `INFO` / `WARNING` lines from MediaPipe at start-up are normal.

### 4.3 Run with the ESP32-CAM

**One-time: install ESP32 support in the Arduino IDE**

1. **File → Preferences → Additional boards manager URLs**, add:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
2. **Boards Manager** (left sidebar) → search **esp32** → install **"esp32 by Espressif Systems"**.

**One-time: upload the camera program**

1. **Tools → Board → esp32 → AI Thinker ESP32-CAM**.
2. **File → Examples → ESP32 → Camera → CameraWebServer**.
3. In the `board_config.h` tab, enable only `#define CAMERA_MODEL_AI_THINKER`.
4. In the main `.ino` tab, enter your Wi‑Fi name (`ssid`) and `password`. It must be a **2.4 GHz**
   network.
5. **Tools → Partition Scheme → "Huge APP (3MB No OTA/1MB SPIFFS)"**, select the COM port, and
   click **Upload**.

**Each time**

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
message.

To avoid typing the options every time, set them in `config.json`:
`"source": "http://192.168.1.15:81/stream"` and `"rotate": 180`.

### 4.4 Run with the DJI Osmo Pocket 3 (not tested yet)

1. Connect it by USB‑C and choose webcam mode on its screen.
2. Find its camera number (this laptop already has cameras 0 and 1, so it is probably 2):

   ```
   python main.py --list-cameras
   ```

3. Start with that number:

   ```
   python main.py --source 2
   ```

### 4.5 Original standalone program

The first version of the project still works with the webcam: `python Finger_count.py`
(press **q** to quit).

### 4.6 Settings (`config.json`)

| Setting | Default | Meaning |
|---|---|---|
| `camera.source` | `0` | Camera number (`0`, `1`, …) or stream URL in quotes |
| `camera.rotate` | `0` | Turn the picture clockwise: `0`, `90`, `180`, `270` (`180` for the ESP32-CAM). Same as `--rotate`. |
| `camera.mirror` | `true` | Mirror view. Keep `true`: the Left/Right hand labels depend on it. |
| `camera.width` / `height` | `1280` / `720` | Resolution requested from a webcam (it may give a different one) |
| `camera.backend` | `"auto"` | `"auto"`, `"dshow"` or `"msmf"`; try `"dshow"` if a webcam opens slowly or shows black |
| `display.width` | `960` | Window width; larger pictures are shrunk |
| `processing.width` | `640` | Picture width used for detection; smaller = faster |
| `features.fingers` | `true` | Finger counting on at start |
| `features.face` / `gestures` / `posture` | `false` | Postponed features, off |

The other sections (`popups`, `face`, `gestures`, `posture`) are for the postponed features.

---

## 5. How finger counting works

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
- **Each frame:** camera picture → mirror (and rotate for the ESP32) → shrink to 640 px wide →
  hand model → count → draw on screen.

**Limitations**

- The hand should be upright with the palm facing the camera. A sideways hand or the back of the
  hand can be miscounted.
- A thumb folded across the palm can sometimes be counted as up.
- With the ESP32-CAM, the count only updates when a new picture arrives (see the known issue in
  [Section 1](#1-project-status)).

---

## 6. Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'cv2'` | Virtual environment not active | `.\myenv\Scripts\activate`, or run `.\myenv\Scripts\python.exe main.py` |
| ESP32 picture upside down | The AI Thinker camera is mounted rotated | Add `--rotate 180` (or `"rotate": 180` in `config.json`) |
| "Waiting for camera…" with the ESP32 | Board offline, wrong address, or a browser tab is using the stream | Check the Serial Monitor for the address, close the browser tab, and ping the board |
| "Camera slow" / "Connection lost – reconnecting" | Weak ESP32 Wi‑Fi (known issue) | See below |
| `Destination host unreachable` when pinging the board | The board is not on the network (restarted, lost power or out of range) | Press RST and check the Serial Monitor; the address may have changed |
| `Brownout detector was triggered` in the Serial Monitor | Not enough power for the board | Another USB port, a short cable, or a 5 V / 2 A charger |
| Wrong count | Hand sideways or back of hand to the camera | Hold the hand upright, palm to the camera |

**Checking the ESP32 connection:**

```
ping 192.168.1.15
```

- Good: `Reply from 192.168.1.15: ... time=8ms`, with replies coming **from the board's own
  address** in under ~30 ms.
- Bad: times in the hundreds of ms, `Request timed out`, or `Reply from 192.168.1.11:
  Destination host unreachable`. `192.168.1.11` is the laptop saying it can't find the board.
  Windows still counts these as "Received", so ignore that number.

**Improving the ESP32 connection (in order of effect):**

1. Move the board closer to the router, with nothing metal in between. Its built-in antenna is
   small.
2. Give it stable power (a short cable, a different USB port, or a 5 V / 2 A charger).
3. Keep the resolution low (QVGA or VGA) on the board's web page.
4. Close any browser tab showing the stream while the program runs.

---

## 7. Future work (postponed features)

These features are already written and were tested on sample photos, but have **not been tested
live** and are postponed. They are switched off in `config.json`.

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
   a text card such as "SMILE – add files to media/expressions/smile/" pops up instead.
2. **Posture photos** in `media/postures/`, or captured with `C`.
3. **Live testing and tuning** with a real person. Press `D` to see the live values, and adjust the
   thresholds in `config.json` (`face.thresholds`, `face.head`, `gestures.min_score`,
   `posture.match_threshold`).
4. A **better ESP32 connection**, or the webcam / Pocket 3. Expressions and gestures need a
   steady stream of pictures to feel responsive.

**Sample-photo test results so far:** smile detected on a portrait; head tilt direction correct;
thumbs up 74%, victory 77%, fist 90%; a yoga pose matched itself 100% and a different pose only
63%. Pop-ups appeared after the hold time and GIFs animated correctly. With all features on, the
program ran at ~16 frames per second on this laptop.

---

## 8. Note on MediaPipe version

The original tutorial uses `mediapipe==0.10.11` and the older `mp.solutions.hands` API. That
version does not support Python 3.13, and newer MediaPipe releases removed `mp.solutions`. This
project therefore uses the current **Tasks API** (`HandLandmarker`), which loads the
`hand_landmarker.task` model file. The 21 hand points and the finger-counting logic are the same
as in the tutorial.
#   I o T - A s s i g n m e n t - 1  
 