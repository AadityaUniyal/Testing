"""
Alignment Engine — Temporal intersection between Whisper text segments and Pyannote speaker turns.
Computes high-precision speaker dialogue turns, talk-time analytics (minutes and percentage per participant),
and resolves conversational identities (e.g. SPEAKER_00 -> Tom) as specified in Manent.
"""
import json
import os
from typing import List, Dict
from app.models import TranscriptSegment, SpeakerSegment, AlignedSegment, SpeakerStat


def format_seconds(seconds: float) -> str:
    """Format seconds into MM:SS timestamp."""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def format_duration_human(seconds: float) -> str:
    """Format seconds into human readable duration e.g. '2m 14s' or '45s'."""
    m, s = divmod(int(seconds), 60)
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def align_transcript_speakers(
    transcript: List[TranscriptSegment],
    speakers: List[SpeakerSegment],
    output_dir: str,
    filename_base: str = "aligned",
) -> List[AlignedSegment]:
    """
    Merge transcript segments with speaker segments by finding the
    speaker with the highest temporal overlap for each transcript segment.
    """
    aligned = []

    for seg in transcript:
        best_speaker = "SPEAKER_00"
        best_overlap = 0.0

        for spk in speakers:
            overlap_start = max(seg.start, spk.start)
            overlap_end = min(seg.end, spk.end)
            overlap = max(0.0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = spk.speaker_id

        start_ts = format_seconds(seg.start)
        end_ts = format_seconds(seg.end)
        aligned.append(AlignedSegment(
            start=round(seg.start, 2),
            end=round(seg.end, 2),
            timestamp_str=f"{start_ts} - {end_ts}",
            speaker_id=best_speaker,
            speaker_name=best_speaker,
            text=seg.text.strip(),
        ))

    # Save aligned JSON for auditing
    output_path = os.path.join(output_dir, f"{filename_base}_aligned.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([a.model_dump() for a in aligned], f, indent=2, ensure_ascii=False)

    return aligned


def apply_speaker_mapping(
    aligned: List[AlignedSegment],
    mapping: Dict[str, str]
) -> List[AlignedSegment]:
    """
    Apply resolved names to transcript segments without losing raw speaker IDs.
    """
    if not mapping:
        return aligned

    updated = []
    for seg in aligned:
        display_name = mapping.get(seg.speaker_id, seg.speaker_name or seg.speaker_id)
        updated.append(AlignedSegment(
            start=seg.start,
            end=seg.end,
            timestamp_str=seg.timestamp_str,
            speaker_id=seg.speaker_id,
            speaker_name=display_name,
            text=seg.text
        ))
    return updated


def calculate_speaker_stats(
    aligned: List[AlignedSegment],
    mapping: Dict[str, str] = None
) -> List[SpeakerStat]:
    """
    Calculates exact speaking time, turn counts, and percentages for each speaker.
    Matches Manent Figma design: 'Speaker 1 · 12:10', 'Speaker 2 · 12:32', talk percentages.
    """
    stats_map = {}
    total_speech_sec = 0.0
    mapping = mapping or {}

    for seg in aligned:
        spk = seg.speaker_id
        duration = max(0.1, seg.end - seg.start)
        total_speech_sec += duration

        if spk not in stats_map:
            display = mapping.get(spk, seg.speaker_name or spk)
            stats_map[spk] = {
                "name": display,
                "seconds": 0.0,
                "turns": 0
            }
        stats_map[spk]["seconds"] += duration
        stats_map[spk]["turns"] += 1

    stats_list = []
    for spk_id, data in stats_map.items():
        sec = data["seconds"]
        pct = (sec / total_speech_sec * 100.0) if total_speech_sec > 0 else 0.0
        stats_list.append(SpeakerStat(
            speaker_id=spk_id,
            name=data["name"],
            total_seconds=round(sec, 1),
            formatted_time=format_duration_human(sec),
            percentage=round(pct, 1),
            turn_count=data["turns"]
        ))

    # Sort by talk time descending
    stats_list.sort(key=lambda s: s.total_seconds, reverse=True)
    return stats_list


def format_transcript_for_llm(aligned: List[AlignedSegment]) -> str:
    """Format aligned transcript into a clean, timestamped dialogue for the LLM."""
    lines = []
    for seg in aligned:
        lines.append(f"[{seg.timestamp_str}] {seg.speaker_name or seg.speaker_id}: {seg.text}")
    return "\n".join(lines)
