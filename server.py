import os
import json
import asyncio
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import Optional

from database import init_db, get_db, load_default_characters
from pipeline.scriptwriter import generate_script
from pipeline.scheduler import load_schedule as load_scheduler_config, save_schedule as save_scheduler_config, run_scheduled_production, scheduler_loop
from pipeline.voice import generate_all_scenes_audio, list_voices, get_available_xtts_voices
from pipeline.video_gen import generate_all_scenes_video
from pipeline.subtitles import generate_srt, generate_ass, generate_preview_ass, get_style_presets
from pipeline.assembler import assemble_video
from pipeline.trends import get_all_trends
from pipeline.thumbnail import generate_thumbnail
from pipeline.music import generate_ambient_track, mix_narration_with_music, get_mood_volume
from pipeline.analytics import calculate_video_stats, get_content_recommendations
from pipeline.autopilot import run_autopilot_cycle, get_autopilot_status
from pipeline.publisher import (add_to_schedule, load_schedule, is_youtube_configured,
                                authenticate_youtube, upload_to_youtube,
                                prepare_tiktok_package, prepare_instagram_package)
from pipeline.context import validate_context, validate_image, build_context_prompt, ContextValidationError

BASE_DIR = os.path.dirname(__file__)
SETTINGS_PATH = os.path.join(BASE_DIR, "config", "settings.json")
CHARACTERS_DIR = os.path.join(BASE_DIR, "config", "characters")

MAX_RETRIES = 3
RETRY_DELAY = 5


scheduler_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler_task
    await init_db()
    await load_default_characters()
    # Auto-start scheduler if enabled
    sched_config = load_scheduler_config()
    if sched_config.get("enabled", False):
        scheduler_task = asyncio.create_task(scheduler_loop())
    yield
    if scheduler_task and not scheduler_task.done():
        scheduler_task.cancel()


app = FastAPI(title="Video Factory", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/output", StaticFiles(directory=os.path.join(BASE_DIR, "output")), name="output")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Track running productions
active_productions = {}


# === MODELS ===

class CharacterCreate(BaseModel):
    name: str
    description: str = ""
    personality: str = ""
    voice_id: str = "en-US-GuyNeural"
    visual_prompt: str = ""
    sample_hooks: list = []
    language: str = "en"


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    personality: Optional[str] = None
    voice_id: Optional[str] = None
    visual_prompt: Optional[str] = None
    sample_hooks: Optional[list] = None
    language: Optional[str] = None


class VideoGenerate(BaseModel):
    character_id: int
    topic: str
    duration: int = 60
    language: str = "en"


class BatchGenerate(BaseModel):
    character_id: int
    topics: list  # list of strings
    duration: int = 60
    language: str = "en"


class SettingsUpdate(BaseModel):
    anthropic_api_key: Optional[str] = None
    fal_api_key: Optional[str] = None
    youtube_api_key: Optional[str] = None
    ollama_model: Optional[str] = None
    music_enabled: Optional[bool] = None
    music_mood: Optional[str] = None
    kokoro_speed: Optional[float] = None
    tts_rate: Optional[str] = None
    tts_pitch: Optional[str] = None
    fish_api_key: Optional[str] = None
    fish_model_id: Optional[str] = None


# === PAGES ===

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


# === CHARACTERS API ===

@app.get("/api/characters")
async def get_characters():
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM characters ORDER BY created_at DESC")
    await db.close()
    characters = []
    for r in rows:
        char = dict(r)
        try:
            char["sample_hooks"] = json.loads(char["sample_hooks"]) if char["sample_hooks"] else []
        except (json.JSONDecodeError, TypeError):
            char["sample_hooks"] = []
        characters.append(char)
    return characters


@app.post("/api/characters")
async def create_character(char: CharacterCreate):
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO characters (name, description, personality, voice_id, visual_prompt, sample_hooks, language)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (char.name, char.description, char.personality, char.voice_id,
         char.visual_prompt, json.dumps(char.sample_hooks), char.language),
    )
    await db.commit()
    char_id = cursor.lastrowid

    # Also save as JSON file
    char_data = char.model_dump()
    os.makedirs(CHARACTERS_DIR, exist_ok=True)
    safe_name = char.name.lower().replace(" ", "_")
    with open(os.path.join(CHARACTERS_DIR, f"{safe_name}.json"), "w", encoding="utf-8") as f:
        json.dump(char_data, f, indent=2, ensure_ascii=False)

    await db.close()
    return {"id": char_id, "message": f"Character '{char.name}' created"}


@app.put("/api/characters/{char_id}")
async def update_character(char_id: int, char: CharacterUpdate):
    db = await get_db()
    existing = await db.execute_fetchall("SELECT * FROM characters WHERE id = ?", (char_id,))
    if not existing:
        await db.close()
        raise HTTPException(status_code=404, detail="Character not found")

    updates = {}
    for field, value in char.model_dump(exclude_none=True).items():
        if field == "sample_hooks":
            updates[field] = json.dumps(value)
        else:
            updates[field] = value

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [char_id]
        await db.execute(f"UPDATE characters SET {set_clause} WHERE id = ?", values)
        await db.commit()

    await db.close()
    return {"message": "Character updated"}


@app.delete("/api/characters/{char_id}")
async def delete_character(char_id: int):
    db = await get_db()
    await db.execute("DELETE FROM characters WHERE id = ?", (char_id,))
    await db.commit()
    await db.close()
    return {"message": "Character deleted"}


# === VIDEOS API ===

@app.get("/api/videos")
async def get_videos():
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT v.*, c.name as character_name
           FROM videos v JOIN characters c ON v.character_id = c.id
           ORDER BY v.created_at DESC"""
    )
    await db.close()
    return [dict(r) for r in rows]


@app.get("/api/videos/{video_id}")
async def get_video(video_id: int):
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT v.*, c.name as character_name
           FROM videos v JOIN characters c ON v.character_id = c.id
           WHERE v.id = ?""",
        (video_id,),
    )
    if not rows:
        await db.close()
        raise HTTPException(status_code=404, detail="Video not found")

    video = dict(rows[0])
    try:
        video["script_json"] = json.loads(video["script_json"]) if video["script_json"] else None
    except (json.JSONDecodeError, TypeError):
        pass

    # Get production logs
    logs = await db.execute_fetchall(
        "SELECT * FROM production_log WHERE video_id = ? ORDER BY id", (video_id,)
    )
    video["logs"] = [dict(l) for l in logs]
    await db.close()
    return video


