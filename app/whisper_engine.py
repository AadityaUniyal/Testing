"""
Whisper Engine — runs whisper-cli.exe for speech-to-text transcription.
Outputs timestamped segments as JSON.
"""
import json
import os
import subprocess
import tempfile
from app.config import WHISPER_CLI, WHISPER_MODEL, WHISPER_LANGUAGE, WHISPER_THREADS
from app.models import TranscriptSegment


def check_whisper_ready() -> dict:
    """Verify whisper-cli and model are available."""
    return {
        "cli_exists": os.path.exists(WHISPER_CLI),
        "model_exists": os.path.exists(WHISPER_MODEL),
        "model_size_mb": round(os.path.getsize(WHISPER_MODEL) / (1024 * 1024), 1) if os.path.exists(WHISPER_MODEL) else 0,
    }


def transcribe(audio_path: str, output_dir: str, language: str = None) -> list[TranscriptSegment]:
    """
    Run whisper-cli on the audio file and return timestamped segments.
    
    Args:
        audio_path: Path to 16kHz mono WAV file.
        output_dir: Directory to store the JSON output.
        language: Language code or 'auto'. Defaults to config setting.
    
    Returns:
        List of TranscriptSegment with start/end times and text.
    """
    if not os.path.exists(WHISPER_CLI):
        raise FileNotFoundError(f"whisper-cli not found at {WHISPER_CLI}")
    if not os.path.exists(WHISPER_MODEL):
        raise FileNotFoundError(f"Whisper model not found at {WHISPER_MODEL}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    lang = language or WHISPER_LANGUAGE
    basename = os.path.splitext(os.path.basename(audio_path))[0]
    output_base = os.path.join(output_dir, basename)

    cmd = [
        WHISPER_CLI,
        "-m", WHISPER_MODEL,
        "-f", audio_path,
        "-l", lang,
        "-t", str(WHISPER_THREADS),
        "-oj",                        # output JSON
        "-of", output_base,           # output file base (whisper adds .json)
        "--no-prints",                 # suppress console noise
    ]

    print(f"[Whisper] Running: {' '.join(cmd[:6])}...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        raise RuntimeError(f"Whisper failed (code {result.returncode}): {result.stderr[:500]}")

    # Whisper outputs <basename>.json
    json_path = output_base + ".json"
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Whisper did not produce expected output at {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = []
    # whisper.cpp JSON format: {"transcription": [{"timestamps": {"from": "...", "to": "..."}, "text": "..."}]}
    for entry in data.get("transcription", []):
        timestamps = entry.get("timestamps", {})
        from_ts = _parse_timestamp(timestamps.get("from", "00:00:00.000"))
        to_ts = _parse_timestamp(timestamps.get("to", "00:00:00.000"))
        text = entry.get("text", "").strip()
        if text:
            segments.append(TranscriptSegment(start=from_ts, end=to_ts, text=text))

    print(f"[Whisper] Transcribed {len(segments)} segments from {audio_path}")
    return segments


def _parse_timestamp(ts: str) -> float:
    """Convert 'HH:MM:SS.mmm' or 'HH:MM:SS,mmm' to seconds."""
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
        return h * 3600 + m * 60 + s
    return 0.0
