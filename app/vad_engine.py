"""
Voice Activity Detection (VAD) & Audio Optimization Engine.
Integrates Silero VAD v5 (2.1 MB ONNX) and Butterworth noise filtration:
1. Ultra-fast (<0.5ms) speech vs silence detection.
2. Filters low-frequency microphone rumble, AC hum, and keyboard taps.
3. Prevents Whisper hallucinations on silence.
4. Drops idle network packets to prevent iOS device heating and battery drain.
5. Computes speech-to-silence ratio telemetry for database documentation.
"""

import os
import wave
import numpy as np
import torch
import soundfile as sf
from typing import Dict, Any, Tuple
import logging

try:
    from scipy.signal import butter, sosfilt
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    from silero_vad import load_silero_vad, get_speech_timestamps
    HAS_SILERO = True
except ImportError:
    HAS_SILERO = False

logger = logging.getLogger("meeting_intelligence.vad")


class SileroVADDetector:
    """
    Lightweight, high-precision neural Voice Activity Detector using Silero VAD ONNX.
    Consumes ~2MB RAM and performs inference in under 0.5 milliseconds.
    """
    def __init__(self):
        self.model = None
        self.sample_rate = 16000
        self._init_model()

    def _init_model(self):
        if HAS_SILERO:
            try:
                self.model = load_silero_vad(onnx=True)
                logger.info("Silero VAD ONNX model loaded successfully.")
            except Exception as e:
                logger.warning(f"Failed to load Silero VAD ONNX model: {e}")
                self.model = None

    def reset(self):
        """Reset internal recurrent neural network states."""
        if self.model is not None and hasattr(self.model, "reset_states"):
            try:
                self.model.reset_states()
            except Exception:
                pass

    def is_speech_chunk(self, pcm_bytes: bytes, threshold: float = 0.40) -> Tuple[bool, float]:
        """
        Evaluate if a PCM 16-bit 16kHz audio chunk contains human voice.
        Returns (is_speech: bool, confidence: float).
        """
        if len(pcm_bytes) < 320:
            return False, 0.0

        audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        return self.is_speech_array(audio_np, threshold)

    def is_speech_array(self, audio_np: np.ndarray, threshold: float = 0.40) -> Tuple[bool, float]:
        """Evaluate float32 normalized [-1.0, 1.0] audio array."""
        if len(audio_np) == 0:
            return False, 0.0

        # Fast RMS energy check first (cuts unnecessary inference for dead silence)
        rms = np.sqrt(np.mean(audio_np ** 2) + 1e-9)
        if rms < 0.004:  # Below ~ -48 dBFS
            return False, 0.0

        if self.model is None:
            # Fallback heuristic: energy + spectral zero crossing
            zcr = np.mean(np.diff(np.sign(audio_np)) != 0)
            is_voice = rms > 0.015 and (0.04 < zcr < 0.45)
            conf = min(1.0, rms * 15.0) if is_voice else 0.1
            return is_voice, float(conf)

        # Silero VAD expects 512-sample chunks for 16kHz
        chunk_size = 512
        confidences = []

        for i in range(0, len(audio_np), chunk_size):
            chunk = audio_np[i:i + chunk_size]
            if len(chunk) < chunk_size:
                chunk = np.pad(chunk, (0, chunk_size - len(chunk)))

            chunk_t = torch.from_numpy(chunk.astype(np.float32))
            try:
                prob = self.model(chunk_t, self.sample_rate).item()
                confidences.append(prob)
            except Exception:
                pass

        if not confidences:
            return False, 0.0

        max_conf = max(confidences)
        is_speech = max_conf >= threshold
        return is_speech, round(max_conf, 3)


# Global singleton instance
_vad_detector = SileroVADDetector()


def get_vad_detector() -> SileroVADDetector:
    return _vad_detector


def filter_audio_noise(audio_np: np.ndarray, sample_rate: int = 16000, cutoff_hz: float = 80.0) -> np.ndarray:
    """
    Applies high-pass Butterworth filter to eliminate table rumble, handling noise,
    and HVAC 50/60Hz electrical hum.
    """
    if not HAS_SCIPY or len(audio_np) < 64:
        return audio_np

    try:
        sos = butter(4, cutoff_hz, btype='highpass', fs=sample_rate, output='sos')
        filtered = sosfilt(sos, audio_np)
        return filtered.astype(audio_np.dtype)
    except Exception:
        return audio_np


def profile_audio_speech(audio_path: str, threshold: float = 0.40) -> Dict[str, Any]:
    """
    Scan entire audio file and compute detailed speech vs silence profile.
    Used for execution telemetry and database performance tracking.
    """
    if not os.path.exists(audio_path):
        return {
            "total_duration_sec": 0.0,
            "speech_duration_sec": 0.0,
            "silence_duration_sec": 0.0,
            "speech_ratio": 0.0,
            "silence_percentage": 0.0
        }

    try:
        data, sr = sf.read(audio_path, dtype='float32')
        if data.ndim > 1:
            data = np.mean(data, axis=1)

        total_duration = len(data) / sr

        # Resample to 16kHz if needed
        if sr != 16000 and HAS_SCIPY:
            from scipy.signal import resample_poly
            from math import gcd
            g = gcd(16000, sr)
            data = resample_poly(data, 16000 // g, sr // g)
            sr = 16000

        wav_t = torch.from_numpy(data.astype(np.float32))

        detector = get_vad_detector()
        if detector.model is not None and HAS_SILERO:
            timestamps = get_speech_timestamps(wav_t, detector.model, sampling_rate=16000, threshold=threshold)
            speech_samples = sum(t['end'] - t['start'] for t in timestamps)
            speech_duration = round(speech_samples / 16000.0, 2)
        else:
            # Energy heuristic fallback
            frame_len = int(sr * 0.03)  # 30ms
            speech_frames = 0
            total_frames = len(data) // frame_len
            for i in range(total_frames):
                frame = data[i * frame_len:(i + 1) * frame_len]
                rms = np.sqrt(np.mean(frame ** 2) + 1e-9)
                if rms > 0.015:
                    speech_frames += 1
            speech_duration = round((speech_frames * frame_len) / sr, 2)

        silence_duration = round(max(0.0, total_duration - speech_duration), 2)
        speech_ratio = round(speech_duration / total_duration, 3) if total_duration > 0 else 0.0
        silence_pct = round((silence_duration / total_duration) * 100.0, 1) if total_duration > 0 else 0.0

        return {
            "total_duration_sec": round(total_duration, 2),
            "speech_duration_sec": speech_duration,
            "silence_duration_sec": silence_duration,
            "speech_ratio": speech_ratio,
            "silence_percentage": silence_pct
        }
    except Exception as e:
        logger.warning(f"Error profiling audio VAD: {e}")
        return {
            "total_duration_sec": 0.0,
            "speech_duration_sec": 0.0,
            "silence_duration_sec": 0.0,
            "speech_ratio": 0.0,
            "silence_percentage": 0.0
        }