@app.delete("/api/videos/{video_id}")
async def delete_video(video_id: int):
    db = await get_db()
    # Get output path to delete file too
    rows = await db.execute_fetchall("SELECT output_path FROM videos WHERE id = ?", (video_id,))
    if rows and rows[0]["output_path"]:
        try:
            os.remove(rows[0]["output_path"])
        except OSError:
            pass
    await db.execute("DELETE FROM production_log WHERE video_id = ?", (video_id,))
    await db.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    await db.commit()
    await db.close()
    return {"message": "Video deleted"}


# === TRENDS API ===

@app.get("/api/trends")
async def api_get_trends(region: str = "US", niche: str = "horror"):
    """Get trending topics from YouTube, Google Trends, and Reddit."""
    try:
        trends = await get_all_trends(region, niche)
        return trends
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === PRODUCTION API ===

@app.post("/api/videos/generate-script")
async def api_generate_script(req: VideoGenerate):
    """Generate script only (for preview before full production)."""
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM characters WHERE id = ?", (req.character_id,))
    if not rows:
        await db.close()
        raise HTTPException(status_code=404, detail="Character not found")

    character = dict(rows[0])
    try:
        character["sample_hooks"] = json.loads(character["sample_hooks"]) if character["sample_hooks"] else []
    except (json.JSONDecodeError, TypeError):
        character["sample_hooks"] = []

    try:
        script = await generate_script(character, req.topic, req.duration, req.language)
    except Exception as e:
        await db.close()
        raise HTTPException(status_code=500, detail=str(e))

    # Save to DB as draft
    cursor = await db.execute(
        """INSERT INTO videos (character_id, title, topic, script_json, status, language, duration_target)
           VALUES (?, ?, ?, ?, 'draft', ?, ?)""",
        (req.character_id, script.get("title", req.topic), req.topic,
         json.dumps(script), req.language, req.duration),
    )
    await db.commit()
    video_id = cursor.lastrowid
    await db.close()

    return {"video_id": video_id, "script": script}


@app.post("/api/videos/manual-script")
async def api_manual_script(request: Request):
    """Save a manually pasted script (no API key needed)."""
    body = await request.json()
    script = body.get("script")
    character_id = body.get("character_id")
    language = body.get("language", "en")
    duration = body.get("duration", 60)

    if not script or not character_id:
        raise HTTPException(status_code=400, detail="script and character_id required")

    if "scenes" not in script:
        raise HTTPException(status_code=400, detail="Script must have 'scenes' array")

    db = await get_db()
    rows = await db.execute_fetchall("SELECT id FROM characters WHERE id = ?", (character_id,))
    if not rows:
        await db.close()
        raise HTTPException(status_code=404, detail="Character not found")

    cursor = await db.execute(
        """INSERT INTO videos (character_id, title, topic, script_json, status, language, duration_target)
           VALUES (?, ?, ?, ?, 'draft', ?, ?)""",
        (character_id, script.get("title", "Manual Script"), "manual",
         json.dumps(script), language, duration),
    )
    await db.commit()
    video_id = cursor.lastrowid
    await db.close()

    return {"video_id": video_id, "script": script}


@app.post("/api/videos/batch")
async def api_batch_generate(req: BatchGenerate):
    """Queue multiple videos for production."""
    if not req.topics:
        raise HTTPException(status_code=400, detail="No topics provided")

    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM characters WHERE id = ?", (req.character_id,))
    if not rows:
        await db.close()
        raise HTTPException(status_code=404, detail="Character not found")
    await db.close()

    video_ids = []
    for topic in req.topics[:10]:  # Max 10 at a time
        try:
            result = await api_generate_script(VideoGenerate(
                character_id=req.character_id,
                topic=topic,
                duration=req.duration,
                language=req.language,
            ))
            video_ids.append({"topic": topic, "video_id": result["video_id"], "status": "draft"})
        except Exception as e:
            video_ids.append({"topic": topic, "video_id": None, "status": "error", "error": str(e)})

    return {"batch": video_ids, "count": len(video_ids)}


