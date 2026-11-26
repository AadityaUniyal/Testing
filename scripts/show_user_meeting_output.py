import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app import database
from app.supabase_client import SUPABASE_URL, SUPABASE_KEY
import urllib.request

meeting_id = "user_meeting_1795707359"
m = database.get_meeting(meeting_id)

print(f"=======================================================")
print(f"🎉 USER MEETING FULL OUTPUT: {meeting_id}")
print(f"=======================================================\n")

if m:
    print(f"Audio File: {m.get('filename')}")
    print(f"Duration: {m.get('duration_sec'):.1f}s ({m.get('duration_sec')/60:.2f} mins)")
    print(f"Identified Speakers: {m.get('speakers')}\n")

    print("--- SPEAKER TALK-TIME BREAKDOWN ---")
    for s in m.get('speaker_stats', []):
        print(f"  • {s.get('name')}: {s.get('formatted_time')} ({s.get('percentage')}% talk-time, {s.get('turn_count')} turns)")

    print("\n--- EXECUTIVE SUMMARY ---")
    print(m.get('summary'))

    print(f"\n--- KEY DECISIONS ({len(m.get('decisions', []))}) ---")
    for d in m.get('decisions', []):
        print(f"  • [{d.get('status')}] {d.get('decision')} (Decided by: {d.get('decided_by') or 'Consensus'})")

    print(f"\n--- ACTION ITEMS / ASSIGNED TASKS ({len(m.get('action_items', []))}) ---")
    for a in m.get('action_items', []):
        print(f"  • [{a.get('assignee')}] {a.get('task')} | Deadline: {a.get('deadline')}")
        if a.get('evidence'):
            print(f"    Evidence: \"{a.get('evidence')}\"")

    print(f"\n--- FULL SEGMENTED TRANSCRIPT ({len(m.get('transcript', []))} turns) ---")
    for seg in m.get('transcript', []):
        spk = seg.get('speaker_name') or seg.get('speaker_id')
        print(f"  [{seg.get('timestamp_str')}] {spk}: {seg.get('text')}")

# Remote Supabase check
print("\n--- SUPABASE CLOUD PERSISTENCE ---")
try:
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/meetings?title=eq.user_team_meeting_manent.m4a&select=id,title,duration_seconds,summary",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    )
    with urllib.request.urlopen(req) as resp:
        sb_data = json.loads(resp.read().decode())
        if sb_data:
            print(f"✅ Synced to Supabase! Record ID: {sb_data[0].get('id')}")
        else:
            print("Sync queued or under alternative title.")
except Exception as e:
    print(f"Supabase check: {e}")
