"""
scripts/fetch_models.py — download the pretrained model files Leofric needs.

Model weights are not committed to git (binary and large); this script fetches
them into data/models/. Safe to re-run — it skips files already present. Run once
on the Pi after cloning:
    python scripts/fetch_models.py
"""

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

MODELS = {
    "MobileNetSSD_deploy.prototxt": (
        "https://raw.githubusercontent.com/djmv/MobilNet_SSD_opencv/master/"
        "MobileNetSSD_deploy.prototxt"
    ),
    "MobileNetSSD_deploy.caffemodel": (
        "https://raw.githubusercontent.com/djmv/MobilNet_SSD_opencv/master/"
        "MobileNetSSD_deploy.caffemodel"
    ),
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx"
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx"
    ),
}


def main():
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in MODELS.items():
        dest = config.MODELS_DIR / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"[skip] {name} already present ({dest.stat().st_size:,} bytes)")
            continue
        print(f"[..] downloading {name} ...")
        urllib.request.urlretrieve(url, dest)
        print(f"[ok]  {name} -> {dest} ({dest.stat().st_size:,} bytes)")
    print("Done. Models are in", config.MODELS_DIR)


if __name__ == "__main__":
    main()