@app.post("/api/videos/{video_id}/produce")
async def api_produce_video(video_id: int, request: Request):
    """
    Start full production pipeline for a video with an approved script.

    Body (optional):
        production_mode: "auto" (default, fal.ai) or "free" (Whisk + Grok manual)
    """
    if video_id in active_productions:
        raise HTTPException(status_code=409, detail="Production already in progress")

    # Parse optional production mode override from request body
    try:
        body = await request.json()
    except Exception:
        body = {}
    production_mode = body.get("production_mode")

    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT v.*, c.name as char_name, c.voice_id, c.visual_prompt as char_visual
           FROM videos v JOIN characters c ON v.character_id = c.id
           WHERE v.id = ?""",
        (video_id,),
    )
    if not rows:
        await db.close()
        raise HTTPException(status_code=404, detail="Video not found")

    video = dict(rows[0])
    await db.close()

    if not video["script_json"]:
        raise HTTPException(status_code=400, detail="No script found. Generate a script first.")

    # Start production in background, passing the mode override
    active_productions[video_id] = "running"
    asyncio.create_task(_run_production(video_id, video, production_mode=production_mode))

    return {
        "message": "Production started",
        "video_id": video_id,
        "production_mode": production_mode or "auto",
    }


@app.post("/api/videos/{video_id}/update-script")
async def api_update_script(video_id: int, request: Request):
    """Update the script for a video."""
    body = await request.json()
    script = body.get("script")
    if not script:
        raise HTTPException(status_code=400, detail="No script provided")

    db = await get_db()
    title = script.get("title", "")
    await db.execute(
        "UPDATE videos SET script_json = ?, title = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps(script), title, video_id),
    )
    await db.commit()
    await db.close()
    return {"message": "Script updated"}


@app.get("/api/videos/{video_id}/status")
async def api_video_status(video_id: int):
    """Get current production status."""
    db = await get_db()
    rows = await db.execute_fetchall("SELECT status, output_path FROM videos WHERE id = ?", (video_id,))
    if not rows:
        await db.close()
        raise HTTPException(status_code=404, detail="Video not found")

    video = dict(rows[0])
    logs = await db.execute_fetchall(
        "SELECT step, status, detail, cost_usd FROM production_log WHERE video_id = ? ORDER BY id DESC",
        (video_id,),
    )
    await db.close()

    total_cost = sum(float(l["cost_usd"] or 0) for l in logs)

    return {
        "status": video["status"],
        "output_path": video["output_path"],
        "is_active": video_id in active_productions,
        "total_cost_usd": round(total_cost, 4),
        "logs": [dict(l) for l in logs],
    }


@app.get("/api/videos/{video_id}/download")
async def api_download_video(video_id: int):
    """Download the final video file."""
    db = await get_db()
    rows = await db.execute_fetchall("SELECT output_path, title FROM videos WHERE id = ?", (video_id,))
    await db.close()
    if not rows or not rows[0]["output_path"]:
        raise HTTPException(status_code=404, detail="Video not ready")

    path = rows[0]["output_path"]
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Video file not found")

    filename = f"{rows[0]['title']}.mp4".replace(" ", "_")
    return FileResponse(path, filename=filename, media_type="video/mp4")


# === SETTINGS API ===

@app.get("/api/settings")
async def get_settings():
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        settings = json.load(f)
    # Mask API keys for display
    masked = dict(settings)
    for key in ["anthropic_api_key", "fal_api_key", "youtube_api_key", "fish_api_key"]:
        if masked.get(key):
            masked[key] = masked[key][:8] + "..." + masked[key][-4:]
    return masked


@app.post("/api/settings")
async def update_settings(req: SettingsUpdate):
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        settings = json.load(f)

    if req.anthropic_api_key is not None:
        settings["anthropic_api_key"] = req.anthropic_api_key
    if req.fal_api_key is not None:
        settings["fal_api_key"] = req.fal_api_key
    if req.youtube_api_key is not None:
        settings["youtube_api_key"] = req.youtube_api_key
    if req.ollama_model is not None:
        settings["ollama_model"] = req.ollama_model
    if req.music_enabled is not None:
        settings["music_enabled"] = req.music_enabled
    if req.music_mood is not None:
        settings["music_mood"] = req.music_mood
    if req.kokoro_speed is not None:
        settings["kokoro_speed"] = req.kokoro_speed
    if req.tts_rate is not None:
        settings["tts_rate"] = req.tts_rate
    if req.tts_pitch is not None:
        settings["tts_pitch"] = req.tts_pitch
    if req.fish_api_key is not None:
        settings["fish_api_key"] = req.fish_api_key
    if req.fish_model_id is not None:
        settings["fish_model_id"] = req.fish_model_id

    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)

    return {"message": "Settings updated"}


@app.get("/api/tts/benchmark")
async def api_tts_benchmark():
    """Return TTS engine benchmark data for the UI."""
    settings = json.load(open(SETTINGS_PATH, "r", encoding="utf-8"))
    return {
        "engines": [
            {
                "id": "fish",
                "name": "Fish Audio S2",
                "naturalness": 9.5,
                "spanish": 8.5,
                "speed": "2-5s/escena (API)",
                "cost": "Gratis (7 min/mes) | $11/mes ilimitado",
                "commercial": "Solo plan pago",
                "voice_clone": True,
                "local": False,
                "configured": bool(settings.get("fish_api_key")),
                "pros": ["Mejor calidad", "Voz casi humana", "Clonacion de voz"],
                "cons": ["Necesita internet", "Free tier limitado", "No comercial gratis"],
            },
            {
                "id": "xtts",
                "name": "XTTS v2 (Coqui)",
                "naturalness": 8.0,
                "spanish": 7.5,
                "speed": "15-30s/escena (CPU)",
                "cost": "Gratis",
                "commercial": "CPML license",
                "voice_clone": True,
                "local": True,
                "configured": True,
                "pros": ["Gratis", "Local", "Clona voces", "17 idiomas"],
                "cons": ["Lento en CPU", "A veces cambia idioma", "Necesita audio de referencia"],
            },
            {
                "id": "edge-tts",
                "name": "Edge-TTS (Microsoft)",
                "naturalness": 6.0,
                "spanish": 7.0,
                "speed": "1-2s/escena",
                "cost": "Gratis",
                "commercial": "Permitido",
                "voice_clone": False,
                "local": False,
                "configured": True,
                "pros": ["Ultra rapido", "Estable", "47+ voces", "Comercial OK"],
                "cons": ["Suena robotico", "Sin clonacion", "Necesita internet"],
            },
            {
                "id": "kokoro",
                "name": "Kokoro AI",
                "naturalness": 7.0,
                "spanish": 3.0,
                "speed": "3-5s/escena (CPU)",
                "cost": "Gratis",
                "commercial": "MIT license",
                "voice_clone": False,
                "local": True,
                "configured": True,
                "pros": ["Gratis", "Local", "Bueno en ingles", "MIT license"],
                "cons": ["Malo en espanol", "Sin clonacion", "Necesita espeak para ES"],
            },
            {
                "id": "elevenlabs",
                "name": "ElevenLabs (multilingual_v2)",
                "naturalness": 10.0,
                "spanish": 9.5,
                "speed": "2-3s/escena (API)",
                "cost": "Free 10K chars/mes | Starter $6/mes 30K chars",
                "commercial": "Solo plan pago (Starter+)",
                "voice_clone": True,
                "local": False,
                "configured": bool(settings.get("elevenlabs_api_key")),
                "pros": ["La mejor calidad del mercado", "Voz humana perfecta", "29 idiomas", "Free tier generoso"],
                "cons": ["Free tier sin licencia comercial", "Requiere internet"],
            },
        ]
    }


@app.post("/api/settings/raw")
async def update_settings_raw(request: Request):
    """Save full settings JSON (for XTTS and advanced settings)."""
    body = await request.json()
    # Preserve API keys that aren't being updated
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        current = json.load(f)
    # Merge: keep existing keys, update with new ones
    for key, val in body.items():
        current[key] = val
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
    return {"message": "Settings saved"}


# === VOICES API ===

@app.get("/api/voices/preview/{voice_id:path}")
async def preview_voice(voice_id: str):
    """Serve pre-generated voice preview audio."""
    preview_dir = os.path.join(BASE_DIR, "output", "voice_previews")

    # Check for kokoro preview
    if voice_id.startswith("kokoro:"):
        kokoro_id = voice_id.replace("kokoro:", "")
        wav_path = os.path.join(preview_dir, f"kokoro_{kokoro_id}.wav")
        if os.path.exists(wav_path):
            return FileResponse(wav_path, media_type="audio/wav")

    # Check for edge-tts preview
    mp3_path = os.path.join(preview_dir, f"{voice_id}.mp3")
    if os.path.exists(mp3_path):
        return FileResponse(mp3_path, media_type="audio/mpeg")

    raise HTTPException(status_code=404, detail=f"No preview for voice: {voice_id}")


# === XTTS VOICE MANAGEMENT ===

@app.get("/api/xtts/voices")
async def api_xtts_voices():
    """List available XTTS voice references."""
    return get_available_xtts_voices()


@app.post("/api/xtts/upload-voice")
async def api_xtts_upload_voice(request: Request):
    """Upload a voice reference audio file for XTTS cloning."""
    form = await request.form()
    audio_file = form.get("audio")
    voice_name = form.get("name", "custom")

    if not audio_file:
        raise HTTPException(status_code=400, detail="No audio file provided")

    voices_dir = os.path.join(BASE_DIR, "assets", "voices")
    os.makedirs(voices_dir, exist_ok=True)

    # Save uploaded file
    safe_name = "".join(c for c in voice_name if c.isalnum() or c in "_-").strip() or "custom"
    ext = os.path.splitext(audio_file.filename)[1] or ".wav"
    save_path = os.path.join(voices_dir, safe_name + ext)

    content = await audio_file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    return {"message": f"Voice '{safe_name}' uploaded", "voice_id": f"xtts:{safe_name}", "path": save_path}


@app.delete("/api/xtts/voices/{voice_name}")
async def api_xtts_delete_voice(voice_name: str):
    """Delete a voice reference."""
    voices_dir = os.path.join(BASE_DIR, "assets", "voices")
    for ext in [".wav", ".mp3", ".ogg", ".m4a"]:
        path = os.path.join(voices_dir, voice_name + ext)
        if os.path.exists(path):
            os.remove(path)
            return {"message": f"Voice '{voice_name}' deleted"}
    raise HTTPException(status_code=404, detail=f"Voice '{voice_name}' not found")


@app.post("/api/xtts/preview")
async def api_xtts_preview(request: Request):
    """Generate a preview with XTTS v2."""
    body = await request.json()
    text = body.get("text", "Esta es una prueba de voz con XTTS.")
    language = body.get("language", "es")
    voice_name = body.get("voice", "default")

    from pipeline.voice import generate_voice
    result = await generate_voice(
        text=text,
        voice_id=f"xtts:{voice_name}",
        output_filename="xtts_preview.mp3",
        language=language,
    )
    return FileResponse(result["path"], media_type="audio/mpeg")


@app.post("/api/xtts/record-voice")
async def api_xtts_record_voice(request: Request):
    """Save a recorded voice from the browser's microphone."""
    form = await request.form()
    audio_file = form.get("audio")
    voice_name = form.get("name", "recorded")

    if not audio_file:
        raise HTTPException(status_code=400, detail="No audio provided")

    voices_dir = os.path.join(BASE_DIR, "assets", "voices")
    os.makedirs(voices_dir, exist_ok=True)

    safe_name = "".join(c for c in voice_name if c.isalnum() or c in "_-").strip() or "recorded"
    raw_path = os.path.join(voices_dir, safe_name + "_raw.webm")
    final_path = os.path.join(voices_dir, safe_name + ".wav")

    content = await audio_file.read()
    with open(raw_path, "wb") as f:
        f.write(content)

    # Convert to WAV (browser sends webm/ogg)
    import subprocess
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", raw_path, "-ar", "22050", "-ac", "1", final_path],
        capture_output=True, text=True,
    )
    try:
        os.remove(raw_path)
    except OSError:
        pass

    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"FFmpeg error: {proc.stderr[:200]}")

    return {"message": f"Voice '{safe_name}' recorded", "voice_id": f"xtts:{safe_name}", "path": final_path}


