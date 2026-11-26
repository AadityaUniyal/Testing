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
from pydantic import BaseModel

from app import config, database, model_manager
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
    # Auto-activate models in background so they are ready on first use
    asyncio.create_task(asyncio.to_thread(model_manager.ensure_llm_server))
    print("[Server] Meeting Intelligence ready at http://localhost:8000")


@app.on_event("shutdown")
async def shutdown():
    model_manager.stop_llm_server()
    diarization_engine.unload_pipeline()


@app.post("/api/trigger-models")
async def trigger_models():
    """
    On-demand model activation trigger.
    Triggered when user clicks Record button or drops an audio file.
    Ensures all models (Whisper, Pyannote, Qwen) are activated and warm.
    """
    status = await asyncio.to_thread(model_manager.trigger_all_models)
    return status


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
                action_val = str(data.get("action", "")).upper()
                if action_val in ("STOP_MEETING", "FINISH_MEETING"):
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

    # Trigger background model readiness
    asyncio.create_task(asyncio.to_thread(model_manager.ensure_llm_server))

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
@app.websocket("/ws/meeting/{meeting_id}")
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


@app.get("/api/meetings/{meeting_id}/telemetry")
async def get_meeting_telemetry(meeting_id: str):
    """
    Retrieve performance telemetry (VAD speech ratio, Whisper latency, realtime factor, model versions).
    """
    telem = database.get_telemetry(meeting_id)
    if not telem:
        meeting = database.get_meeting(meeting_id)
        if meeting and "telemetry" in meeting:
            return meeting["telemetry"]
        raise HTTPException(404, "Telemetry not found for meeting")
    return telem


class RenameSpeakerRequest(BaseModel):
    old_name: str
    new_name: str


@app.post("/api/meetings/{meeting_id}/speakers/rename")
async def rename_speaker(meeting_id: str, req: RenameSpeakerRequest):
    """
    Rename a speaker across minutes, transcripts, speaker stats, action items, and Supabase.
    """
    updated = database.rename_speaker(meeting_id, req.old_name.strip(), req.new_name.strip())
    if not updated:
        raise HTTPException(404, f"Meeting {meeting_id} not found or rename failed")
    return updated


@app.get("/api/meetings/{meeting_id}/audio")
async def get_meeting_audio(meeting_id: str):
    """Serve audio stream for meeting playback."""
    # 1. Processed audio
    proc_path = os.path.join(config.AUDIO_PROCESSED, f"{meeting_id}.wav")
    if os.path.exists(proc_path):
        return FileResponse(proc_path, media_type="audio/wav")

    # 2. Input folder files starting with meeting_id
    if os.path.exists(config.AUDIO_INPUT):
        for f in os.listdir(config.AUDIO_INPUT):
            if f.startswith(meeting_id):
                full_p = os.path.join(config.AUDIO_INPUT, f)
                ext = os.path.splitext(f)[1].lower()
                mime = "audio/wav" if ext == ".wav" else "audio/mpeg" if ext == ".mp3" else "audio/mp4"
                return FileResponse(full_p, media_type=mime)

    # 3. Match by meeting filename
    meeting = database.get_meeting(meeting_id)
    if meeting and meeting.get("filename"):
        cand = os.path.join(config.AUDIO_INPUT, meeting["filename"])
        if os.path.exists(cand):
            ext = os.path.splitext(meeting["filename"])[1].lower()
            mime = "audio/wav" if ext == ".wav" else "audio/mpeg" if ext == ".mp3" else "audio/mp4"
            return FileResponse(cand, media_type=mime)

    raise HTTPException(404, "Audio file not found for this meeting")


@app.get("/api/meetings/{meeting_id}/speakers-grouped")
async def get_speakers_grouped(meeting_id: str):
    """
    Returns segregated transcript grouped by speaker:
    Each participant with their aggregate speaking metrics and all spoken turns with timestamps.
    """
    meeting = database.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(404, "Meeting not found")

    stats = meeting.get("speaker_stats", [])
    transcript = meeting.get("transcript", [])

    # Group statements
    grouped_map = {}
    for seg in transcript:
        spk = seg.get("speaker_name") or seg.get("speaker") or seg.get("speaker_id") or "Unknown"
        if spk not in grouped_map:
            grouped_map[spk] = []
        grouped_map[spk].append({
            "start": float(seg.get("start") or 0.0),
            "end": float(seg.get("end") or 0.0),
            "timestamp_str": seg.get("timestamp_str") or f"{seg.get('start', 0):.1f}s - {seg.get('end', 0):.1f}s",
            "text": seg.get("text", "")
        })

    result = []
    known_speakers = set()
    for st in stats:
        name = st.get("name") or st.get("speaker_name")
        if name:
            known_speakers.add(name)
            result.append({
                "name": name,
                "speaker_id": st.get("speaker_id", name),
                "total_seconds": st.get("total_seconds", 0.0),
                "formatted_time": st.get("formatted_time", ""),
                "percentage": st.get("percentage", 0.0),
                "turn_count": len(grouped_map.get(name, [])),
                "statements": grouped_map.get(name, [])
            })

    # Include any remaining speakers found in transcript
    for spk, stmts in grouped_map.items():
        if spk not in known_speakers:
            total_sec = sum(max(0.1, s["end"] - s["start"]) for s in stmts)
            result.append({
                "name": spk,
                "speaker_id": spk,
                "total_seconds": round(total_sec, 1),
                "formatted_time": f"{int(total_sec//60):02d}:{int(total_sec%60):02d}",
                "percentage": 0.0,
                "turn_count": len(stmts),
                "statements": stmts
            })

    return {
        "meeting_id": meeting_id,
        "speakers": result
    }
