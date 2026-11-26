import asyncio
import json
import time
from app.pipeline import run_pipeline

async def main():
    audio_file = r"E:\TESTING\audio\input\meeting_sample.mp3"
    print(f"=== PROCESSING UPLOADED MEETING AUDIO: {audio_file} ===")
    t0 = time.time()
    
    result = await run_pipeline(
        audio_path=audio_file,
        meeting_id="meeting_sample_run",
        min_speakers=2,
        max_speakers=5
    )
    
    elapsed = time.time() - t0
    print(f"\n=== PIPELINE FINISHED IN {elapsed:.1f}s ===")
    print(f"Duration: {result.duration_seconds:.1f}s")
    print(f"Speakers Identified: {result.speakers}")
    print(f"\n--- SUMMARY ---\n{result.summary}")
    
    print("\n--- DECISIONS ---")
    for d in result.decisions:
        print(f" • [{d.speaker_id}] {d.decision}")
        
    print("\n--- ACTION ITEMS & TASKS ---")
    for a in result.action_items:
        print(f" • Task: {a.task}")
        print(f"   Assignee: {a.assignee} | Deadline: {a.deadline}")
        print(f"   Evidence: \"{a.evidence}\"")
        
    print("\n--- ALIGNED TRANSCRIPT (first 10 turns) ---")
    for seg in result.aligned_transcript[:10]:
        print(f" [{seg.start:.1f}s - {seg.end:.1f}s] {seg.speaker_id}: {seg.text}")

if __name__ == "__main__":
    asyncio.run(main())