@app.get("/api/voices/{language}")
async def get_voices(language: str):
    voices = await list_voices(language)
    return voices


@app.get("/api/voice-preview/{voice_id:path}")
async def preview_voice(voice_id: str):
    """Get or generate a voice preview audio sample."""
    preview_dir = os.path.join(BASE_DIR, "output", "voice_previews")
    os.makedirs(preview_dir, exist_ok=True)

    # ─── ElevenLabs ─────────────────────────────────────────────
    # Use the pre-rendered preview_url from /v1/voices/{id} —
    # FREE, doesn't touch the user's character quota. Cache locally.
    if voice_id.startswith("elevenlabs:"):
        eleven_id = voice_id.replace("elevenlabs:", "").strip()
        # Sanitize filename
        safe_id = "".join(c for c in eleven_id if c.isalnum() or c in "-_")
        cache_path = os.path.join(preview_dir, f"elevenlabs_{safe_id}.mp3")
        if os.path.exists(cache_path):
            return FileResponse(cache_path, media_type="audio/mpeg")

        # Fetch voice metadata to get preview_url
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            settings = json.load(f)
        api_key = settings.get("elevenlabs_api_key", "")
        if not api_key:
            raise HTTPException(status_code=400,
                detail="ElevenLabs API key not configured in settings.")

        import httpx
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    f"https://api.elevenlabs.io/v1/voices/{eleven_id}",
                    headers={"xi-api-key": api_key},
                )
                if r.status_code != 200:
                    raise HTTPException(status_code=400,
                        detail=f"ElevenLabs voice lookup failed ({r.status_code}): {r.text[:150]}")
                voice_data = r.json()
                preview_url = voice_data.get("preview_url")
                if not preview_url:
                    raise HTTPException(status_code=404,
                        detail=f"No preview available for voice '{eleven_id}'")

                # Download the pre-rendered preview (free, no credit cost)
                pr = await client.get(preview_url)
                if pr.status_code != 200:
                    raise HTTPException(status_code=500,
                        detail="Failed to download preview audio")
                with open(cache_path, "wb") as fout:
                    fout.write(pr.content)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"ElevenLabs preview error: {e}")

        return FileResponse(cache_path, media_type="audio/mpeg")

    # ─── Kokoro voices (wav files) ──────────────────────────────
    if voice_id.startswith("kokoro:"):
        kokoro_name = voice_id.replace("kokoro:", "")
        wav_path = os.path.join(preview_dir, f"kokoro_{kokoro_name}.wav")
        if os.path.exists(wav_path):
            return FileResponse(wav_path, media_type="audio/wav")
        # Generate on the fly
        try:
            from pipeline.voice import generate_voice
            result = await generate_voice(
                "Sit down and listen carefully. This is a story that will change how you see everything.",
                voice_id, f"preview_{kokoro_name}.mp3",
            )
            return FileResponse(result["path"], media_type="audio/mpeg")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Voice error: {e}")

    # ─── Edge-TTS voices ────────────────────────────────────────
    preview_path = os.path.join(preview_dir, f"{voice_id}.mp3")
    if not os.path.exists(preview_path):
        import edge_tts
        text = "Sit down and listen carefully. This is a story that will change how you see everything around you. Are you ready?"
        try:
            comm = edge_tts.Communicate(text, voice_id, rate="-8%", pitch="-3Hz")
            await comm.save(preview_path)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Voice not available: {e}")

    return FileResponse(preview_path, media_type="audio/mpeg")


