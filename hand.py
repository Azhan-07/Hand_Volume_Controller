import cv2
import mediapipe as mp
import math
import time
import sys
import subprocess

# --- Platform volume control backends ---
PLATFORM = sys.platform

# Default: per-app (browser) volume is Windows-only; other OSes fall back to prints.
def set_browser_volume(percent):
    print(f"browser volume -> {percent:.1f}%  [per-app volume only supported on Windows]")


def set_browser_mute(muted):
    print(f"browser mute -> {'ON' if muted else 'OFF'}  [per-app volume only supported on Windows]")


if PLATFORM.startswith("win"):

    _vol = None
    try:
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        _devices = AudioUtilities.GetSpeakers()
        _interface = _devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        _vol = cast(_interface, POINTER(IAudioEndpointVolume))

    except Exception as e:
        print("pycaw unavailable, volume control disabled:", e)

    def set_volume(percent):
        percent = max(0.0, min(100.0, float(percent)))
        if _vol is not None:
            try:
                _vol.SetMasterVolumeLevelScalar(percent / 100.0, None)
            except Exception as e:
                print("set_volume failed:", e)
        else:
            print(f"volume -> {percent:.1f}%  [pycaw unavailable]")

    def set_mute(muted):
        if _vol is not None:
            try:
                _vol.SetMute(1 if muted else 0, None)
            except Exception as e:
                print("set_mute failed:", e)
        else:
            print(f"mute -> {'ON' if muted else 'OFF'}  [pycaw unavailable]")

    # --- Per-app (browser) volume via Windows Volume Mixer ---
    BROWSER_PROCESSES = ("chrome.exe", "msedge.exe", "firefox.exe",
                         "brave.exe", "opera.exe", "vivaldi.exe")

    _browser = None
    _browser_scan_time = 0.0
    _no_session_warn = 0.0

    def get_browser_session():
        """Best browser audio session; prefers one currently playing audio."""
        global _browser, _browser_scan_time
        now = time.time()
        if now - _browser_scan_time < 1.0:
            return _browser
        _browser_scan_time = now
        try:
            sessions = AudioUtilities.GetAllSessions()
            fallback = None
            for s in sessions:
                if s.Process is None:
                    continue
                if s.Process.name().lower() in BROWSER_PROCESSES:
                    if s.State == 1:  # AudioSessionStateActive — making sound now
                        _browser = s
                        return _browser
                    if fallback is None:
                        fallback = s
            _browser = fallback
        except Exception as e:
            print("browser session scan failed:", e)
            _browser = None
        return _browser

    def _reset_browser_scan():
        global _browser, _browser_scan_time
        _browser = None
        _browser_scan_time = 0.0

    def set_browser_volume(percent):
        global _no_session_warn
        percent = max(0.0, min(100.0, float(percent)))
        if _vol is None:
            return
        sess = get_browser_session()
        if sess is None:
            now = time.time()
            if now - _no_session_warn > 2.0:
                _no_session_warn = now
                print("browser volume -> %.1f%%  [no browser playing; "
                      "start audio in a browser first]" % percent)
            return
        try:
            sess.SetMasterVolume(percent / 100.0, None)
        except Exception as e:
            print("browser volume failed:", e)
            _reset_browser_scan()

    def set_browser_mute(muted):
        global _no_session_warn
        if _vol is None:
            return
        sess = get_browser_session()
        if sess is None:
            now = time.time()
            if now - _no_session_warn > 2.0:
                _no_session_warn = now
                print("browser mute -> %s  [no browser playing; "
                      "start audio in a browser first]" % ("ON" if muted else "OFF"))
            return
        try:
            sess.SetMute(1 if muted else 0, None)
        except Exception as e:
            print("browser mute failed:", e)
            _reset_browser_scan()

elif PLATFORM == "darwin":  # macOS

    def set_volume(percent):
        percent = int(max(0.0, min(100.0, percent)))
        subprocess.call(["osascript", "-e", f"set volume output volume {percent}"])

    def set_mute(muted):
        subprocess.call(["osascript", "-e", f"set volume output muted {'true' if muted else 'false'}"])

elif PLATFORM.startswith("linux"):

    def set_volume(percent):
        percent = int(max(0, min(100, percent)))
        subprocess.call(["amixer", "sset", "Master", f"{percent}%"])

    def set_mute(muted):
        subprocess.call(["amixer", "sset", "Master", "mute" if muted else "unmute"])

else:

    def set_volume(percent):
        print(f"volume -> {percent:.1f}%  [Unsupported OS]")

    def set_mute(muted):
        print(f"mute -> {'ON' if muted else 'OFF'}  [Unsupported OS]")


# --- Volume target dispatch: system-wide or the browser tab that's playing ---
volume_target = "system"  # "system" (master) or "browser" (per-app, Windows)


def set_target_volume(percent):
    if volume_target == "browser":
        set_browser_volume(percent)
    else:
        set_volume(percent)


def set_target_mute(muted):
    if volume_target == "browser":
        set_browser_mute(muted)
    else:
        set_mute(muted)


mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.6
)


# --- Helper functions ---

