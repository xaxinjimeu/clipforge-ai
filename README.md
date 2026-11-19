# ClipForge AI v2 — speech-aware highlight MVP

This version upgrades the original starter with optional local speech transcription and transcript-based highlight ranking.

## What works
- Upload MP4, MOV, M4V, WEBM or MKV
- Create 1–10 clips, 10–90 seconds each
- Export 9:16, 1:1 or 16:9 MP4
- If faster-whisper is installed, transcribe speech and rank candidate moments using transcript cues (questions, emphasis, hook phrases, information density)
- Download generated clips

## Important limitations
This is an early MVP, not a full OpusClip replacement. Transcript ranking is heuristic AI-assisted selection, not a trained virality predictor. It may miss visual jokes, action, silent highlights, context and speaker changes. Always review clips before publishing.
Animated word-level captions, face tracking, YouTube import, B-roll generation, accounts, cloud storage and social publishing are not included yet.

## Requirements
- Python 3.10+
- FFmpeg and FFprobe installed and available on PATH

## Install and run
1. Extract the ZIP.
2. Open a terminal in the extracted `clipforge_ai_v2` folder.
3. Create and activate a virtual environment:
   - Windows: `py -m venv .venv` then `.venv\\Scripts\\activate`
   - macOS/Linux: `python3 -m venv .venv` then `source .venv/bin/activate`
4. Install core dependencies:
   `pip install -r requirements.txt`
5. Optional: install speech AI:
   `pip install -r requirements-ai.txt`
   This installs faster-whisper and can download a model on first use. The default model is `base`; set `WHISPER_MODEL=small` for better accuracy if your machine can handle it.
6. Start:
   `uvicorn app.main:app --reload`
7. Open `http://127.0.0.1:8000`.

## Performance note
Local transcription and video rendering are CPU/RAM intensive. First model download requires internet. A desktop/laptop is recommended; a phone is not suitable for running the backend. To make this a public online service, deploy on a server with FFmpeg and sufficient compute, and add authentication, upload limits, private storage, background jobs and abuse protection.
