import json
from app import database
from app.models import MeetingIntelligence, Decision, ActionItem, AlignedSegment

# Load the aligned transcript
with open(r"E:\TESTING\results\meeting_sample_run.json", "r", encoding="utf-8") as f:
    orig = json.load(f)

# Build the rich meeting intelligence
meeting = MeetingIntelligence(
    meeting_id="meeting_sample_run",
    filename="resources_RC_Conversation_Sample.mp3",
    duration_seconds=orig["duration_seconds"],
    processed_at="2026-11-26T11:27:00",
    speakers=["Tom (SPEAKER_00)", "Sameer (SPEAKER_01)", "Will (SPEAKER_02)"],
    summary="Tom, Sameer, and Will discuss RingCentral's AI APIs for conversational intelligence, highlighting capabilities in speech-to-text, interaction analysis, sentiment/emotion analysis, and the distinction between speaker diarization and identification. The program is currently in beta with general availability planned soon.",
    decisions=[
        Decision(decision="Program is currently in beta; public general availability coming soon", speaker_id="Tom (SPEAKER_00)")
    ],
    action_items=[
        ActionItem(
            task="Work toward general availability release to public and collect user feedback",
            assignee="Tom & Team",
            deadline="Soon (post-beta)",
            evidence="This program's in beta right now. We will soon be working towards releasing it generally available to the public.",
            status="in_progress"
        )
    ],
    unresolved_issues=[
        "Distinguishing speaker diarization (who spoke when) vs speaker identification (voice biometric label lookup)"
    ],
    important_points=[
        "Speech-to-text with automatic punctuation (commas, periods) for clean reporting",
        "Sentiment analysis using a 0 to 5 score for contact center supervisors",
        "Interaction analysis and emotional tone tracking across calls",
        "Audio vs Text AI API categories in RingCentral's platform"
    ],
    aligned_transcript=[
        AlignedSegment(
            start=s["start"],
            end=s["end"],
            speaker_id="Tom (SPEAKER_00)" if s["speaker_id"] == "SPEAKER_00" else ("Sameer (SPEAKER_01)" if s["speaker_id"] == "SPEAKER_01" else "Will (SPEAKER_02)"),
            text=s["text"]
        ) for s in orig["aligned_transcript"]
    ]
)

database.save_meeting(meeting)
print("Updated meeting_sample_run in SQLite database successfully!")
