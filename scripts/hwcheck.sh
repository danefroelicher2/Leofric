#!/usr/bin/env bash
# Leofric Phase 1A — Hardware Verification
# Confirms the webcam and ReSpeaker are present and can actually capture.
set -u

FRAME="$HOME/hwcheck_frame.jpg"
AUDIO="$HOME/hwcheck_audio.wav"
CAM_DEV="/dev/video0"
MIC_CARD=2            # ReSpeaker 4 Mic Array, from 'arecord -l'

echo "=== 1A HARDWARE VERIFICATION ==="

if [ -e "$CAM_DEV" ]; then
  echo "[PASS] Camera device $CAM_DEV exists"
else
  echo "[FAIL] Camera device $CAM_DEV missing"; exit 1
fi

if arecord -l | grep -q "card ${MIC_CARD}:"; then
  echo "[PASS] Mic capture device card ${MIC_CARD} exists"
else
  echo "[FAIL] Mic capture card ${MIC_CARD} missing"; exit 1
fi

if ! command -v fswebcam >/dev/null 2>&1; then
  echo "[..] Installing fswebcam (enter your sudo password if asked)..."
  sudo apt update && sudo apt install -y fswebcam
fi

echo "[..] Capturing test frame from $CAM_DEV ..."
if fswebcam -d "$CAM_DEV" -r 1280x720 --no-banner "$FRAME" 2>/dev/null && [ -s "$FRAME" ]; then
  echo "[PASS] Frame saved: $FRAME ($(du -h "$FRAME" | cut -f1))"
else
  echo "[FAIL] Frame capture failed on $CAM_DEV"
fi

echo "[..] Recording 3s from card ${MIC_CARD} — SPEAK NOW..."
if arecord -D "plughw:${MIC_CARD},0" -c 1 -r 16000 -f S16_LE -d 3 "$AUDIO" 2>/dev/null && [ -s "$AUDIO" ]; then
  echo "[PASS] Audio saved: $AUDIO ($(du -h "$AUDIO" | cut -f1))"
else
  echo "[FAIL] Audio record failed on card ${MIC_CARD}"
fi

echo "=== DONE ==="
