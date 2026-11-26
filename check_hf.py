from huggingface_hub import HfApi

api = HfApi()

for repo in ["Qwen/Qwen2.5-0.5B-Instruct-GGUF", "Qwen/Qwen2.5-1.5B-Instruct-GGUF", "gguf/Qwen3.5-0.8B-GGUF", "Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF"]:
    try:
        files = api.list_repo_files(repo)
        print(f"=== {repo} ===")
        for f in files:
            if "q4_k_m" in f.lower() or "q4" in f.lower():
                print(f"  {f}")
    except Exception as e:
        print(f"=== {repo} === Error: {e}")

try:
    p_files = api.list_repo_files("pyannote/speaker-diarization-community-1")
    print(f"\n=== pyannote/speaker-diarization-community-1 ===")
    print(f"Files count: {len(p_files)}")
    for f in p_files[:10]:
        print(f"  {f}")
except Exception as e:
    print(f"=== pyannote error: {e}")
