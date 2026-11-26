"""
Generate Benchmark Audio Suite (10 Diverse Variants)
Creates realistic multi-speaker conversation audio files covering:
- 2, 3, and 4 speaker counts
- Fast standups, long planning, retrospectives
- High-action tasks with explicit assignees & deadlines
- Strategic debates with consensus decisions
- Multi-accent dialogues (UK, US, Indian)
- Natural conversation intervals
"""

import asyncio
import os
import shutil
import tempfile
import numpy as np
import soundfile as sf
import edge_tts

AUDIO_INPUT_DIR = r"E:\TESTING\audio\input"
os.makedirs(AUDIO_INPUT_DIR, exist_ok=True)

# Define voice profiles
VOICES = {
    # US English
    "sarah": "en-US-JennyNeural",
    "alex": "en-US-GuyNeural",
    "priya": "en-IN-NeerjaNeural",
    "elena": "en-US-AriaNeural",
    "david": "en-US-ChristopherNeural",
    "marcus": "en-US-EricNeural",
    "chloe": "en-US-MichelleNeural",
    "jordan": "en-US-RogerNeural",
    "rachel": "en-US-SteffanNeural",
    "liam": "en-US-AndrewNeural",
    "sophia": "en-US-EmmaNeural",
    "viktor": "en-US-BrianNeural",
    "maya": "en-US-AvaNeural",
    "carlos": "en-US-GuyNeural",
    # International Accents
    "oliver_uk": "en-GB-RyanNeural",
    "aarav_in": "en-IN-PrabhatNeural",
    "jennifer_us": "en-US-JennyNeural",
    # Brainstorm
    "hannah": "en-US-AnaNeural",
    "noah": "en-US-EricNeural",
    # 1-on-1 Consultation
    "dr_aris": "en-US-ChristopherNeural",
    "nathan": "en-US-GuyNeural",
    # Post-Mortem
    "kevin": "en-US-BrianNeural",
    "nina": "en-US-AriaNeural",
    "daniel": "en-US-RogerNeural"
}

