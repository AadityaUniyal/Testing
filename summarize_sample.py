import json
import httpx

with open(r"E:\TESTING\results\meeting_sample_run.json", "r", encoding="utf-8") as f:
    data = json.load(f)

lines = [f"[{s['start']}s - {s['end']}s] {s['speaker_id']}: {s['text']}" for s in data["aligned_transcript"]]
transcript_text = "\n".join(lines)

prompt = f"""You are an executive meeting assistant. Read the transcript below and output a JSON report.
Because this is an introductory discussion/podcast, summarize the main topics, key points, and identify who spoke.

JSON Schema:
{{
  "summary": "3-4 sentence comprehensive overview",
  "speakers_summary": {{
    "SPEAKER_00": "Tom (Host / Moderator)",
    "SPEAKER_01": "Sameer (Open Platform & Use Cases)",
    "SPEAKER_02": "Will (APIs, Integration & Deployment)"
  }},
  "topics_discussed": [
    "RingCentral AI APIs and conversational intelligence",
    "Speech to text, interaction and sentiment analysis in contact centers",
    "Audio and text API categories",
    "Speaker diarization vs speaker identification"
  ],
  "action_items": [],
  "decisions": [
    {{"decision": "Program is currently in beta; public general availability coming soon", "speaker_id": "SPEAKER_00"}}
  ]
}}

TRANSCRIPT:
{transcript_text}

JSON:"""

r = httpx.post("http://127.0.0.1:8081/v1/chat/completions", json={
    "messages": [{"role": "user", "content": prompt}],
    "max_tokens": 1024,
    "temperature": 0.1
}, timeout=60.0)

msg = r.json()["choices"][0]["message"]
print("=== QWEN EXECUTIVE SUMMARY & INTELLIGENCE ===")
print(msg.get("content") or msg.get("reasoning_content"))
