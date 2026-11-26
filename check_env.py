import sys
import os

print(f"Python Executable: {sys.executable}")
print(f"Python Version: {sys.version}")

# Check PyTorch & CUDA
try:
    import torch
    print(f"PyTorch Version: {torch.__version__}")
    print(f"CUDA Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"Device Name: {torch.cuda.get_device_name(0)}")
        print(f"CUDA Version: {torch.version.cuda}")
except Exception as e:
    print(f"PyTorch Check Failed: {e}")

# Check pyannote.audio
try:
    import pyannote.audio
    print(f"pyannote.audio Version: {pyannote.audio.__version__}")
except Exception as e:
    print(f"pyannote.audio Check Failed: {e}")

# Check huggingface_hub
try:
    import huggingface_hub
    print(f"huggingface_hub Version: {huggingface_hub.__version__}")
except Exception as e:
    print(f"huggingface_hub Check Failed: {e}")

# Search Downloads for Whisper Model
downloads = os.path.join(os.environ.get("USERPROFILE", ""), "Downloads")
print(f"\nSearching for Whisper model in: {downloads}")
found = []
if os.path.exists(downloads):
    for root, dirs, files in os.walk(downloads):
        for f in files:
            lower_name = f.lower()
            if any(k in lower_name for k in ["whisper", "turbo", "large-v3", "ggml"]) or f.endswith(".bin"):
                full_p = os.path.join(root, f)
                try:
                    size_mb = os.path.getsize(full_p) / (1024 * 1024)
                    found.append((f, size_mb, full_p))
                except Exception:
                    pass

if found:
    print(f"Found {len(found)} candidate model files:")
    for name, size, path in found:
        print(f" - {name} ({size:.1f} MB) -> {path}")
else:
    print("No matching Whisper files found in Downloads.")