# Dialogues for variants 3 through 10
SCENARIOS = {
    "bench_03_daily_standup_3spk.wav": [
        ("sarah", "Morning team. Let's do our quick daily standup. Alex, what's your update on the auth service?"),
        ("alex", "Hey Sarah. Yesterday I finished the token refresh logic. Today I'm fixing the OAuth callback bug. No blockers on my end."),
        ("sarah", "Great. Priya, how is the end-to-end testing looking?"),
        ("priya", "Good morning. I ran regression tests on the staging environment. Found two minor visual glitches in the dashboard, but the core pipeline is solid."),
        ("sarah", "Awesome. Alex, please review Priya's PR before lunch. Let's aim for a code freeze by 4 PM today."),
        ("alex", "Will do, I'll review it right after standup."),
        ("priya", "Thanks Alex, sounds good.")
    ],
    "bench_04_sprint_planning_4spk.wav": [
        ("elena", "Welcome everyone to Sprint 42 planning. David, can you walk us through the high-priority architecture items?"),
        ("david", "Sure Elena. We need to migrate our database connection pool to Supabase PostgREST. Marcus, how long will the schema migration take?"),
        ("marcus", "I estimate about two days. I'll need to write the migration script and test foreign key constraints on staging."),
        ("chloe", "From the frontend perspective, we need the new WebSocket endpoints for real-time transcription streaming."),
        ("elena", "Okay, let's make that a priority. Marcus, take ownership of the PostgREST migration. Chloe, start the WebSocket hook integration."),
        ("david", "Agreed. Let's set our sprint goal as sub-second latency for the entire audio pipeline."),
        ("marcus", "Understood. I will have the initial PR up by Wednesday."),
        ("chloe", "I'll align the UI components by Thursday morning.")
    ],
    "bench_05_action_heavy_ops_4spk.wav": [
        ("jordan", "Alright team, we have strict deliverables before Friday's enterprise client demo. Let's lock in assignments."),
        ("rachel", "I will coordinate the release branch cut. Jordan, I need Liam to ensure cloud IAM roles are locked down."),
        ("liam", "I can handle that. I will finalize the AWS and Supabase IAM policies by tomorrow noon, November 27th."),
        ("sophia", "Security-wise, I must complete the SOC2 audit checklist for customer audio retention. I will submit the report by Friday at 5 PM."),
        ("jordan", "Excellent. Rachel, please freeze the staging environment tomorrow at 6 PM. Liam, send the signed policy document to Sophia once ready."),
        ("liam", "Understood. Delivery by Wednesday noon confirmed."),
        ("sophia", "Received. I will include it in the final audit package.")
    ],
    "bench_06_strategic_decisions_3spk.wav": [
        ("viktor", "Thanks for joining Carlos and Maya. We have to decide between DynamoDB, raw Postgres, and Supabase for our intelligence backend."),
        ("maya", "I've benchmarked all three. DynamoDB is fast for key-value, but querying complex speaker stats and relational action items becomes painful."),
        ("carlos", "Supabase gives us managed Postgres, PostgREST API over port 443, and Row Level Security out of the box."),
        ("maya", "Exactly. And we get foreign key integrity between meetings, speakers, and transcripts without building custom layers."),
        ("viktor", "So the consensus is Supabase with local SQLite fallback. Do we all agree?"),
        ("carlos", "Yes, let's officially resolve that Supabase is our primary cloud database."),
        ("maya", "Agreed. What about the GraphQL layer?"),
        ("viktor", "We will defer GraphQL to the next quarter. We'll stick to REST and WebSockets for now.")
    ],
    "bench_07_international_accents_3spk.wav": [
        ("oliver_uk", "Cheerio everyone. Looking at our cross-region telemetry from London and Frankfurt, we are noticing slight latency spikes."),
        ("aarav_in", "Namaste Oliver. From our Mumbai data center, the connection to Singapore Supabase cluster is running well under forty milliseconds."),
        ("jennifer_us", "Hi Oliver and Aarav. North America East in Virginia is also stable. If Frankfurt is having routing issues, we can route traffic through Dublin."),
        ("oliver_uk", "Brilliant idea Jennifer. Aarav, could you run ping diagnostics from Mumbai to Dublin to compare transit times?"),
        ("aarav_in", "Sure Oliver, I will set up the automated ping scripts and share the latency matrix by end of day today."),
        ("jennifer_us", "Great, let's reconvene once Aarav shares the diagnostic numbers.")
    ],
    "bench_08_rapid_overlap_ux_3spk.wav": [
        ("hannah", "Quick sync on the mobile onboarding flow. Users are dropping off at step three."),
        ("noah", "I noticed that too! The microphone permission popup appears before explaining why we need it."),
        ("hannah", "Exactly Noah. If we explain live transcription benefits first, conversion will jump."),
        ("alex", "Totally agree. I can update the onboarding screens to show a visual wave animation before requesting mic access."),
        ("noah", "Yes! Make it engaging."),
        ("hannah", "Perfect Alex, push that change today so we can A-B test it tomorrow.")
    ],
    "bench_09_consultation_1on1_2spk.wav": [
        ("dr_aris", "Nathan, thank you for meeting. As a healthcare provider, HIPAA and patient confidentiality are paramount. Can this pipeline run 100% on premise without external internet calls?"),
        ("nathan", "Absolutely Dr. Aris. Whisper Turbo and Pyannote run entirely on your local GPU, and Qwen runs via local llama-server. All audio and patient transcripts are written to an encrypted local database."),
        ("dr_aris", "What about performance? Can it process a thirty minute clinical consultation in under two minutes?"),
        ("nathan", "Yes. On an Nvidia GPU, Whisper Turbo processes audio at approximately ten times real-time speed. A thirty minute recording takes under three minutes total."),
        ("dr_aris", "That meets our SLA. Let's proceed with an on-premise pilot deployment next week.")
    ],
    "bench_10_postmortem_retro_4spk.wav": [
        ("kevin", "Let's begin the retrospective for yesterday's API gateway outage. Nina, what was the timeline?"),
        ("nina", "At 14:15 UTC, error rates spiked to fifteen percent. SRE traced it to database connection pool exhaustion on the public endpoint."),
        ("daniel", "The root cause was unclosed connections during high-volume audio uploads. By 14:45 UTC, we deployed a hotfix with automatic connection pooling."),
        ("maya", "We need to ensure this cannot happen again under enterprise load. What are our preventative action items?"),
        ("kevin", "Daniel, implement strict connection timeout limits and health checks by Thursday."),
        ("nina", "I will configure automated alerts in Grafana for pool saturation above eighty percent."),
        ("maya", "Decision is approved. Let's document this in the incident postmortem repository.")
    ]
}

