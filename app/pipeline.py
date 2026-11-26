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

from app import config, database, alignment, diarization_engine, llm_engine, whisper_engine, audio_utils, model_manager
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
            final_speakers = [speaker_mapping.get(s, s) for s in raw_speakers]
        else:
            final_speakers = raw_speakers

        await _status("intelligence", 1.0,
                       f"Intelligence extracted in {llm_time:.1f}s ({len(intelligence.get('action_items', []))} action items)")

        # ─── STAGE 6: Build Intelligence Object & Persist ──────
        await _status("saving", 0.0, "Saving to SQLite database & syncing...")

        # Parse decisions
        decisions_list = []
        for d in intelligence.get("decisions", []):
            if isinstance(d, dict):
                speaker_val = d.get("speaker") or d.get("speaker_id")
                # Map speaker if known
                if speaker_val in speaker_mapping:
                    speaker_val = speaker_mapping[speaker_val]
                decisions_list.append(Decision(decision=d.get("decision", ""), speaker_id=speaker_val))
            elif isinstance(d, str):
                decisions_list.append(Decision(decision=d))

        # Parse action items
        action_items_list = []
        for a in intelligence.get("action_items", []):
            if isinstance(a, dict):
                assignee_val = a.get("assignee")
                if assignee_val in speaker_mapping:
                    assignee_val = speaker_mapping[assignee_val]
                action_items_list.append(ActionItem(
                    task=a.get("task", ""),
                    assignee=assignee_val,
                    deadline=a.get("deadline"),
                    evidence=a.get("evidence"),
                    commitment_type=a.get("type") or a.get("commitment_type"),
                    status=a.get("status", "pending")
                ))

        result = MeetingIntelligence(
            meeting_id=mid,
            filename=os.path.basename(audio_path),
            duration_seconds=duration,
            processed_at=datetime.now().isoformat(),
            speakers=final_speakers,
            summary=intelligence.get("summary", ""),
            decisions=decisions_list,
            action_items=action_items_list,
            unresolved_issues=intelligence.get("unresolved_issues", []),
            important_points=intelligence.get("important_points", []),
            aligned_transcript=aligned,
        )

        # 1. Local SQLite storage (100% offline guarantee)
        database.save_meeting(
            result,
            raw_whisper=json.dumps([s.model_dump() for s in transcript_segments]),
            raw_diarize=json.dumps([s.model_dump() for s in speaker_segments]),
            raw_llm=json.dumps(intelligence),
        )

        # 2. Local JSON artifact
        result_path = os.path.join(config.RESULTS_DIR, f"{mid}.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)

        # 3. Optional Supabase Cloud Sync (if configured)
        try:
            from app import supabase_client
            if supabase_client.is_configured():
                await supabase_client.sync_meeting(result)
        except Exception as e:
            print(f"[Supabase Sync Notice] {e}")

        total_time = whisper_time + diarize_time + llm_time
        await _status("complete", 1.0,
                       f"Processing complete in {total_time:.1f}s! Discovered {len(final_speakers)} speakers and {len(action_items_list)} tasks.")

        return result

    except Exception as e:
        await _status("error", 0.0, str(e), error=str(e))
        raise
