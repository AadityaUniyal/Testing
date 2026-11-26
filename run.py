"""
Entry point — start the Meeting Intelligence web server.
Usage: python run.py
"""
import uvicorn

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════╗
    ║       🎙️  Meeting Intelligence Server           ║
    ║                                                  ║
    ║  Pipeline: Whisper → Pyannote → Qwen             ║
    ║  All models run locally on your GPU              ║
    ║                                                  ║
    ║  Open: http://localhost:8000                      ║
    ╚══════════════════════════════════════════════════╝
    """)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
