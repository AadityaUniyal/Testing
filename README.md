# Offline Meeting Intelligence & Live Transcription Pipeline

An end-to-end, privacy-first, fully local meeting intelligence platform capable of live streaming transcription, speaker diarization, dynamic speaker identification, and structured action-item extraction.

Built with an architecture designed to run 100% offline on consumer hardware (NVIDIA RTX GPUs on Windows/Linux) and portable to on-device iOS applications (via WhisperKit, FluidAudio, and llama.cpp Metal).

---

## Architecture Overview

```
                                [ Audio Source ]
                     (Live Microphone Stream or Audio File)
                                       │
                                       ▼
                     [ 1. Universal Audio Ingestion ]
                     soundfile + scipy 16kHz resampler
                                       │
                ┌──────────────────────┴──────────────────────┐
                │                                             │
                ▼                                             ▼
  [ 2. Whisper Large-v3 Turbo ]               [ 3. Pyannote Diarization ]
    whisper.cpp (CUDA / CoreML)                   Community-1 (PyTorch)
  High-accuracy word timestamps               Precise multi-speaker turns
                │                                             │
                └──────────────────────┬──────────────────────┘
                                       │
                                       ▼
                      [ 4. Temporal Alignment Engine ]
                      Intersects time intervals to label
                     each spoken sentence with speaker ID
                                       │
                                       ▼
                       [ 5. LLM Intelligence Engine ]
                           Qwen 3.5 0.8B (GGUF)
                    - Dynamically maps SPEAKER_XX -> Name
                    - Executive summary & key decisions
                    - Action items with assignees & deadlines
                                       │
                ┌──────────────────────┴──────────────────────┐
                │                                             │
                ▼                                             ▼
     [ 6A. Local SQLite Store ]                    [ 6B. Supabase Sync ]
     100% offline persistence                      Cloud Postgres & RLS
```

---

## Features

- **Dynamic Speaker Resolution**: Automatically infers who is speaking from contextual conversation clues (e.g. *"Hey Tom"*, *"Thanks Sameer"*), mapping raw acoustic IDs (`SPEAKER_00`) to real human names without prior voice enrolling or hardcoding.
- **Dual Operating Modes**:
  1. **Batch Audio Ingestion**: Upload MP3, WAV, M4A, AAC, or FLAC files of any duration.
  2. **Real-time Live Audio Streaming**: Stream mic chunks over WebSockets with real-time bubble transcript updates and task detection.
- **Zero Heavy External Dependencies**: Audio ingestion is handled entirely in pure Python using `soundfile` and `scipy.signal`—no system-installed FFmpeg required.
- **Hybrid Storage & Cloud Sync**:
  - Out of the box, stores all transcripts and reports in local SQLite (`meeting_intelligence.db`).
  - Includes ready-to-deploy Supabase schema (`supabase/schema.sql`) and PostgREST sync client (`app/supabase_client.py`).
- **Modern Responsive Web UI**: Single-page frontend with live HTML5 waveform visualizer, dynamic speaker badges, real-time action items feed, and export capabilities.

---

## Repository Structure

```
├── app/
│   ├── alignment.py          # Temporal alignment between Whisper & Pyannote
│   ├── audio_utils.py        # 16kHz mono audio normalization & conversion
│   ├── config.py             # Global configuration & port definitions
│   ├── database.py           # Local SQLite storage and schema
│   ├── diarization_engine.py # Pyannote Community-1 diarization runner
│   ├── live_pipeline.py      # WebSocket real-time audio stream handler
│   ├── llm_engine.py         # Qwen 3.5 structured JSON extractor
│   ├── main.py               # FastAPI server (REST + WebSocket endpoints)
│   ├── models.py             # Pydantic schemas for meetings, tasks, speakers
│   ├── pipeline.py           # Unified orchestrator (Audio -> Whisper -> Pyannote -> LLM)
│   ├── supabase_client.py    # Hybrid cloud sync client for Supabase
│   └── whisper_engine.py     # Whisper.cpp CUDA/CPU runner
├── frontend/
│   ├── app.js                # WebSocket recorder, visualizer, UI controllers
│   ├── index.html            # Meeting Intelligence Dashboard
│   └── style.css             # Dark-themed glassmorphism interface
├── supabase/
│   └── schema.sql            # Postgres DDL schema for Supabase
├── run.py                    # Server launch script
└── requirements.txt          # Python dependencies
```

---

## Getting Started

### 1. Requirements & Prerequisites
- Python 3.10 – 3.13
- NVIDIA GPU with CUDA 12+ (optional, runs on CPU fallback)
- Windows / Linux / macOS

### 2. Setup Virtual Environment & Install Dependencies
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Setup Models
```bash
python setup_models.py
```
This prepares:
- **Whisper**: `ggml-large-v3-turbo.bin`
- **Pyannote**: `pyannote/speaker-diarization-community-1`
- **Qwen**: `qwen3.5-0.8b-Q4_K_M.gguf`

### 4. Run the Platform
```bash
# Terminal 1: Start local Qwen GGUF server
llama-server -m models/qwen/qwen3.5-0.8b-Q4_K_M.gguf --host 127.0.0.1 --port 8081 -c 8192 -ngl 99

# Terminal 2: Start Meeting Intelligence Web Server
python run.py
```

Open your browser at **http://localhost:8000** to begin recording or upload audio files.

---

## Supabase Setup (Optional Cloud Sync)

To enable automatic cloud sync:
1. Create a Supabase project at [supabase.com](https://supabase.com).
2. Run the SQL script in `supabase/schema.sql` inside your Supabase SQL Editor.
3. Set your environment variables:
```bash
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_KEY="your-anon-or-service-key"
```
The pipeline automatically detects these environment variables and synchronizes meetings in real-time.