# === UPLOAD API ===

@app.post("/api/upload/image")
async def upload_image(request: Request):
    """Upload a context image. Returns path and validation info."""
    from fastapi import UploadFile, File
    import uuid

    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    # Save to uploads dir
    uploads_dir = os.path.join(BASE_DIR, "output", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    filename = f"{uuid.uuid4().hex[:12]}.{ext}"
    filepath = os.path.join(uploads_dir, filename)

    contents = await file.read()
    with open(filepath, "wb") as f:
        f.write(contents)

    # Validate
    try:
        info = validate_image(filepath)
        return {
            "status": "ok",
            "path": filepath,
            "filename": filename,
            "url": f"/output/uploads/{filename}",
            **info,
        }
    except ContextValidationError as e:
        os.remove(filepath)
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/upload/list")
async def list_uploads():
    """List uploaded context images."""
    uploads_dir = os.path.join(BASE_DIR, "output", "uploads")
    if not os.path.exists(uploads_dir):
        return []
    files = []
    for f in os.listdir(uploads_dir):
        path = os.path.join(uploads_dir, f)
        if os.path.isfile(path):
            size_mb = os.path.getsize(path) / (1024 * 1024)
            files.append({
                "filename": f,
                "path": path,
                "url": f"/output/uploads/{f}",
                "size_mb": round(size_mb, 2),
            })
    return files


# === SCRIPT TEMPLATES API ===

@app.get("/api/templates")
async def get_templates():
    """Get all saved script templates."""
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT st.*, c.name as character_name
           FROM script_templates st
           LEFT JOIN characters c ON st.character_id = c.id
           ORDER BY st.use_count DESC, st.created_at DESC"""
    )
    await db.close()
    results = []
    for r in rows:
        d = dict(r)
        try:
            d["script_json"] = json.loads(d["script_json"]) if d["script_json"] else {}
        except (json.JSONDecodeError, TypeError):
            pass
        results.append(d)
    return results


@app.post("/api/templates")
async def save_template(request: Request):
    """Save a script as a reusable template."""
    body = await request.json()
    name = body.get("name", "")
    script = body.get("script")
    character_id = body.get("character_id")
    language = body.get("language", "en")
    tags = body.get("tags", "")

    if not name or not script:
        raise HTTPException(status_code=400, detail="name and script are required")

    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO script_templates (name, character_id, script_json, language, tags)
           VALUES (?, ?, ?, ?, ?)""",
        (name, character_id, json.dumps(script), language, tags),
    )
    await db.commit()
    template_id = cursor.lastrowid
    await db.close()
    return {"id": template_id, "message": f"Template '{name}' saved"}


