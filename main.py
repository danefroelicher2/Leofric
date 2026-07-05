"""
Leofric — entry point.

This is the always-on process that will eventually start every subsystem:
camera, motion, person, identity, audio, wake word, transcription, and the
brain client. Right now it is a skeleton. Subsystems are added one phase at a
time and this file grows with each; full integration happens in Phase 1K.

Run on the Pi with:  python main.py
"""

import config


def main() -> None:
    print(f"Leofric node '{config.NODE_ID}' starting up.")
    print(f"  Camera device : {config.CAMERA_DEVICE}")
    print(f"  Mic card      : {config.MIC_CARD}")
    print(f"  Brain (Mac)   : {config.MAC_MINI_URL}")
    print("No subsystems wired yet — skeleton only. See docs/ROADMAP.md.")


if __name__ == "__main__":
    main()
