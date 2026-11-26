"""
Live Streaming Meeting Intelligence Pipeline.
Handles real-time audio chunk ingestion from browser microphone:
1. Live Speech-to-Text via persistent GPU Whisper server.
2. Online speaker tracking and assignment.
3. Live real-time action item detection via Qwen.
4. Final consolidation when meeting ends.
"""
import io
import os
import time
import wave
import json
import asyncio
import numpy as np
import httpx
from datetime import datetime

from app import config, database, alignment, diarization_engine, llm_engine, model_manager
from app.models import AlignedSegment, ActionItem, Decision, MeetingIntelligence

WHISPER_SERVER_URL = "http://127.0.0.1:8082/inference"

# Keyword indicators for instant task detection
TASK_INDICATORS = [
    "will", "shall", "need to", "must", "assign", "deadline", "by tomorrow",
    "by friday", "by monday", "by next", "complete", "finish", "deliver",
    "karega", "karunga", "kar dunga", "dekh lunga", "bhejna", "bhej dunga"
]


class LiveMeetingSession:
    def __init__(self, meeting_id: str, client_ws):
        self.meeting_id = meeting_id
        self.ws = client_ws
        self.start_time = time.time()
        self.audio_chunks = []
        self.transcript_history = []
        self.detected_tasks = []
        self.speaker_counter = 0
        self.speaker_embeddings = {}  # speaker_id -> list of feature vectors
        self.sample_rate = 16000
        self.is_active = True
        self.current_offset = 0.0

        # Auto-activate local model services if not already active
        try:
            model_manager.ensure_llm_server(max_wait_sec=5.0)
        except Exception:
            pass

    async def ingest_chunk(self, pcm_bytes: bytes):
        """Process incoming 16kHz mono 16-bit PCM chunk from browser."""
        if not self.is_active or len(pcm_bytes) < 3200:
            return

        self.audio_chunks.append(pcm_bytes)
        chunk_duration = len(pcm_bytes) / (self.sample_rate * 2)  # 2 bytes per sample

        # 1. Convert raw PCM chunk to in-memory WAV for Whisper
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_bytes)
        wav_io.seek(0)

        # 2. Transcribe via GPU Whisper Server
        text = await self._transcribe_chunk(wav_io.getvalue())
        text = text.strip()

        if not text or text in [".", "..", "...", "Thank you.", "Bye."]:
            self.current_offset += chunk_duration
            return

        # 3. Speaker Assignment (Voice Acoustic Clustering)
        speaker_id = self._assign_speaker_simple(pcm_bytes)

        start_ts = self.current_offset
        end_ts = self.current_offset + chunk_duration
        self.current_offset = end_ts

        segment = {
            "start": round(start_ts, 2),
            "end": round(end_ts, 2),
            "speaker_id": speaker_id,
            "text": text
        }
        self.transcript_history.append(segment)

        # Broadcast live segment to UI
        await self.ws.send_json({
            "type": "live_transcript",
            "speaker": speaker_id,
            "text": text,
            "start": segment["start"],
            "end": segment["end"]
        })

        # 4. Real-time Action Item Spotting
        await self._check_live_task(speaker_id, text)

    async def _transcribe_chunk(self, wav_bytes: bytes) -> str:
        """Call persistent Whisper server on port 8082."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                files = {"file": ("chunk.wav", wav_bytes, "audio/wav")}
                r = await client.post(WHISPER_SERVER_URL, files=files)
                if r.status_code == 200:
                    data = r.json()
                    return data.get("text", "")
        except Exception as e:
            print(f"[Live] Whisper inference error: {e}")
        return ""

    def _assign_speaker_simple(self, pcm_bytes: bytes) -> str:
        """
        Fast online speaker tracking using energy, pitch/zero-crossing, and spectral moments.
        Provides distinct live speaker IDs (SPEAKER_00, SPEAKER_01, etc.) in real time.
        """
        audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        if len(audio_np) == 0:
            return "SPEAKER_00"

        # Acoustic signature: pitch approximation, zero-crossing rate, energy, centroid
        rms = np.sqrt(np.mean(audio_np ** 2))
        zcr = np.mean(np.diff(np.sign(audio_np)) != 0)
        fft = np.abs(np.fft.rfft(audio_np[:1024]))
        centroid = np.sum(fft * np.arange(len(fft))) / (np.sum(fft) + 1e-6)

        feat = np.array([rms / 1000.0, zcr * 10.0, centroid / 100.0])

        best_spk = None
        best_dist = 999999.0

        for spk, history in self.speaker_embeddings.items():
            avg_feat = np.mean(history, axis=0)
            dist = np.linalg.norm(feat - avg_feat)
            if dist < best_dist:
                best_dist = dist
                best_spk = spk

        # Threshold for new speaker vs existing speaker
        if best_dist < 4.5 and best_spk is not None:
            self.speaker_embeddings[best_spk].append(feat)
            return best_spk
        else:
            new_spk = f"SPEAKER_{self.speaker_counter:02d}"
            self.speaker_counter += 1
            self.speaker_embeddings[new_spk] = [feat]
            return new_spk

    async def _check_live_task(self, speaker: str, text: str):
        """Spot commitments and tasks in real-time as words are spoken."""
        text_lower = text.lower()
        if any(trigger in text_lower for trigger in TASK_INDICATORS):
            # Trigger fast Qwen extraction
            prompt = f"Speaker '{speaker}' said: \"{text}\". If an action item, task, or deadline is stated, extract it as JSON with keys: task, assignee, deadline. Else return {{}}."
            try:
                task_info = await asyncio.to_thread(llm_engine.extract_intelligence, prompt)
                if isinstance(task_info, dict) and task_info.get("task"):
                    item = {
                        "task": task_info["task"],
                        "assignee": task_info.get("assignee") or speaker,
                        "deadline": task_info.get("deadline") or "Not specified",
                        "evidence": text
                    }
                    self.detected_tasks.append(item)
                    await self.ws.send_json({
                        "type": "live_task",
                        "item": item
                    })
            except Exception as e:
                print(f"[Live] Live task error: {e}")

    async def finalize_meeting(self) -> MeetingIntelligence:
        """Consolidate full recording, perform global alignment and generate summary."""
        self.is_active = False
        duration = time.time() - self.start_time

        # Save complete session audio
        full_wav_path = os.path.join(config.AUDIO_INPUT, f"{self.meeting_id}.wav")
        all_pcm = b"".join(self.audio_chunks)
        with wave.open(full_wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(all_pcm)

        print(f"[Live] Saved full session audio: {full_wav_path} ({duration:.1f}s)")

        # Prepare formatted transcript
        formatted_lines = []
        aligned_segments = []
        unique_speakers = list(self.speaker_embeddings.keys()) or ["SPEAKER_00"]

        for seg in self.transcript_history:
            aligned_segments.append(AlignedSegment(
                start=seg["start"],
                end=seg["end"],
                speaker_id=seg["speaker_id"],
                text=seg["text"]
            ))
            formatted_lines.append(f"[{seg['start']}s - {seg['end']}s] {seg['speaker_id']}: {seg['text']}")

        full_transcript_text = "\n".join(formatted_lines)

        # Run Qwen full summary & intelligence extraction
        print("[Live] Generating final meeting intelligence report with Qwen...")
        try:
            intel = await asyncio.to_thread(llm_engine.extract_intelligence, full_transcript_text)
        except Exception as e:
            intel = {
                "summary": "Meeting concluded.",
                "decisions": [],
                "action_items": self.detected_tasks,
                "unresolved_issues": [],
                "important_points": []
            }

        # Build final MeetingIntelligence object
        action_items = [ActionItem(**a) for a in intel.get("action_items", [])]
        if not action_items and self.detected_tasks:
            action_items = [ActionItem(**a) for a in self.detected_tasks]

        meeting = MeetingIntelligence(
            meeting_id=self.meeting_id,
            filename=f"Live_Meeting_{self.meeting_id}.wav",
            duration_seconds=duration,
            processed_at=datetime.now().isoformat(),
            speakers=unique_speakers,
            summary=intel.get("summary", ""),
            decisions=[Decision(**d) for d in intel.get("decisions", [])],
            action_items=action_items,
            unresolved_issues=intel.get("unresolved_issues", []),
            important_points=intel.get("important_points", []),
            aligned_transcript=aligned_segments
        )

        # Save to database
        database.save_meeting(meeting)

        # Save results JSON
        res_path = os.path.join(config.RESULTS_DIR, f"{self.meeting_id}.json")
        with open(res_path, "w", encoding="utf-8") as f:
            json.dump(meeting.model_dump(), f, indent=2, ensure_ascii=False)

        return meeting
