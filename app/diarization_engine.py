"""
Diarization Engine — runs Pyannote Community-1 for speaker identification.
Uses in-memory PyTorch tensor loaded via soundfile to bypass torchcodec/FFmpeg.
Uses CUDA GPU acceleration when available for blazing-fast inference (~5-10s).
"""
import json
import os
import torch
import soundfile as sf
from app.config import PYANNOTE_MODEL, MAX_SPEAKERS
from app.models import SpeakerSegment

_pipeline = None


def check_diarization_ready() -> dict:
    model_dir = PYANNOTE_MODEL
    config_exists = os.path.exists(os.path.join(model_dir, "config.yaml"))
    seg_exists = os.path.exists(os.path.join(model_dir, "segmentation", "pytorch_model.bin"))
    emb_exists = os.path.exists(os.path.join(model_dir, "embedding", "pytorch_model.bin"))
    return {
        "config_exists": config_exists,
        "segmentation_model": seg_exists,
        "embedding_model": emb_exists,
    }


def _load_pipeline():
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    from pyannote.audio import Pipeline

    config_path = os.path.join(PYANNOTE_MODEL, "config.yaml")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Pyannote config not found at {config_path}")

    print("[Diarization] Loading Pyannote Community-1 pipeline...")
    _pipeline = Pipeline.from_pretrained(PYANNOTE_MODEL)
    
    if torch.cuda.is_available():
        print("[Diarization] Activating CUDA GPU acceleration for Pyannote...")
        try:
            _pipeline.to(torch.device("cuda"))
        except Exception as e:
            print(f"[Diarization] CUDA init warning ({e}), continuing on CPU.")

    return _pipeline


def unload_pipeline():
    global _pipeline
    if _pipeline is not None:
        del _pipeline
        _pipeline = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def diarize(audio_path: str, output_dir: str,
            min_speakers: int = 2, max_speakers: int = None) -> list[SpeakerSegment]:
    """
    Run speaker diarization on a 16kHz WAV file.
    Loads waveform into memory via soundfile to bypass external FFmpeg requirements.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    max_spk = max_speakers or MAX_SPEAKERS
    pipeline = _load_pipeline()

    # Load audio into memory as float32 torch tensor (channels, time)
    data, sr = sf.read(audio_path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    
    # Device matching
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    waveform = torch.from_numpy(data).float().unsqueeze(0).to(device)

    print(f"[Diarization] Processing {audio_path} ({len(data)/sr:.1f}s) on {device}...")
    diarization_output = pipeline(
        {"waveform": waveform, "sample_rate": sr},
        min_speakers=min_speakers,
        max_speakers=max_spk,
    )

    segments = []
    # Pyannote Community-1 outputs DiarizeOutput with speaker_diarization annotation
    annotation = getattr(diarization_output, "speaker_diarization", diarization_output)

    if hasattr(annotation, "itertracks"):
        iterator = annotation.itertracks(yield_label=True)
        for turn, _, speaker in iterator:
            segments.append(SpeakerSegment(
                speaker_id=speaker,
                start=round(turn.start, 3),
                end=round(turn.end, 3),
            ))
    else:
        for turn, speaker in annotation:
            segments.append(SpeakerSegment(
                speaker_id=speaker,
                start=round(turn.start, 3),
                end=round(turn.end, 3),
            ))

    # Save to JSON
    basename = os.path.splitext(os.path.basename(audio_path))[0]
    output_path = os.path.join(output_dir, f"{basename}_diarization.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([s.model_dump() for s in segments], f, indent=2, ensure_ascii=False)

    unique_speakers = list(set(s.speaker_id for s in segments))
    print(f"[Diarization] Found {len(unique_speakers)} speakers, {len(segments)} segments.")

    return segments
