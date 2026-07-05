"""
macmini/server.py — Leofric's brain API (runs on the Mac Mini).

A small Flask server that fronts Ollama. The Pi POSTs transcribed speech here;
this forwards it to a local Ollama model (Llama 3.2) with Leofric's persona plus
the recent conversation, and returns the model's text reply. Heavy inference stays
on the Mac; the Pi stays light.

Run on the Mac Mini (see macmini/README.md):
    python3 server.py
Binds 0.0.0.0:5000 so the Pi on the LAN can reach it.
"""

import os

import requests
from flask import Flask, jsonify, request

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.getenv("LEOFRIC_MODEL", "llama3.2")

SYSTEM_PROMPT = (
    "You are Leofric, a local home intelligence system running on the builder's "
    "own hardware. You watch and listen through sensors and answer through text. "
    "You are concise, calm, and direct. Keep replies short unless asked for detail."
)

app = Flask(__name__)


@app.get("/")
def health():
    return jsonify(status="ok", service="leofric-brain", model=MODEL)


@app.post("/chat")
def chat():
    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip()
    history = data.get("history") or []  # list of {"role", "content"}
    if not message:
        return jsonify(error="missing 'message'"), 400

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "messages": messages, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        reply = resp.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        return jsonify(error=f"ollama request failed: {e}"), 502

    return jsonify(response=reply)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
