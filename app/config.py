"""
Configuration — all paths and settings in one place.
Adjust paths here if you move models or tools.
"""
import os

BASE_DIR = r"E:\TESTING"

# ── Model paths ──────────────────────────────────────────────
WHISPER_MODEL   = os.path.join(BASE_DIR, "models", "whisper", "ggml-large-v3-turbo.bin")
WHISPER_CLI     = os.path.join(BASE_DIR, "tools", "whisper", "Release", "whisper-cli.exe")

PYANNOTE_MODEL  = os.path.join(BASE_DIR, "models", "pyannote", "community-1")

QWEN_MODEL      = os.path.join(BASE_DIR, "models", "qwen", "qwen3.5-0.8b-Q4_K_M.gguf")
LLAMA_SERVER    = r"C:\Users\HP\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe"

# ── Working directories ──────────────────────────────────────
AUDIO_INPUT     = os.path.join(BASE_DIR, "audio", "input")
AUDIO_PROCESSED = os.path.join(BASE_DIR, "audio", "processed")
TRANSCRIPTS_DIR = os.path.join(BASE_DIR, "transcripts")
RESULTS_DIR     = os.path.join(BASE_DIR, "results")
DB_PATH         = os.path.join(BASE_DIR, "meeting_intelligence.db")

# ── LLM server settings ─────────────────────────────────────
LLM_HOST = "127.0.0.1"
LLM_PORT = 8081          # avoids conflict with the web app on 8000

# ── Whisper settings ─────────────────────────────────────────
WHISPER_LANGUAGE = "auto"       # auto-detect Hindi/English
WHISPER_THREADS  = 4

# ── Pipeline settings ────────────────────────────────────────
MAX_SPEAKERS     = 15           # upper bound hint for diarization
CHUNK_MINUTES    = 15           # split long audio into chunks

# Ensure directories exist
for d in [AUDIO_INPUT, AUDIO_PROCESSED, TRANSCRIPTS_DIR, RESULTS_DIR]:
    os.makedirs(d, exist_ok=True)
