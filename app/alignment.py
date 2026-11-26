"""
Alignment Engine — Temporal intersection between Whisper text segments and Pyannote speaker turns.
Includes speaker name resolution to replace raw IDs (SPEAKER_00) with identified human names.
"""
import json
import os
from app.models import TranscriptSegment, SpeakerSegment, AlignedSegment


def align_transcript_speakers(
    transcript: list[TranscriptSegment],
    speakers: list[SpeakerSegment],
    output_dir: str,
    filename_base: str = "aligned",
) -> list[AlignedSegment]:
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

        aligned.append(AlignedSegment(
            start=round(seg.start, 2),
            end=round(seg.end, 2),
            speaker_id=best_speaker,
            text=seg.text.strip(),
        ))

    # Save aligned JSON for debugging and auditing
    output_path = os.path.join(output_dir, f"{filename_base}_aligned.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([a.model_dump() for a in aligned], f, indent=2, ensure_ascii=False)

    return aligned


def apply_speaker_mapping(aligned: list[AlignedSegment], mapping: dict[str, str]) -> list[AlignedSegment]:
    """
    Replace raw speaker IDs (e.g. SPEAKER_00) with identified human names
    (e.g. 'Tom (Host)') discovered by the LLM.
    """
    if not mapping:
        return aligned

    updated = []
    for seg in aligned:
        resolved_name = mapping.get(seg.speaker_id, seg.speaker_id)
        updated.append(AlignedSegment(
            start=seg.start,
            end=seg.end,
            speaker_id=resolved_name,
            text=seg.text
        ))
    return updated


def format_transcript_for_llm(aligned: list[AlignedSegment]) -> str:
    """Format aligned transcript into a clean, timestamped dialogue for the LLM."""
    lines = []
    for seg in aligned:
        start_m, start_s = divmod(int(seg.start), 60)
        end_m, end_s = divmod(int(seg.end), 60)
        lines.append(
            f"[{start_m:02d}:{start_s:02d} - {end_m:02d}:{end_s:02d}] "
            f"{seg.speaker_id}: {seg.text}"
        )
    return "\n".join(lines)