async def generate_speech_segment(text: str, voice: str, outfile: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(outfile)

async def build_scenario_audio(filename: str, dialogue: list):
    temp_dir = tempfile.mkdtemp()
    segment_wavs = []
    
    try:
        for idx, (speaker, text) in enumerate(dialogue):
            voice = VOICES.get(speaker, "en-US-JennyNeural")
            mp3_path = os.path.join(temp_dir, f"seg_{idx:03d}.mp3")
            await generate_speech_segment(text, voice, mp3_path)
            
            # Read audio and resample to 16kHz mono float32
            data, sr = sf.read(mp3_path)
            if data.ndim > 1:
                data = data.mean(axis=1)
            if sr != 16000:
                from scipy import signal
                num_samples = int(len(data) * 16000 / sr)
                data = signal.resample(data, num_samples)
            segment_wavs.append(data.astype(np.float32))
            
            # Add short natural pause between speakers (0.4 to 0.7 sec)
            pause_samples = int(16000 * 0.5)
            segment_wavs.append(np.zeros(pause_samples, dtype=np.float32))
        
        # Concatenate full conversation
        full_audio = np.concatenate(segment_wavs)
        # Peak normalize to -1 dB
        peak = np.max(np.abs(full_audio))
        if peak > 0:
            full_audio = full_audio / peak * 0.9
            
        out_path = os.path.join(AUDIO_INPUT_DIR, filename)
        sf.write(out_path, full_audio, 16000)
        dur = len(full_audio) / 16000.0
        print(f"[GENERATED] {filename}: {dur:.1f}s ({len(dialogue)} turns)")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

async def main():
    print("Generating benchmark audio suite...")
    
    # Copy existing verified real audios
    # 1. Tech APIs (RingCentral)
    src_rc = r"E:\TESTING\audio\input\meeting_sample.mp3"
    dst_rc = os.path.join(AUDIO_INPUT_DIR, "bench_01_tech_apis_3spk.mp3")
    if os.path.exists(src_rc) and not os.path.exists(dst_rc):
        shutil.copy2(src_rc, dst_rc)
        print(f"[COPIED] bench_01_tech_apis_3spk.mp3 from meeting_sample.mp3")
        
    # 2. Pyannote benchmark
    src_py = os.path.join(AUDIO_INPUT_DIR, "sample_pyannote.wav")
    dst_py = os.path.join(AUDIO_INPUT_DIR, "bench_02_pyannote_eval_room.wav")
    if os.path.exists(src_py) and not os.path.exists(dst_py):
        shutil.copy2(src_py, dst_py)
        print(f"[COPIED] bench_02_pyannote_eval_room.wav from sample_pyannote.wav")
        
    # Generate scenarios 3 through 10
    for filename, dialogue in SCENARIOS.items():
        out_path = os.path.join(AUDIO_INPUT_DIR, filename)
        if not os.path.exists(out_path):
            await build_scenario_audio(filename, dialogue)
        else:
            print(f"[EXISTS] {filename}")
            
    print("\nBenchmark Audio Suite ready in E:\\TESTING\\audio\\input!")

if __name__ == "__main__":
    asyncio.run(main())