@app.post("/api/templates/{template_id}/use")
async def use_template(template_id: int):
    """Load a template for use and increment use count."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM script_templates WHERE id = ?", (template_id,)
    )
    if not rows:
        await db.close()
        raise HTTPException(status_code=404, detail="Template not found")

    await db.execute(
        "UPDATE script_templates SET use_count = use_count + 1 WHERE id = ?",
        (template_id,),
    )
    await db.commit()
    await db.close()

    template = dict(rows[0])
    try:
        template["script_json"] = json.loads(template["script_json"])
    except (json.JSONDecodeError, TypeError):
        pass
    return template


@app.delete("/api/templates/{template_id}")
async def delete_template(template_id: int):
    db = await get_db()
    await db.execute("DELETE FROM script_templates WHERE id = ?", (template_id,))
    await db.commit()
    await db.close()
    return {"message": "Template deleted"}


# === ANALYTICS API ===

@app.get("/api/stats")
async def api_stats_redirect():
    """Legacy endpoint — redirect to analytics."""
    return await api_analytics()


@app.get("/api/analytics")
async def api_analytics():
    """Get comprehensive production analytics."""
    db = await get_db()
    stats = await calculate_video_stats(db)
    recs = get_content_recommendations(stats)
    await db.close()
    stats["recommendations"] = recs
    return stats


# === AUTOPILOT API ===

@app.post("/api/autopilot/run")
async def api_autopilot_run(request: Request):
    """
    Run one autopilot cycle with optional context.
    Accepts JSON body: {character_id, context_texts[], context_image_paths[], topic (optional)}
    If topic is provided, skips trend detection and uses that topic directly.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    character_id = body.get("character_id", 1)
    context_texts = body.get("context_texts", [])
    context_image_paths = body.get("context_image_paths", [])
    manual_topic = body.get("topic", "")
    duration = body.get("duration", 60)
    language = body.get("language", "en")

    db = await get_db()

    # Validate character
    rows = await db.execute_fetchall("SELECT * FROM characters WHERE id = ?", (character_id,))
    if not rows:
        await db.close()
        raise HTTPException(status_code=404, detail="Character not found")

    character = dict(rows[0])
    try:
        character["sample_hooks"] = json.loads(character["sample_hooks"]) if character["sample_hooks"] else []
    except (json.JSONDecodeError, TypeError):
        character["sample_hooks"] = []

    # Validate context if provided
    context_prompt = ""
    validated_images = []
    if context_texts or context_image_paths:
        try:
            ctx = validate_context(
                [t for t in context_texts if t and t.strip()],
                [p for p in context_image_paths if p and os.path.exists(p)],
            )
            context_prompt = build_context_prompt(ctx["texts"], len(ctx["images"]))
            validated_images = ctx["images"]
        except ContextValidationError as e:
            await db.close()
            raise HTTPException(status_code=400, detail=str(e))

    # Get topic: manual or from trends
    if manual_topic:
        topic = manual_topic.strip()
    else:
        async def trend_func():
            return await get_all_trends("US", "horror")
        result = await run_autopilot_cycle(db, _load_settings_sync(), character_id, None, trend_func)
        if result.get("status") != "topic_ready" or not result.get("topic"):
            await db.close()
            return result
        topic = result["topic"]

    # Try to generate script
    settings = _load_settings_sync()
    result = {"status": "topic_ready", "topic": topic}

    if settings.get("anthropic_api_key") or settings.get("ollama_model"):
        try:
            script = await generate_script(character, topic, duration, language, context_prompt)
            cursor = await db.execute(
                """INSERT INTO videos (character_id, title, topic, script_json, status, language, duration_target)
                   VALUES (?, ?, ?, ?, 'draft', ?, ?)""",
                (character_id, script.get("title", topic), topic,
                 json.dumps(script), language, duration),
            )
            await db.commit()
            result["video_id"] = cursor.lastrowid
            result["script"] = script
            result["context_used"] = {
                "texts": len(context_texts),
                "images": len(validated_images),
            }
        except Exception as e:
            result["script_error"] = str(e)
    else:
        cursor = await db.execute(
            """INSERT INTO videos (character_id, title, topic, status, language, duration_target)
               VALUES (?, ?, ?, 'draft', ?, ?)""",
            (character_id, topic, topic, language, duration),
        )
        await db.commit()
        result["video_id"] = cursor.lastrowid
        result["message"] = "Topic saved as draft. No LLM configured — paste a script manually."

    # Store image paths for R2V if available
    if validated_images and result.get("video_id"):
        img_paths_json = json.dumps([img["path"] for img in validated_images])
        await db.execute(
            "INSERT INTO production_log (video_id, step, status, detail) VALUES (?, 'context_images', 'done', ?)",
            (result["video_id"], img_paths_json),
        )
        await db.commit()

    await db.close()
    return result


@app.get("/api/autopilot/status")
async def api_autopilot_status():
    """Get current autopilot status."""
    return get_autopilot_status()


# === PUBLISH API ===

@app.get("/api/publish/youtube-status")
async def api_youtube_status():
    """Check if YouTube is configured for auto-upload."""
    return is_youtube_configured()


@app.post("/api/publish/youtube-auth")
async def api_youtube_auth():
    """Start YouTube OAuth2 authentication."""
    result = await authenticate_youtube()
    return result


@app.post("/api/publish/youtube/{video_id}")
async def api_publish_youtube(video_id: int, request: Request):
    """Upload a video to YouTube."""
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}

    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT v.output_path, v.title, v.script_json, c.name as char_name "
        "FROM videos v JOIN characters c ON v.character_id = c.id "
        "WHERE v.id = ? AND v.status = 'done'",
        (video_id,),
    )
    await db.close()

    if not rows or not rows[0]["output_path"]:
        raise HTTPException(status_code=404, detail="Video not ready")

    video = dict(rows[0])
    title = body.get("title", video["title"] or "Untitled")
    description = body.get("description", f"A story by {video['char_name']}")
    tags = body.get("tags", ["horror", "scarystory", "creepypasta", "nosleep"])
    privacy = body.get("privacy", "public")

    result = await upload_to_youtube(
        video["output_path"], title, description, tags, privacy=privacy
    )
    return result


@app.post("/api/publish/tiktok/{video_id}")
async def api_export_tiktok(video_id: int):
    """Export a TikTok-ready video package."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT output_path, title FROM videos WHERE id = ? AND status = 'done'",
        (video_id,),
    )
    await db.close()
    if not rows or not rows[0]["output_path"]:
        raise HTTPException(status_code=404, detail="Video not ready")

    return await prepare_tiktok_package(
        rows[0]["output_path"], rows[0]["title"] or "Untitled", video_id=video_id
    )


@app.post("/api/publish/instagram/{video_id}")
async def api_export_instagram(video_id: int):
    """Export an Instagram Reels-ready video package."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT output_path, title FROM videos WHERE id = ? AND status = 'done'",
        (video_id,),
    )
    await db.close()
    if not rows or not rows[0]["output_path"]:
        raise HTTPException(status_code=404, detail="Video not ready")

    return await prepare_instagram_package(
        rows[0]["output_path"], rows[0]["title"] or "Untitled", video_id=video_id
    )


