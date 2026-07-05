# Leofric Brain (Mac Mini)

The heavy-inference half of Leofric. A small Flask API in front of Ollama
(Llama 3.2). The Pi sends transcribed speech to `POST /chat`; this returns a text
reply. Nothing leaves the LAN.

## API

- `GET /` → `{"status":"ok","service":"leofric-brain","model":"llama3.2"}`
- `POST /chat` → body `{"message": "...", "history": [{"role","content"}, ...]}`
  returns `{"response": "..."}`

## Setup (on the Mac Mini)

```bash
# 1. Install Ollama (if not already): https://ollama.com/download  (or: brew install ollama)
# 2. Pull the model:
ollama pull llama3.2
# 3. Python deps for the server:
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# 4. Run the server (Ollama must be running — `ollama serve` or the app):
python3 server.py
```

The server listens on `0.0.0.0:5000`. Point the Pi's `MAC_MINI_URL` at
`http://<mac-ip>:5000`. Give the Mac a static/reserved IP so it doesn't drift.
