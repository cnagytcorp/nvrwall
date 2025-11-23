import cv2
import numpy as np
import threading
import time

# ---- NVR CONFIG (temp hard-coded; later we can move to a config file) ----
HOST = "192.168.1.7"
USER = "admin"
PASSWORD = "647382911"
PORT = 554
CHANNELS = [1, 2, 3, 4]

# 0 = main stream, 1 = substream
STREAM_ID = 0


def make_url(channel, stream=STREAM_ID):
    return (
        f"rtsp://{HOST}:{PORT}/user={USER}&password={PASSWORD}"
        f"&channel={channel}&stream={stream}.sdp"
    )


latest_frames = {ch: None for ch in CHANNELS}
status = {ch: "idle" for ch in CHANNELS}
_lock = threading.Lock()
_started = False


def _camera_worker(channel: int):
    """Background thread: keep pulling frames from one camera with auto-reconnect."""
    url = make_url(channel)

    while True:
        status[channel] = "connecting"
        cap = cv2.VideoCapture(url)

        if not cap.isOpened():
            status[channel] = "failed to open"
            cap.release()
            time.sleep(2)
            continue

        status[channel] = "online"

        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                status[channel] = "lost signal"
                break

            with _lock:
                latest_frames[channel] = frame

        cap.release()
        time.sleep(2)  # reconnect delay


def init_nvr():
    """Start camera threads once."""
    global _started
    if _started:
        return

    for ch in CHANNELS:
        t = threading.Thread(
            target=_camera_worker,
            args=(ch,),
            daemon=True,
        )
        t.start()

    _started = True


def _draw_placeholder(channel: int, text: str, width: int, height: int) -> np.ndarray:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.putText(
        frame,
        f"CH{channel} - {text}",
        (40, height // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 0, 255),
        2,
        cv2.LINE_AA,
    )
    return frame


def get_grid_frame() -> np.ndarray:
    """
    Build a 2x2 grid frame from the latest frames.
    Always returns a valid image (uses placeholders if needed).
    """
    with _lock:
        # find first real frame to define target size
        target_w = target_h = None
        for ch in CHANNELS:
            f = latest_frames[ch]
            if f is not None:
                target_h, target_w = f.shape[:2]
                break

        if target_w is None or target_h is None:
            target_w, target_h = 640, 360

        frames = []
        for ch in CHANNELS:
            frame = latest_frames[ch]
            st = status[ch]

            if frame is None:
                frame = _draw_placeholder(ch, st, target_w, target_h)
            else:
                h, w = frame.shape[:2]
                if h != target_h or w != target_w:
                    frame = cv2.resize(
                        frame,
                        (target_w, target_h),
                        interpolation=cv2.INTER_AREA,
                    )

                cv2.putText(
                    frame,
                    f"CH{ch} ({st})",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )

            frames.append(frame)

    top = np.hstack((frames[0], frames[1]))
    bottom = np.hstack((frames[2], frames[3]))
    grid = np.vstack((top, bottom))
    return grid
