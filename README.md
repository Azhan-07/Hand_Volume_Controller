# HandVolumizer 🖐️

Control your system volume with hand gestures, using nothing but your webcam.

Frame the thumb and index finger into a pinch gesture to turn the volume up and
down — no touching your keyboard or trackpad required.

## Features

- **Gesture-driven volume** — pinch your thumb and index finger to set volume from 0–100%
- **No accidental toggling** — a held **fist** switches between `IDLE` and `VOLUME` mode; the flat hand used for volume never double-fires a toggle
- **Quick mute** — flash a **V sign** to mute/unmute in any mode
- **Rotation-invariant detection** — fingers are detected via joint angles (MediaPipe landmark angles), so it works from any camera angle
- **Smooth output** — exponential moving-average smoothing prevents volume jitter
- **Cross-platform** — works on Windows, macOS, and Linux

## How it works

MediaPipe Hands produces 21 2D hand landmarks per detected hand. The app:

1. Classifies the hand state from the joint angles between landmarks,
   resolving it to one of: `flat`, `fist`, `v`, or `unknown`.
2. Maps the pixel distance between the thumb tip and index fingernail into a
   0–100% volume level.
3. Sends the result to a platform-specific `set_volume` / `set_mute` backend.

### Gesture guide

| Gesture | Action |
| --- | --- |
| 👊 **Fist** (hold ~0.6s) | Toggle between `IDLE` and `VOLUME` mode |
| ✋ **Flat hand** | Active volume posture (drawn as a pinch line) |
| 🤏 **Pinch** (thumb + index distance) | Set volume 0–100% (only in `VOLUME` mode) |
| ✌️ **V sign** (index + middle up) | Mute / unmute |
| `q` | Quit the app |

## Requirements

- Python 3.8+
- A working webcam
- **Windows only**: the [`pycaw`](https://github.com/AndreMiras/pycaw) and
  [`comtypes`](https://github.com/enthought/comtypes) packages for system-volume control

## Installation

```bash
git clone https://github.com/Azhan-07/Hand_Volume_Controller/
cd handvolumizer
python -m venv .venv

# Windows
.venv\Scripts\activate
pip install opencv-python mediapipe pycaw comtypes

# macOS / Linux
source .venv/bin/activate
pip install opencv-python mediapipe
```

> **Linux note:** the app shells out to `amixer` for the `Master` channel. If
> that fails, it prints the volume change instead rather than crashing.

## Usage

```bash
python hand.py
```

A live camera window opens. Wait for the green `VOLUME` badge, then pinch to
adjust. Press `q` to quit.

If no system backend is available, the app falls back to printing the intended
volume/mute changes to the console so the gesture logic still runs.

## Project structure

```
handvolumizer/
├── hand.py        # Single-file implementation (gesture tracking + backends)
├── requirements   # See Installation section
└── .gitignore
```

## Platform backends

| OS | Volume control |
| --- | --- |
| Windows | `pycaw` `IAudioEndpointVolume` on the default render device (system-wide) |
| macOS | `osascript` (`set volume output volume`) |
| Linux | `amixer sset Master` |
| Fallback | Prints the would-be change (feature development / unsupported OS) |

## Troubleshooting

- **"pycaw unavailable, volume control disabled"** — install `pycaw` and
  `comtypes`; the app still runs in print-fallback mode.
- **Hand not detected** — raise lighting, keep the palm facing the camera, and
  stay within ~0.5–2 m of the lens.
- **Volume jumps while using control gestures** — this is intentional: volume
  updates are suspended while a fist or V sign is recognized.

## Roadmap

- [ ] Two-hand support (one hand volume, one hand mode control)
- [ ] Gesture-based raise/lower steps for fine control
- [ ] Per-process volume targeting

## License

MIT
