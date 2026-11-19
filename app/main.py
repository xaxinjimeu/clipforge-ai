from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import uuid, shutil, subprocess, re, os, json, math

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
STORAGE = ROOT / "storage"
UPLOADS, OUTPUTS = STORAGE / "uploads", STORAGE / "outputs"
for p in (UPLOADS, OUTPUTS): p.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ClipForge AI v2")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
JOBS = {}

def ffmpeg(args, timeout=1200):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise HTTPException(500, "FFmpeg is missing. Install FFmpeg and add it to PATH.")
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Processing timed out.")
    if r.returncode:
        raise HTTPException(500, "Media processing failed: " + (r.stderr[-1000:] or "Unknown FFmpeg error"))
    return r

def duration_of(path):
    try:
        r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],capture_output=True,text=True,timeout=30)
        return float(r.stdout.strip())
    except Exception:
        raise HTTPException(400, "Could not read this video. Please try an MP4, MOV, WEBM or MKV file.")

def transcribe_with_whisper(video_path, work_dir):
    """Optional local speech transcription using faster-whisper."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None, "Speech AI is not installed. Install requirements-ai.txt to enable it."
    audio = work_dir / "audio.wav"
    ffmpeg(["ffmpeg","-y","-i",str(video_path),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(audio)])
    model_size = os.getenv("WHISPER_MODEL", "base")
    try:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(audio), vad_filter=True, word_timestamps=False)
        rows = []
        for seg in segments:
            txt = (seg.text or "").strip()
            if txt:
                rows.append({"start": float(seg.start), "end": float(seg.end), "text": txt})
        return rows, f"Transcribed speech using Whisper ({info.language or 'language unknown'})."
    except Exception as e:
        return None, "Whisper could not run: " + str(e)[:180]

def rank_speech_moments(segments, total_duration, count, clip_len):
    """Heuristic highlight ranking over real speech transcript segments."""
    if not segments:
        return []
    terms = {
        "high": ["secret","never","best","worst","amazing","incredible","shocking","truth","mistake","important","finally","money","love","hate","crazy","insane","imagine","surprise","wow","unbelievable"],
        "hook": ["how","why","what","here's","listen","watch","stop","remember","because","the reason","number one"],
        "filler": ["um","uh","you know","like","sort of","kind of"]
    }
    scored = []
    for s in segments:
        text = s["text"].lower()
        words = re.findall(r"\b[\w']+\b", text)
        if not words: continue
        score = min(len(words) / 12, 2.0)
        score += sum(1.25 for w in terms["high"] if w in text)
        score += sum(0.8 for w in terms["hook"] if w in text)
        score -= sum(0.55 for w in terms["filler"] if w in text)
        score += 0.9 if "?" in text or "!" in text else 0
        score += 0.35 if any(w.isupper() and len(w) > 2 for w in s["text"].split()) else 0
        # Prefer energetic, information-dense transcript passages, not simply the beginning.
        scored.append((score, s["start"], s["end"], s["text"]))
    if not scored: return []
    half = clip_len / 2
    candidates = []
    for score, start, end, txt in scored:
        center = (start + end) / 2
        a = max(0, min(total_duration - clip_len, center - half))
        b = min(total_duration, a + clip_len)
        candidates.append({"score": score, "start": a, "duration": b-a, "snippet": txt})
    candidates.sort(key=lambda x: x["score"], reverse=True)
    chosen = []
    for c in candidates:
        if all(abs(c["start"] - x["start"]) > clip_len * 0.65 for x in chosen):
            chosen.append(c)
        if len(chosen) >= count: break
    chosen.sort(key=lambda x: x["start"])
    return chosen

def fallback_moments(duration, count, clip_len):
    length = min(float(clip_len), duration)
    if duration <= length: return [{"start":0.0,"duration":length,"score":0.0,"snippet":"Sample segment"}]
    count = min(count, max(1, int(duration // max(1, length*.55))))
    if count <= 1: starts = [(duration-length)/2]
    else:
        gap=(duration-length)/(count-1); starts=[i*gap for i in range(count)]
    return [{"start":s,"duration":min(length,duration-s),"score":0.0,"snippet":"Sample segment"} for s in starts]

def video_filter(aspect):
    w,h={"9:16":(1080,1920),"1:1":(1080,1080),"16:9":(1920,1080)}[aspect]
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"

@app.get("/")
def home(): return FileResponse(STATIC/"index.html")

@app.get("/api/health")
def health():
    try:
        subprocess.run(["ffmpeg","-version"],capture_output=True,timeout=5)
        ff=True
    except Exception: ff=False
    try:
        import faster_whisper
        whisper=True
    except ImportError: whisper=False
    return {"ok":True,"ffmpeg":ff,"speech_ai":whisper,"version":"2.0"}

@app.post("/api/process")
async def process_video(video: UploadFile=File(...), clip_count:int=Form(3), clip_seconds:int=Form(30), aspect:str=Form("9:16")):
    if not video.filename: raise HTTPException(400,"Choose a video first.")
    suffix=Path(video.filename).suffix.lower()
    if suffix not in {".mp4",".mov",".m4v",".webm",".mkv"}: raise HTTPException(400,"Supported: MP4, MOV, M4V, WEBM, MKV.")
    if not 1<=clip_count<=10: raise HTTPException(400,"Choose 1–10 clips.")
    if not 10<=clip_seconds<=90: raise HTTPException(400,"Clip length must be 10–90 seconds.")
    if aspect not in {"9:16","1:1","16:9"}: raise HTTPException(400,"Invalid format.")
    job=uuid.uuid4().hex[:12]; source=UPLOADS/f"{job}{suffix}"
    with source.open("wb") as f: shutil.copyfileobj(video.file,f)
    duration=duration_of(source)
    if duration<5: source.unlink(missing_ok=True); raise HTTPException(400,"Video must be at least 5 seconds long.")
    work=OUTPUTS/job; work.mkdir(parents=True,exist_ok=True)
    transcript, ai_note=transcribe_with_whisper(source,work)
    moments=rank_speech_moments(transcript,duration,clip_count,clip_seconds) if transcript else []
    ai_used=bool(moments)
    if not moments: moments=fallback_moments(duration,clip_count,clip_seconds)
    clips=[]
    for i,m in enumerate(moments,1):
        name=f"clip_{i:02d}.mp4"; target=work/name
        ffmpeg(["ffmpeg","-y","-ss",f"{m['start']:.3f}","-i",str(source),"-t",f"{m['duration']:.3f}","-vf",video_filter(aspect),"-c:v","libx264","-preset","veryfast","-crf","23","-c:a","aac","-b:a","128k","-movflags","+faststart",str(target)])
        clips.append({"name":name,"start":round(m["start"],1),"duration":round(m["duration"],1),"score":round(m.get("score",0),2),"snippet":m.get("snippet",""),"url":f"/api/jobs/{job}/clips/{name}"})
    JOBS[job]={"job_id":job,"status":"completed","source_name":video.filename,"source_duration":round(duration,1),"aspect":aspect,"clips":clips,"ai_highlights":ai_used,"ai_note":ai_note if transcript is None else "Speech transcribed; clips ranked by transcript cues. Review before publishing.","transcript_available":bool(transcript)}
    source.unlink(missing_ok=True)
    try: (work/"audio.wav").unlink(missing_ok=True)
    except Exception: pass
    return JOBS[job]

@app.get("/api/jobs/{job}")
def get_job(job):
    if job not in JOBS: raise HTTPException(404,"Job not found.")
    return JOBS[job]

@app.get("/api/jobs/{job}/clips/{filename}")
def get_clip(job,filename):
    if not re.fullmatch(r"clip_\d{2}\.mp4",filename): raise HTTPException(400,"Invalid clip.")
    p=OUTPUTS/job/filename
    if not p.exists(): raise HTTPException(404,"Clip not found.")
    return FileResponse(p,media_type="video/mp4",filename=filename)
