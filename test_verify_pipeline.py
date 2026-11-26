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
        meeting_id="e2e_verification_test"
    )

    print("\n=== PIPELINE SUCCESSFUL ===")
    print(f"Meeting ID: {result.meeting_id}")
    print(f"Duration: {result.duration_seconds:.2f}s")
    print(f"Speakers Identified: {result.speakers}")
    print(f"Summary: {result.summary[:200]}...")
    print(f"Action Items Count: {len(result.action_items)}")
    for a in result.action_items:
        print(f"  - [{a.assignee}] {a.task} (Deadline: {a.deadline})")
    print(f"Decisions Count: {len(result.decisions)}")
    for d in result.decisions:
        print(f"  - {d.decision}")

if __name__ == "__main__":
    asyncio.run(main())
