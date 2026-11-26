"""
Audio Utilities — Universal audio decoding, normalization, and conversion.
Handles any audio format (MP3, WAV, M4A, AAC, FLAC, OGG, WEBM) without external FFmpeg binaries.
"""
import os
import numpy as np
import soundfile as sf
import scipy.signal


def load_and_normalize_audio(input_path: str, target_sr: int = 16000) -> tuple[np.ndarray, float]:
    """
    Load any audio file, convert to mono, resample to target_sr (16kHz),
    and apply peak normalization to optimize for Whisper and Pyannote.
    
    Returns:
        (audio_data: np.ndarray (float32, 1D), duration_seconds: float)
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Audio file does not exist: {input_path}")

    # Read audio using soundfile (supports WAV, MP3, FLAC, OGG, etc.)
    try:
        data, sr = sf.read(input_path, dtype='float32')
    except Exception as e:
        raise RuntimeError(f"Failed to read audio file '{input_path}': {e}")

    # 1. Convert to Mono
    if data.ndim > 1:
        data = data.mean(axis=1)

    # 2. Resample to target_sr if needed
    if sr != target_sr:
        num_target_samples = int(round(len(data) * float(target_sr) / float(sr)))
        data = scipy.signal.resample(data, num_target_samples).astype(np.float32)
        sr = target_sr

    # 3. Peak Normalization (prevent clipping while boosting quiet speech)
    max_val = np.max(np.abs(data))
    if max_val > 1e-4:
        # Scale to -1.0 dB (approx 0.89 amplitude)
        data = (data / max_val) * 0.89

    duration_seconds = len(data) / float(target_sr)
    return data, duration_seconds


def convert_to_16k_mono_wav(input_path: str, output_path: str) -> float:
    """
    Convert any audio file to 16kHz mono WAV file.
    
    Returns:
        duration_seconds: float
    """
    data, duration = load_and_normalize_audio(input_path, target_sr=16000)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    sf.write(output_path, data, 16000, subtype='PCM_16')
    return duration
