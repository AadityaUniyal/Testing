import os
import shutil
import urllib.request
import json
from huggingface_hub import hf_hub_download, snapshot_download

BASE_DIR = r"E:\TESTING"
os.chdir(BASE_DIR)

# 1. Ensure folders exist
for folder in [
    r"models\whisper",
    r"models\pyannote",
    r"models\qwen",
    r"audio\input",
    r"audio\processed",
    r"transcripts",
    r"results",
    r"tools\whisper"
]:
    os.makedirs(os.path.join(BASE_DIR, folder), exist_ok=True)

# 2. Link or copy Whisper model from Downloads
whisper_src = os.path.join(os.environ.get("USERPROFILE", ""), "Downloads", "ggml-large-v3-turbo.bin")
whisper_dst = os.path.join(BASE_DIR, "models", "whisper", "ggml-large-v3-turbo.bin")

if os.path.exists(whisper_src) and not os.path.exists(whisper_dst):
    print("Linking Whisper model...")
    try:
        os.link(whisper_src, whisper_dst)
        print("Hardlink created successfully!")
    except Exception as e:
        print(f"Hardlink failed ({e}), copying file...")
        shutil.copy2(whisper_src, whisper_dst)
        print("Copied successfully!")

if os.path.exists(whisper_dst):
    size_mb = os.path.getsize(whisper_dst) / (1024 * 1024)
    print(f"[Model 1] Whisper model ready: {whisper_dst} ({size_mb:.1f} MB)")
else:
    print("[Model 1] Whisper model not found at destination!")

# 3. Download Qwen model
qwen_file = "qwen3.5-0.8b-Q4_K_M.gguf"
qwen_dst = os.path.join(BASE_DIR, "models", "qwen", qwen_file)

if not os.path.exists(qwen_dst):
    print(f"\n[Model 2] Downloading Qwen model ({qwen_file})...")
    try:
        downloaded_path = hf_hub_download(
            repo_id="gguf/Qwen3.5-0.8B-GGUF",
            filename=qwen_file,
            local_dir=os.path.join(BASE_DIR, "models", "qwen")
        )
        print(f"[Model 2] Qwen downloaded successfully: {downloaded_path}")
    except Exception as e:
        print(f"[Model 2] Failed to download Qwen: {e}")
else:
    size_mb = os.path.getsize(qwen_dst) / (1024 * 1024)
    print(f"[Model 2] Qwen model already present: {qwen_dst} ({size_mb:.1f} MB)")

# 4. Check Pyannote Community-1 download
pyannote_dir = os.path.join(BASE_DIR, "models", "pyannote", "community-1")
print(f"\n[Model 3] Checking Pyannote Community-1...")
try:
    snapshot_path = snapshot_download(
        repo_id="pyannote/speaker-diarization-community-1",
        local_dir=pyannote_dir
    )
    print(f"[Model 3] Pyannote Community-1 ready in: {snapshot_path}")
except Exception as e:
    print(f"[Model 3] Pyannote Community-1 download notice: {e}")

# 5. Check whisper.cpp prebuilt releases
print("\nChecking latest whisper.cpp GitHub releases...")
try:
    req = urllib.request.Request(
        "https://api.github.com/repos/ggml-org/whisper.cpp/releases/latest",
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        tag = data.get("tag_name")
        print(f"Latest whisper.cpp release: {tag}")
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if "win" in name.lower() or "cuda" in name.lower():
                print(f"  Asset: {name} -> {asset.get('browser_download_url')}")
except Exception as e:
    print(f"Error checking whisper.cpp release: {e}")