def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def angle_between(a, b, c):
    """Angle (degrees) at point b between segments a-b and b-c, rotation-invariant."""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    denom = math.hypot(*v1) * math.hypot(*v2)
    if denom == 0:
        return 0.0
    cos = (v1[0] * v2[0] + v1[1] * v2[1]) / denom
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def fingers_up(landmarks):
    """
    Returns list of 5 booleans: thumb → pinky indicating if each finger is up.
    Uses joint angles (MediaPipe IDs: MCP, PIP, TIP) so it works from any
    camera angle instead of assuming a vertical hand.
    """
    coords = [(l.x, l.y) for l in landmarks]  # normalized 0-1 coords
    # Thumb: angle at IP (3) between MCP (2) and TIP (4)
    up = [angle_between(coords[2], coords[3], coords[4]) < 160]
    # Others: angle at PIP between MCP and TIP
    for mcp, pip, tip in ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)):
        up.append(angle_between(coords[mcp], coords[pip], coords[tip]) < 160)
    return up


def classify_gesture(up):
    counts = sum(up)
    if counts == 0:
        return "fist"
    if counts == 5:
        return "flat"
    # V sign: index + middle up, ring + pinky down (thumb state ignored)
    if up[1] and up[2] and not up[3] and not up[4]:
        return "v"
    # Shaka: thumb + pinky up, others down — switches volume target
    if up[0] and up[4] and not up[1] and not up[2] and not up[3]:
        return "shaka"
    return "unknown"


def map_distance_to_volume(dist, min_d=20, max_d=220):
    d = max(min_d, min(max_d, dist))
    return (d - min_d) / (max_d - min_d) * 100.0


class HoldSwitch:
    """Fires once after a gesture is sustained for `hold_time`, then requires a
    release before it can fire again (prevents holding it when you release)."""

    def __init__(self, hold_time):
        self.hold_time = hold_time
        self.start = None
        self.primed = False

    def update(self, active):
        now = time.time()
        if not active:
            self.start = None
            self.primed = False
            return False
        if self.start is None:
            self.start = now
            return False
        if not self.primed and now - self.start >= self.hold_time:
            self.primed = True
            return True
        return False


# --- Main loop ---
cap = cv2.VideoCapture(0)
p_time = 0
vol_smooth = 0.0
smoothing = 0.7
in_volume_mode = False
muted = False
toggle_switch = HoldSwitch(0.6)
mute_switch = HoldSwitch(0.3)
target_switch = HoldSwitch(0.6)


try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Can't read camera. Exiting.")
            break

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)

        if result.multi_hand_landmarks:
            lm = result.multi_hand_landmarks[0].landmark
            mp_drawing.draw_landmarks(frame, result.multi_hand_landmarks[0], mp_hands.HAND_CONNECTIONS)

            up = fingers_up(lm)
            gesture = classify_gesture(up)

            # Fist (hold 0.6s) toggles volume mode — distinct from flat hand, so
            # toggling on doesn't immediately grab that same hand's volume.
            if toggle_switch.update(gesture == "fist"):
                in_volume_mode = not in_volume_mode

            # Shaka (thumb + pinky, hold 0.6s) switches the pinch target between
            # the system master volume and the browser tab that is playing audio.
            if target_switch.update(gesture == "shaka"):
                volume_target = "system" if volume_target == "browser" else "browser"
                print(f"volume target -> {volume_target}")

            # V sign toggles mute on the active target, in any mode.
            if mute_switch.update(gesture == "v"):
                muted = not muted
                set_target_mute(muted)

            thumb_tip = (int(lm[4].x * w), int(lm[4].y * h))
            index_tip = (int(lm[8].x * w), int(lm[8].y * h))
            d = distance(thumb_tip, index_tip)

            state_color = (0, 255, 0) if in_volume_mode else (0, 0, 255)
            cv2.putText(frame, f"Mode: {'VOLUME' if in_volume_mode else 'IDLE'} | Target: {volume_target}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, state_color, 2)

            # Volume control is gated so control gestures never yank the volume
            # (e.g. closing a fist to exit mode won't drop it to 0%).
            if in_volume_mode and gesture not in ("fist", "v", "shaka"):
                target_vol = map_distance_to_volume(d)
                vol_smooth = vol_smooth * smoothing + target_vol * (1 - smoothing)
                set_target_volume(vol_smooth)

                cv2.line(frame, thumb_tip, index_tip, (255, 0, 255), 3)
                cv2.circle(frame, thumb_tip, 8, (0, 255, 0), cv2.FILLED)
                cv2.circle(frame, index_tip, 8, (0, 255, 0), cv2.FILLED)

            mute_color = (0, 0, 255) if muted else (255, 255, 0)
            cv2.putText(frame, f"Vol: {vol_smooth:3.0f}%  Mute: {'ON' if muted else 'OFF'}",
                        (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, mute_color, 2)
            cv2.putText(frame, "FIST(hold): mode | SHAKA(hold): sys/browser | V: mute | pinch: volume",
                        (10, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 2)

        # FPS
        c_time = time.time()
        fps = 1 / (c_time - p_time) if c_time != p_time else 0
        p_time = c_time
        cv2.putText(frame, f"FPS: {int(fps)}", (10, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        cv2.imshow("Volume Card Gesture", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break

finally:
    cap.release()
    cv2.destroyAllWindows()