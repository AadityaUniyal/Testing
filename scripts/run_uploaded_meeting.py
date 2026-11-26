import asyncio
import os
import sys
import time
import json
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.pipeline import run_pipeline
from app import database, config

async def main():
    audio_file = os.path.join(config.AUDIO_INPUT, "user_team_meeting_manent.m4a")
    if not os.path.exists(audio_file):
        raise FileNotFoundError(f"Audio file not found: {audio_file}")

    meeting_id = f"user_meeting_{int(time.time())}"
    print(f"\n=======================================================", flush=True)
    print(f"🚀 PROCESSING USER TEAM MEETING: {meeting_id}", flush=True)
    print(f"File: {audio_file} ({os.path.getsize(audio_file)/(1024*1024):.2f} MB)", flush=True)
    print(f"=======================================================\n", flush=True)

    t_start = time.time()

    def status_callback(status):
        pct = int(status.progress * 100)
        print(f"[{status.stage.upper()}] {pct}% — {status.message}", flush=True)

    result = await run_pipeline(
        audio_path=audio_file,
        meeting_id=meeting_id,
        min_speakers=2,
        max_speakers=5,
        on_status=status_callback
    )

    t_total = time.time() - t_start

    telem = database.get_telemetry(meeting_id) or {}
    meeting = database.get_meeting(meeting_id) or {}

    print(f"\n=======================================================", flush=True)
    print(f"✅ PIPELINE EXECUTION COMPLETED IN {t_total:.1f}s", flush=True)
    print(f"=======================================================\n", flush=True)

    print(f"Audio Duration: {result.duration_seconds:.1f}s ({result.duration_seconds/60:.2f} mins)", flush=True)
    print(f"Speech Ratio: {telem.get('speech_ratio', 0)*100:.1f}% Speech | {telem.get('silence_percentage', 0):.1f}% Silence", flush=True)
    print(f"Whisper Latency: {telem.get('whisper_latency_seconds', 0):.1f}s", flush=True)
    print(f"Diarization Latency: {telem.get('diarization_latency_seconds', 0):.1f}s", flush=True)
    print(f"LLM Latency: {telem.get('llm_latency_seconds', 0):.1f}s", flush=True)
    print(f"Total Words: {telem.get('word_count', 0)} | Total Turns: {telem.get('turn_count', 0)}", flush=True)
    print(f"Speakers Identified: {result.speakers}", flush=True)

    print("\n--- EXECUTIVE SUMMARY ---", flush=True)
    print(result.summary, flush=True)

    print("\n--- PARTICIPANT PROFILES ---", flush=True)
    for s in result.speaker_stats:
        print(f"  • {s.name}: {s.formatted_time} ({s.percentage}% talk-time, {s.turn_count} turns)", flush=True)

    print(f"\n--- KEY DECISIONS ({len(result.decisions)}) ---", flush=True)
    for d in result.decisions:
        print(f"  • [{d.status}] {d.decision} (Decided by: {d.decided_by or 'Consensus'})", flush=True)

    print(f"\n--- ACTION ITEMS / ASSIGNED TASKS ({len(result.action_items)}) ---", flush=True)
    for a in result.action_items:
        print(f"  • [{a.assignee}] {a.task} | Deadline: {a.deadline}", flush=True)
        if a.evidence:
            print(f"    Evidence: \"{a.evidence}\"", flush=True)

    # Save output json
    with open("USER_MEETING_RESULT.json", "w", encoding="utf-8") as f:
        json.dump({
            "meeting_id": meeting_id,
            "duration": result.duration_seconds,
            "telemetry": telem,
            "summary": result.summary,
            "speakers": [s.model_dump() for s in result.speaker_stats],
            "decisions": [d.model_dump() for d in result.decisions],
            "action_items": [a.model_dump() for a in result.action_items],
            "transcript": [t.model_dump() for t in result.transcript]
        }, f, indent=2, ensure_ascii=False)
    print("\nSaved result to USER_MEETING_RESULT.json", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