@app.post("/api/publish/all/{video_id}")
async def api_publish_all(video_id: int):
    """Publish to YouTube + export packages for TikTok and Instagram."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT v.output_path, v.title, v.script_json, c.name as char_name "
        "FROM videos v JOIN characters c ON v.character_id = c.id "
        "WHERE v.id = ? AND v.status = 'done'",
        (video_id,),
    )
    await db.close()
    if not rows or not rows[0]["output_path"]:
        raise HTTPException(status_code=404, detail="Video not ready")

    video = dict(rows[0])
    results = {}

    # YouTube auto-upload
    yt_status = is_youtube_configured()
    if yt_status["authenticated"]:
        results["youtube"] = await upload_to_youtube(
            video["output_path"], video["title"] or "Untitled",
            f"A story by {video['char_name']}",
        )
    else:
        results["youtube"] = {"status": "not_configured", "message": "Set up YouTube in Settings first"}

    # TikTok export
    results["tiktok"] = await prepare_tiktok_package(
        video["output_path"], video["title"] or "Untitled", video_id=video_id
    )

    # Instagram export
    results["instagram"] = await prepare_instagram_package(
        video["output_path"], video["title"] or "Untitled", video_id=video_id
    )

    return results


@app.get("/api/publish/queue")
async def api_publish_queue():
    """Get the publishing schedule."""
    return load_schedule()


@app.post("/api/publish/schedule/{video_id}")
async def api_schedule_publish(video_id: int):
    """Add video to schedule for all platforms."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT output_path, title FROM videos WHERE id = ? AND status = 'done'",
        (video_id,),
    )
    await db.close()
    if not rows or not rows[0]["output_path"]:
        raise HTTPException(status_code=404, detail="Video not ready")

    return await add_to_schedule(
        video_id, rows[0]["output_path"], rows[0]["title"] or "Untitled",
    )


# === SCHEDULER API ===

@app.get("/api/scheduler")
async def api_get_scheduler():
    return load_scheduler_config()


@app.post("/api/scheduler")
async def api_update_scheduler(request: Request):
    body = await request.json()
    config = load_scheduler_config()
    config.update(body)
    save_scheduler_config(config)
    return {"message": "Schedule updated"}


@app.post("/api/scheduler/start")
async def api_start_scheduler():
    global scheduler_task
    config = load_scheduler_config()
    config["enabled"] = True
    save_scheduler_config(config)
    if scheduler_task is None or scheduler_task.done():
        scheduler_task = asyncio.create_task(scheduler_loop())
    return {"message": "Scheduler started"}


@app.post("/api/scheduler/stop")
async def api_stop_scheduler():
    global scheduler_task
    config = load_scheduler_config()
    config["enabled"] = False
    save_scheduler_config(config)
    if scheduler_task and not scheduler_task.done():
        scheduler_task.cancel()
        scheduler_task = None
    return {"message": "Scheduler stopped"}


@app.post("/api/scheduler/run-now")
async def api_run_scheduler_now():
    """Run one production cycle immediately."""
    config = load_scheduler_config()
    result = await run_scheduled_production(config)
    return result


# === SUBTITLE CONFIG API ===

@app.get("/api/subtitles/presets")
async def api_subtitle_presets():
    """Get available subtitle style presets."""
    return get_style_presets()


@app.post("/api/subtitles/save-style")
async def api_save_subtitle_style(request: Request):
    """Save subtitle style as global config."""
    body = await request.json()
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        settings = json.load(f)
    settings["subtitle_style"] = body
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    return {"message": "Subtitle style saved globally"}


@app.get("/api/subtitles/current-style")
async def api_current_subtitle_style():
    """Get current global subtitle style."""
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        settings = json.load(f)
    return settings.get("subtitle_style", {"preset": "viral"})


@app.post("/api/subtitles/preview")
async def api_subtitle_preview(request: Request):
    """
    Generate a preview video with subtitles.
    Accepts: {text, language, style}
    Returns a short video with the subtitle style applied.
    """
    body = await request.json()
    text = body.get("text", "")
    language = body.get("language", "en")
    style = body.get("style", {})

    if not text:
        if language == "es":
            text = "Sientate, hijo. Esta historia nunca debi contarla. Paso en una noche fria de octubre."
        else:
            text = "Sit down, kid. This one I was never supposed to tell. It happened on a cold October night."

    # Get voice from style or default
    voice_id = body.get("voice_id", "en-US-GuyNeural" if language == "en" else "es-MX-JorgeNeural")

    preview_dir = os.path.join(BASE_DIR, "output", "previews")
    os.makedirs(preview_dir, exist_ok=True)

    # 1. Generate audio
    from pipeline.voice import generate_voice
    audio_result = await generate_voice(text, voice_id, "subtitle_preview_audio.mp3")
    audio_path = audio_result["path"]
    audio_duration = audio_result["duration"]

    # 2. Generate ASS subtitles with the style
    ass_path = generate_preview_ass(text, style, audio_duration)

    # 3. Generate a dark background video with subtitles burned in
    import subprocess
    preview_video = os.path.join(preview_dir, "subtitle_preview.mp4")
    ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x0a0a0f:s=1080x1920:d={audio_duration}:r=24",
        "-i", audio_path,
        "-vf", f"ass='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        preview_video,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {proc.stderr[:300]}")

    return FileResponse(preview_video, media_type="video/mp4")


def _load_settings_sync():
    """Load settings synchronously."""
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# === PRODUCTION PIPELINE (with retry logic and cost tracking) ===

