"""
scripts/test_camera.py — Phase 1C camera smoke test.

Starts the camera, runs for a few seconds, prints stats (requested vs actual
resolution and measured FPS), then saves one sample frame to data/ so it can be
copied off the Pi and eyeballed.

Run from the project root with the venv active:
    python scripts/test_camera.py
"""

import sys
import time
from pathlib import Path

# Allow running as a script from the repo root by making project modules importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402

import config  # noqa: E402
from vision.camera import Camera  # noqa: E402


def main():
    print(
        f"Opening camera {config.CAMERA_DEVICE} at "
        f"{config.CAMERA_WIDTH}x{config.CAMERA_HEIGHT}, {config.CAMERA_FPS}fps ..."
    )
    with Camera() as cam:
        w, h = cam.actual_resolution()
        print(f"Actual resolution: {w}x{h}")

        seconds = 5
        print(f"Capturing for {seconds}s to measure throughput ...")
        start = time.time()
        start_count = cam.frame_count
        time.sleep(seconds)
        captured = cam.frame_count - start_count
        elapsed = time.time() - start
        print(
            f"Frames captured: {captured} in {elapsed:.1f}s "
            f"= {captured / elapsed:.1f} FPS"
        )

        frame = cam.read()
        if frame is None:
            print("ERROR: no frame available to save")
            return
        out = config.DATA_DIR / "camera_test.jpg"
        cv2.imwrite(str(out), frame)
        print(f"Sample frame saved to {out}")


if __name__ == "__main__":
    main()
