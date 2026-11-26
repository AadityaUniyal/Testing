"""
Pipeline Orchestrator — End-to-end synchronized meeting intelligence.
100% Dynamic — No hardcoded scripts, names, or assumptions.
Stages:
1. Universal Audio Ingestion & Normalization (soundfile + scipy)
2. Speech-to-Text Transcription with Timestamps (Whisper Large-v3 Turbo on CUDA)
3. Multi-Speaker Diarization (Pyannote Community-1)
4. Temporal Speaker-Turn Alignment
5. Executive Intelligence Extraction & Speaker Name Resolution (Qwen3.5-0.8B)
6. Persistence to Local SQLite & Supabase Cloud
"""
import json
import os
import time
import uuid
from datetime import datetime

from app import config, database, alignment, diarization_engine, llm_engine, whisper_engine, audio_utils, model_manager, vad_engine
from app.models import (
    MeetingIntelligence, PipelineStatus,
    TranscriptSegment, SpeakerSegment, AlignedSegment,
    ActionItem, Decision,
)


async def run_pipeline(
    audio_path: str,
    meeting_id: str = None,
    min_speakers: int = 2,
    max_speakers: int = None,
    on_status=None,
) -> MeetingIntelligence:
    """
    Execute full synchronized pipeline on any audio input.
    Works for both uploaded recordings and saved live sessions.
    """
    mid = meeting_id or f"mtg_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    async def _status(stage, progress, message, error=None):
        s = PipelineStatus(meeting_id=mid, stage=stage, progress=progress, message=message, error=error)
        print(f"[Pipeline] [{stage}] {progress:.0%} — {message}")
        if on_status:
            await on_status(s)

    try:
        # Auto-activate LLM server in background if not already active
        model_manager.ensure_llm_server(max_wait_sec=5.0)

        # ─── STAGE 1: Audio Preprocessing & Normalization ──────
        await _status("preprocess", 0.0, "Decoding and normalizing audio to 16kHz mono...")
        basename = os.path.splitext(os.path.basename(audio_path))[0]
        processed_path = os.path.join(config.AUDIO_PROCESSED, f"{basename}.wav")

        duration = audio_utils.convert_to_16k_mono_wav(audio_path, processed_path)
        await _status("preprocess", 1.0, f"Audio ready: {duration:.1f}s ({duration/60:.1f} min)")

        # ─── STAGE 2: Whisper Large-v3 Turbo Transcription ────
        await _status("transcription", 0.0, "Transcribing speech with Whisper Large-v3 Turbo (CUDA)...")
        t0 = time.time()

        transcript_segments = whisper_engine.transcribe(
            audio_path=processed_path,
            output_dir=config.TRANSCRIPTS_DIR,
        )

        whisper_time = time.time() - t0
        await _status("transcription", 1.0,
                       f"Transcribed {len(transcript_segments)} segments in {whisper_time:.1f}s")

        # ─── STAGE 3: Pyannote Speaker Diarization ──────────────
        await _status("diarization", 0.0, "Identifying speakers with Pyannote Community-1...")
        t0 = time.time()

        speaker_segments = diarization_engine.diarize(
            audio_path=processed_path,
            output_dir=config.TRANSCRIPTS_DIR,
            min_speakers=min_speakers,
            max_speakers=max_speakers or config.MAX_SPEAKERS,
        )

        diarize_time = time.time() - t0
        raw_speakers = list(set(s.speaker_id for s in speaker_segments))
        await _status("diarization", 1.0,
                       f"Identified {len(raw_speakers)} distinct speakers in {diarize_time:.1f}s")

        # Free diarization resources
        diarization_engine.unload_pipeline()

        # ─── STAGE 4: Temporal Alignment ───────────────────────
        await _status("alignment", 0.0, "Aligning transcript with speaker turns...")

        aligned = alignment.align_transcript_speakers(
            transcript=transcript_segments,
            speakers=speaker_segments,
            output_dir=config.TRANSCRIPTS_DIR,
            filename_base=basename,
        )
        await _status("alignment", 1.0, f"Aligned {len(aligned)} dialogue turns")

        # ─── STAGE 5: Qwen Meeting Intelligence ────────────────
        await _status("intelligence", 0.0, "Analyzing meeting with Qwen (Summary, Speaker Names, Tasks)...")
        t0 = time.time()

        formatted_dialogue = alignment.format_transcript_for_llm(aligned)
        intelligence = llm_engine.extract_intelligence(formatted_dialogue)
        llm_time = time.time() - t0

        # Apply identified speaker names (e.g. SPEAKER_00 -> Tom)
        speaker_mapping = intelligence.get("speaker_mapping", {})
        if speaker_mapping:
            aligned = alignment.apply_speaker_mapping(aligned, speaker_mapping)

        # Calculate rich talk-time stats & minutes per speaker (Figma Manent spec)
        speaker_stats = alignment.calculate_speaker_stats(aligned, speaker_mapping)
        final_speakers = [s.name for s in speaker_stats]

        await _status("intelligence", 1.0,
                       f"Intelligence extracted in {llm_time:.1f}s ({len(intelligence.get('action_items', []))} action items, {len(speaker_stats)} speakers profiled)")

        # ─── STAGE 6: Build Intelligence Object & Persist ──────
        await _status("saving", 0.0, "Saving to SQLite database & syncing...")

        # Parse decisions
        decisions_list = []
        for d in intelligence.get("decisions", []):
            if isinstance(d, dict):
                speaker_val = d.get("speaker") or d.get("speaker_id") or d.get("decided_by")
                if speaker_val in speaker_mapping:
                    speaker_val = speaker_mapping[speaker_val]
                decisions_list.append(Decision(
                    decision=d.get("decision", ""),
                    status=d.get("status", "RESOLVED"),
                    decided_by=speaker_val,
                    timestamp=d.get("timestamp"),
                    evidence=d.get("evidence")
                ))
            elif isinstance(d, str):
                decisions_list.append(Decision(decision=d))

        # Parse action items (ActionFlow)
        action_items_list = []
        for a in intelligence.get("action_items", []):
            if isinstance(a, dict):
                assignee_val = a.get("assignee") or a.get("owner")
                if assignee_val in speaker_mapping:
                    assignee_val = speaker_mapping[assignee_val]
                action_items_list.append(ActionItem(
                    task=a.get("task", ""),
                    assignee=assignee_val or "Unassigned",
                    deadline=a.get("deadline") or "Not specified",
                    evidence=a.get("evidence"),
                    timestamp=a.get("timestamp"),
                    commitment_type=a.get("type") or a.get("commitment_type"),
                    status=a.get("status", "open")
                ))

        result = MeetingIntelligence(
            meeting_id=mid,
            filename=os.path.basename(audio_path),
            duration_seconds=duration,
            processed_at=datetime.now().isoformat(),
            speakers=final_speakers,
            speaker_stats=speaker_stats,
            summary=intelligence.get("summary", ""),
            key_topics=intelligence.get("key_topics", intelligence.get("important_points", [])),
            decisions=decisions_list,
            action_items=action_items_list,
            unresolved_issues=intelligence.get("unresolved_issues", []),
            important_points=intelligence.get("important_points", []),
            aligned_transcript=aligned,
        )

        total_time = whisper_time + diarize_time + llm_time

        # Compute VAD speech-to-silence ratio & noise profile
        vad_profile = vad_engine.profile_audio_speech(audio_path)
        word_count = sum(len(s.text.split()) for s in aligned)
        turn_count = len(aligned)
        realtime_factor = round(total_time / max(0.1, duration), 3)

        telemetry = {
            "meeting_id": mid,
            "audio_duration_seconds": round(duration, 2),
            "whisper_latency_seconds": round(whisper_time, 2),
            "diarization_latency_seconds": round(diarize_time, 2),
            "llm_latency_seconds": round(llm_time, 2),
            "total_latency_seconds": round(total_time, 2),
            "realtime_factor": realtime_factor,
            "speech_ratio": vad_profile.get("speech_ratio", 0.0),
            "silence_percentage": vad_profile.get("silence_percentage", 0.0),
            "word_count": word_count,
            "turn_count": turn_count,
            "speaker_count": len(final_speakers),
            "task_count": len(action_items_list),
            "decision_count": len(decisions_list),
            "device_profile": "hybrid_edge_ios",
            "model_versions": {
                "whisper": "large-v3-turbo-cuda",
                "diarization": "pyannote-community-1",
                "llm": "qwen2.5-0.8b-instruct-q4",
                "vad": "silero-vad-v5-onnx"
            },
            "created_at": datetime.now().isoformat()
        }

        # 1. Local SQLite storage with full execution telemetry
        database.save_meeting(
            result,
            raw_whisper=json.dumps([s.model_dump() for s in transcript_segments]),
            raw_diarize=json.dumps([s.model_dump() for s in speaker_segments]),
            raw_llm=json.dumps(intelligence),
            telemetry=telemetry
        )

        # 2. Local JSON artifact
        result_dict = result.model_dump()
        result_dict["telemetry"] = telemetry
        result_path = os.path.join(config.RESULTS_DIR, f"{mid}.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False)

        # 3. Optional Supabase Cloud Sync (including telemetry)
        try:
            from app import supabase_client
            if supabase_client.is_configured():
                import inspect
                sync_res = supabase_client.sync_meeting(result_dict)
                if inspect.isawaitable(sync_res):
                    await sync_res
        except Exception as e:
            print(f"[Supabase Sync Notice] {e}")

        await _status("complete", 1.0,
                       f"Processing complete in {total_time:.1f}s ({realtime_factor}x real-time)! Discovered {len(final_speakers)} speakers, {len(action_items_list)} tasks, {vad_profile.get('speech_ratio', 0.0)*100:.0f}% speech.")

        return result

    except Exception as e:
        await _status("error", 0.0, str(e), error=str(e))
        raise
