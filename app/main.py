"""
FastAPI Server — Meeting Intelligence Web App.
REST endpoints + WebSocket for both Live Streaming Meetings and File Upload.
"""
import asyncio
import json
import os
import shutil
import uuid
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app import config, database
from app.pipeline import run_pipeline
from app.live_pipeline import LiveMeetingSession
from app.models import PipelineStatus
from app import whisper_engine, diarization_engine, llm_engine

app = FastAPI(title="Meeting Intelligence", version="2.0.0")

# Serve frontend
FRONTEND_DIR = os.path.join(config.BASE_DIR, "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Active WebSocket connections per meeting
_ws_connections: dict[str, list[WebSocket]] = {}
_live_sessions: dict[str, LiveMeetingSession] = {}


@app.on_event("startup")
async def startup():
    database.init_db()
    print("[Server] Meeting Intelligence ready at http://localhost:8000")


@app.on_event("shutdown")
async def shutdown():
    llm_engine.stop_server()
    diarization_engine.unload_pipeline()


# ── Frontend ──────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# ── Health & Status ───────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "whisper": whisper_engine.check_whisper_ready(),
        "diarization": diarization_engine.check_diarization_ready(),
        "llm": llm_engine.check_llm_ready(),
    }


# ── LIVE MEETING WEBSOCKET ────────────────────────────────────

@app.websocket("/ws/live-meeting/{meeting_id}")
async def live_meeting_websocket(websocket: WebSocket, meeting_id: str):
    """
    Accepts live streaming microphone audio from the client.
    Sends back real-time live transcriptions, speaker tracking, and detected tasks.
    """
    await websocket.accept()
    session = LiveMeetingSession(meeting_id, websocket)
    _live_sessions[meeting_id] = session
    print(f"[Live] Started live session {meeting_id}")

    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message and message["bytes"]:
                # Incoming audio chunk (PCM 16-bit 16kHz mono)
                await session.ingest_chunk(message["bytes"])
            elif "text" in message and message["text"]:
                data = json.loads(message["text"])
                if data.get("action") == "STOP_MEETING":
                    print(f"[Live] Finalizing live session {meeting_id}...")
                    await websocket.send_json({"type": "status", "message": "Finalizing intelligence report..."})
                    final_meeting = await session.finalize_meeting()
                    await websocket.send_json({
                        "type": "meeting_completed",
                        "data": final_meeting.model_dump()
                    })
                    break
    except WebSocketDisconnect:
        print(f"[Live] Session {meeting_id} disconnected.")
    except Exception as e:
        print(f"[Live] WebSocket error: {e}")
    finally:
        _live_sessions.pop(meeting_id, None)


# ── FILE UPLOAD & BATCH PROCESSING ────────────────────────────

@app.post("/api/upload")
async def upload_audio(file: UploadFile = File(...)):
    allowed = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".mp4"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported format: {ext}. Use: {allowed}")

    meeting_id = f"mtg_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    save_path = os.path.join(config.AUDIO_INPUT, f"{meeting_id}{ext}")

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {
        "meeting_id": meeting_id,
        "filename": file.filename,
        "saved_path": save_path,
        "size_mb": round(os.path.getsize(save_path) / (1024 * 1024), 2),
    }


@app.post("/api/process/{meeting_id}")
async def process_meeting(meeting_id: str, min_speakers: int = 2, max_speakers: int = 15):
    files = [f for f in os.listdir(config.AUDIO_INPUT) if f.startswith(meeting_id)]
    if not files:
        raise HTTPException(404, f"No audio file found for meeting {meeting_id}")

    audio_path = os.path.join(config.AUDIO_INPUT, files[0])

    async def _run():
        try:
            await run_pipeline(
                audio_path=audio_path,
                meeting_id=meeting_id,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
                on_status=lambda s: _broadcast(meeting_id, s),
            )
        except Exception as e:
            await _broadcast(meeting_id, PipelineStatus(
                meeting_id=meeting_id, stage="error", progress=0, message=str(e), error=str(e)
            ))

    asyncio.create_task(_run())
    return {"meeting_id": meeting_id, "status": "processing_started"}


@app.websocket("/ws/{meeting_id}")
async def websocket_endpoint(websocket: WebSocket, meeting_id: str):
    await websocket.accept()
    _ws_connections.setdefault(meeting_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_connections[meeting_id].remove(websocket)


async def _broadcast(meeting_id: str, status: PipelineStatus):
    connections = _ws_connections.get(meeting_id, [])
    data = status.model_dump_json()
    for ws in connections[:]:
        try:
            await ws.send_text(data)
        except Exception:
            connections.remove(ws)


# ── RESULTS & HISTORY ─────────────────────────────────────────

@app.get("/api/meetings")
async def list_meetings():
    return database.list_meetings()


@app.get("/api/meetings/{meeting_id}")
async def get_meeting(meeting_id: str):
    result = database.get_meeting(meeting_id)
    if result is None:
        raise HTTPException(404, "Meeting not found")
    return result