async def _retry_async(func, *args, retries=MAX_RETRIES, delay=RETRY_DELAY, **kwargs):
    """Retry an async function with exponential backoff."""
    last_error = None
    for attempt in range(retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                await asyncio.sleep(delay * (attempt + 1))
    raise last_error


async def _run_production(video_id: int, video: dict, production_mode: str = None):
    """
    Run the full production pipeline in background with retry logic.

    production_mode: override the settings.production_mode. "auto" uses fal.ai,
    "free" uses the manual Whisk+Grok workflow.
    """
    db = await get_db()
    try:
        script = json.loads(video["script_json"])
        scenes = script["scenes"]
        voice_id = video["voice_id"]
        char_visual = video.get("char_visual", "")

        # Load settings
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            settings = json.load(f)

        # Determine production mode (request override > settings default)
        if production_mode is None:
            production_mode = settings.get("production_mode", "auto")

        # Step 1: Update status
        await db.execute("UPDATE videos SET status = 'generating' WHERE id = ?", (video_id,))
        await db.commit()

        # Step 2: Generate voice (with retry)
        await _log_step(db, video_id, "voice", "running", "Generating narration audio...")
        audio_results = await _retry_async(
            generate_all_scenes_audio,
            scenes, voice_id, video_id,
            rate=settings.get("tts_rate", "-10%"),
            pitch=settings.get("tts_pitch", "-5Hz"),
        )
        await _log_step(db, video_id, "voice", "done",
                       f"Generated {len(audio_results)} audio files", cost=0.0)

        # Step 3: Generate video clips (with retry per clip)
        mode_label = "Whisk + Grok manual" if production_mode == "free" else "fal.ai automatico"
        await _log_step(db, video_id, "video", "running",
                       f"Generando clips ({mode_label})...")
        video_clips = await _retry_async(
            generate_all_scenes_video, scenes, video_id, char_visual,
            "", "", production_mode  # reference_image_url, reference_image_path, mode
        )
        # Estimate cost: $0.05/sec for Wan 2.6 if fal.ai key is set
        fal_cost = 0.0
        if settings.get("fal_api_key"):
            total_secs = sum(s.get("duration_seconds", 10) for s in scenes)
            fal_cost = total_secs * 0.05
        await _log_step(db, video_id, "video", "done",
                       f"Generated {len(video_clips)} video clips", cost=fal_cost)

        # Step 4: Generate background music and mix with narration
        if settings.get("music_enabled", True):
            await _log_step(db, video_id, "music", "running", "Generating background music...")
            total_audio_duration = sum(a["duration"] for a in audio_results)
            mood = settings.get("music_mood", "horror")
            music_path = await _retry_async(
                generate_ambient_track,
                total_audio_duration + 4,  # extra for fade out
                mood,
                f"ambient_video_{video_id}.mp3",
            )
            # Concatenate all narration audio first, then mix with music
            concat_narration = os.path.join(BASE_DIR, "output", "audio", f"video_{video_id}_narration_full.mp3")
            await _concat_audio_files(audio_results, concat_narration)
            mixed_audio = os.path.join(BASE_DIR, "output", "audio", f"video_{video_id}_mixed.mp3")
            vol_db = get_mood_volume(mood)
            await mix_narration_with_music(concat_narration, music_path, mixed_audio, vol_db)
            # Replace audio_results with single mixed file for assembler
            import subprocess as sp
            # Per-scene audio_results drive clip sync; the ducked mixed_audio
            # is only the final master track. Pass both to the assembler.
            merged_master_audio = mixed_audio
            await _log_step(db, video_id, "music", "done", f"Music mixed ({mood} mood)", cost=0.0)
        else:
            merged_master_audio = None

        # Step 5: Generate subtitles (ASS format for professional styling)
        await _log_step(db, video_id, "subtitles", "running", "Creating word-by-word subtitles...")
        srt_path = generate_ass(scenes, audio_results, video_id)
        await _log_step(db, video_id, "subtitles", "done", "Subtitles created (word-by-word)", cost=0.0)

        # Step 6: Assemble final video
        await db.execute("UPDATE videos SET status = 'rendering' WHERE id = ?", (video_id,))
        await db.commit()
        await _log_step(db, video_id, "assembly", "running", "Assembling final video...")

        final_path = await assemble_video(
            video_clips,
            audio_results,                       # per-scene for clip sync
            srt_path, video_id,
            resolution=settings.get("video_resolution", "1080x1920"),
            merged_audio_path=merged_master_audio,  # None if no music mix
        )
        await _log_step(db, video_id, "assembly", "done", "Video assembled", cost=0.0)

        # Step 7: Generate thumbnail
        await _log_step(db, video_id, "thumbnail", "running", "Generating thumbnail...")
        try:
            thumb_path = await generate_thumbnail(
                title=script.get("title", ""),
                video_path=final_path,
                output_filename=f"thumb_video_{video_id}.jpg",
                style="horror",
            )
            await _log_step(db, video_id, "thumbnail", "done", f"Thumbnail: {thumb_path}", cost=0.0)
        except Exception as e:
            await _log_step(db, video_id, "thumbnail", "done", f"Thumbnail skipped: {e}", cost=0.0)

        # Step 7: Done
        await db.execute(
            "UPDATE videos SET status = 'done', output_path = ?, updated_at = datetime('now') WHERE id = ?",
            (final_path, video_id),
        )
        await db.commit()

    except Exception as e:
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        await db.execute(
            "UPDATE videos SET status = 'error', updated_at = datetime('now') WHERE id = ?",
            (video_id,),
        )
        await _log_step(db, video_id, "error", "failed", error_detail[:500])
        await db.commit()

    finally:
        await db.close()
        active_productions.pop(video_id, None)


async def _concat_audio_files(audio_results: list, output_path: str):
    """Concatenate multiple audio files into one using FFmpeg."""
    import subprocess
    sorted_audio = sorted(audio_results, key=lambda x: x["scene_number"])
    concat_file = output_path + ".txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for a in sorted_audio:
            p = a["path"].replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{p}'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", output_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        os.remove(concat_file)
    except OSError:
        pass
    if proc.returncode != 0:
        raise Exception(f"Audio concat error: {proc.stderr}")


async def _log_step(db, video_id: int, step: str, status: str, detail: str, cost: float = 0.0):
    """Log a production step with cost tracking."""
    now = datetime.utcnow().isoformat()
    await db.execute(
        """INSERT INTO production_log (video_id, step, status, detail, cost_usd, started_at, finished_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (video_id, step, status, detail, cost, now,
         now if status in ("done", "failed") else None),
    )
    await db.commit()


# === RUN ===

if __name__ == "__main__":
    import uvicorn
    import sys
    # Fix Windows asyncio ConnectionResetError
    if sys.platform == "win32":
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run(app, host="0.0.0.0", port=8000)
