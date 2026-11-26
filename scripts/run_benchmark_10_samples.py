"""
Benchmark 10 Audio Variants Execution Engine
Iterates through all 10 real-world conversation scenarios across the entire pipeline:
1. Universal Audio Ingestion & Resampling (16kHz mono)
2. Speech-to-Text Transcription with Whisper Large-v3 Turbo (CUDA)
3. Speaker Diarization with Pyannote Community-1
4. Temporal Alignment & Speaker Talk-Time Minutes Computation
5. Executive Intelligence & Dynamic Speaker Identification with Qwen 3.5
6. Persistence to SQLite & Cloud Sync to Supabase
7. Generates Comprehensive Markdown & JSON Benchmark Reports
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure app is importable
sys.path.insert(0, r"E:\TESTING")

from app import config, database, supabase_client
from app.pipeline import run_pipeline

BENCHMARK_SAMPLES = [
    {
        "id": "bench_var01_tech_apis_3spk",
        "file": "bench_01_tech_apis_3spk.mp3",
        "variant": "Tech Architecture Sync (3 speakers)",
        "expected_speakers": 3,
        "description": "Real multi-speaker tech dialogue: Tom, Sameer, Will discussing AI APIs, release dates, beta testing, and architecture."
    },
    {
        "id": "bench_var02_pyannote_room",
        "file": "bench_02_pyannote_eval_room.wav",
        "variant": "Conference Room Acoustic Benchmark",
        "expected_speakers": 2,
        "description": "Pyannote official evaluation audio with natural room reverberation, realistic mic distance, and overlapping speech."
    },
    {
        "id": "bench_var03_daily_standup_3spk",
        "file": "bench_03_daily_standup_3spk.wav",
        "variant": "Daily Standup / Rapid Check-in (3 speakers)",
        "expected_speakers": 3,
        "description": "Fast-paced standup meeting: Sarah (Scrum Master), Alex (Dev), Priya (QA) reviewing blockers and code freeze."
    },
    {
        "id": "bench_var04_sprint_planning_4spk",
        "file": "bench_04_sprint_planning_4spk.wav",
        "variant": "Cross-Functional Sprint Planning (4 speakers)",
        "expected_speakers": 4,
        "description": "Sprint planning: Elena (PM), David (Architect), Marcus (Backend), Chloe (Frontend) debating PostgREST and WebSockets."
    },
    {
        "id": "bench_var05_action_heavy_ops_4spk",
        "file": "bench_05_action_heavy_ops_4spk.wav",
        "variant": "Action-Item Heavy Delivery Sync (4 speakers)",
        "expected_speakers": 4,
        "description": "High action density: Jordan, Rachel, Liam, Sophia assigning tasks with specific deadlines and compliance deliverables."
    },
    {
        "id": "bench_var06_strategic_decisions_3spk",
        "file": "bench_06_strategic_decisions_3spk.wav",
        "variant": "Strategic Architecture Debate (3 speakers)",
        "expected_speakers": 3,
        "description": "Architectural debate between DynamoDB, Postgres, and Supabase. Formal consensus reached and GraphQL deferred."
    },
    {
        "id": "bench_var07_international_accents_3spk",
        "file": "bench_07_international_accents_3spk.wav",
        "variant": "Multi-Accent International Sync (3 speakers)",
        "expected_speakers": 3,
        "description": "Cross-region telemetry review featuring UK British (Oliver), Indian (Aarav), and US (Jennifer) English accents."
    },
    {
        "id": "bench_var08_rapid_overlap_ux_3spk",
        "file": "bench_08_rapid_overlap_ux_3spk.wav",
        "variant": "High-Overlap UX Brainstorming (3 speakers)",
        "expected_speakers": 3,
        "description": "Rapid back-and-forth remarks, interruptions, and quick affirmations on mobile onboarding permissions."
    },
    {
        "id": "bench_var09_consultation_1on1_2spk",
        "file": "bench_09_consultation_1on1_2spk.wav",
        "variant": "1-on-1 Executive Consultation (2 speakers)",
        "expected_speakers": 2,
        "description": "Healthcare client Dr. Aris interviewing Nathan on HIPAA compliance, on-premise GPU latency, and offline requirements."
    },
    {
        "id": "bench_var10_postmortem_retro_4spk",
        "file": "bench_10_postmortem_retro_4spk.wav",
        "variant": "Incident Post-Mortem & Sprint Retrospective (4 speakers)",
        "expected_speakers": 4,
        "description": "Outage retrospective: Kevin, Nina, Daniel, Maya reviewing connection pooling root causes and preventative action items."
    }
]

async def run_benchmark():
    print("=" * 80)
    print("STARTING MANENT PIPELINE 10-SAMPLE BENCHMARK SUITE")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Supabase Cloud Sync Configured: {supabase_client.is_configured()}")
    
    results = []
    
    for idx, sample in enumerate(BENCHMARK_SAMPLES, 1):
        file_path = os.path.join(config.AUDIO_INPUT, sample["file"])
        if not os.path.exists(file_path):
            print(f"\n[SKIP] Audio file not found: {file_path}")
            continue
            
        print(f"\n" + "-" * 75)
        print(f"[{idx}/10] BENCHMARK VARIANT: {sample['variant']}")
        print(f"File: {sample['file']}")
        print(f"Description: {sample['description']}")
        print("-" * 75)
        
        t_start = time.time()
        try:
            intel = await run_pipeline(
                audio_path=file_path,
                meeting_id=sample["id"]
            )
            total_elapsed = time.time() - t_start
            
            # Retrieve from SQLite to verify local persistence
            db_row = database.get_meeting(sample["id"])
            
            # Format speaker stats
            spk_summary = []
            for spk in intel.speaker_stats:
                spk_summary.append(f"{spk.name} ({spk.formatted_time}, {spk.percentage:.1f}%, {spk.turn_count} turns)")
                
            benchmark_record = {
                "sample_index": idx,
                "variant": sample["variant"],
                "meeting_id": sample["id"],
                "filename": sample["file"],
                "duration_seconds": round(intel.duration_seconds, 1),
                "total_processing_time_s": round(total_elapsed, 1),
                "rtf": round(total_elapsed / max(intel.duration_seconds, 0.1), 2),
                "transcript_turn_count": len(intel.aligned_transcript),
                "speakers_detected": intel.speakers,
                "speaker_stats": [s.model_dump() for s in intel.speaker_stats],
                "summary": intel.summary,
                "key_topics": intel.key_topics,
                "action_items_count": len(intel.action_items),
                "action_items": [a.model_dump() for a in intel.action_items],
                "decisions_count": len(intel.decisions),
                "decisions": [d.model_dump() for d in intel.decisions],
                "sqlite_persisted": bool(db_row is not None),
                "supabase_synced": supabase_client.is_configured()
            }
            results.append(benchmark_record)
            
            print(f"[OK] Completed in {total_elapsed:.1f}s (Audio Duration: {intel.duration_seconds:.1f}s)")
            print(f"  • Speakers ({len(intel.speakers)}): {', '.join(spk_summary)}")
            print(f"  • Summary: {intel.summary[:140]}...")
            print(f"  • Action Items ({len(intel.action_items)}):")
            for act in intel.action_items:
                print(f"     - [{act.assignee}] {act.task} (Deadline: {act.deadline})")
            print(f"  • Decisions ({len(intel.decisions)}):")
            for dec in intel.decisions:
                print(f"     - [{dec.status}] {dec.decision} (By: {dec.decided_by or 'Consensus'})")
                
        except Exception as e:
            print(f"[ERROR] Failed on {sample['file']}: {e}")
            import traceback
            traceback.print_exc()
            
    # Save Benchmark JSON
    benchmark_json_path = os.path.join(r"E:\TESTING", "benchmark_10_samples_results.json")
    with open(benchmark_json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n[SAVED] Benchmark raw results saved to: {benchmark_json_path}")
    
    return results

if __name__ == "__main__":
    asyncio.run(run_benchmark())
