import asyncio
import os
import sys
import json
from app import pipeline, config

async def main():
    test_audio = r"C:\Users\HP\.gemini\antigravity\brain\02655370-c289-4ba1-9c7e-cb0271ddd0f6\.user_uploaded\uploaded_media_1795672107407.mp3"
    print(f"Testing pipeline against: {test_audio}")
    if not os.path.exists(test_audio):
        print("Audio file does not exist!")
        sys.exit(1)

    print("Executing pipeline.run_pipeline()...")
    result = await pipeline.run_pipeline(
        audio_path=test_audio,
        meeting_id="manent_pipeline_benchmark"
    )

    print("\n" + "="*60)
    print("MANENT BACKEND PIPELINE BENCHMARK REPORT")
    print("="*60)
    print(f"Meeting ID:       {result.meeting_id}")
    print(f"Audio Duration:   {result.duration_seconds:.2f}s ({result.duration_seconds/60:.1f} mins)")
    print(f"Summary:          {result.summary}")
    print(f"Key Topics:       {result.key_topics}")
    
    print("\n--- SPEAKER PARTICIPATION & MINUTES SPOKEN ---")
    for s in result.speaker_stats:
        print(f"  • {s.name:<20} | Time: {s.formatted_time:<8} | Share: {s.percentage:5.1f}% | Turns: {s.turn_count}")

    print("\n--- ACTIONFLOW (TASK ALLOCATIONS) ---")
    print(f"Total Action Items: {len(result.action_items)}")
    for a in result.action_items:
        print(f"  ⚡ [{a.assignee}] {a.task}")
        print(f"     Deadline: {a.deadline} | Status: {a.status}")
        if a.evidence:
            print(f"     Evidence: \"{a.evidence}\"")

    print("\n--- KEY DECISIONS & AGREEMENTS ---")
    print(f"Total Decisions: {len(result.decisions)}")
    for d in result.decisions:
        print(f"  ⚖️ [{d.status}] {d.decision} (Decided by: {d.decided_by or 'Consensus'})")
        if d.evidence:
            print(f"     Evidence: \"{d.evidence}\"")

    print("\n--- SAMPLE ALIGNED TRANSCRIPT TURNS ---")
    for t in result.aligned_transcript[:5]:
        print(f"  [{t.timestamp_str}] {t.speaker_name}: {t.text}")

if __name__ == "__main__":
    asyncio.run(main())
