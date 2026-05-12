"""
Voice generation module.
Supports four engines:
- Fish Audio (Best quality, API-based, voice cloning, multilingual)
- XTTS v2 (Coqui, free, voice cloning, multilingual, local)
- Edge-TTS (Microsoft, free, 47+ voices, decent quality, fast)
- Kokoro (Open source, free, natural quality, runs locally, English-best)
"""
import edge_tts
import os
import json
import subprocess

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "audio")
SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")
VOICES_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "voices")

# Singletons (lazy loaded)
_kokoro_pipeline = None
_xtts_model = None


def _get_kokoro_pipeline():
    global _kokoro_pipeline
    if _kokoro_pipeline is None:
        from kokoro import KPipeline
        _kokoro_pipeline = KPipeline(lang_code='a')
    return _kokoro_pipeline


def _get_xtts_model():
    """Load XTTS v2 model (lazy, singleton). ~1.8GB first time."""
    global _xtts_model
    if _xtts_model is None:
        # Patch torchaudio.load to use soundfile (avoids torchcodec DLL issues on Windows)
        import torch
        import soundfile as sf
        import numpy as np
        import torchaudio

        def patched_load(filepath, *args, **kwargs):
            data, sr = sf.read(str(filepath), dtype='float32')
            if data.ndim == 1:
                data = data[np.newaxis, :]
            else:
                data = data.T
            return torch.FloatTensor(data), sr

        torchaudio.load = patched_load

        from TTS.api import TTS
        _xtts_model = TTS('tts_models/multilingual/multi-dataset/xtts_v2')
    return _xtts_model


def _load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


async def generate_voice(text: str, voice_id: str = "en-US-GuyNeural",
                         output_filename: str = "scene.mp3",
                         rate: str = "-10%", pitch: str = "-5Hz",
                         speaker_wav: str = None, language: str = None) -> dict:
    """
    Generate speech audio. Auto-detects engine from voice_id prefix:
    - 'fish:' prefix → Fish Audio engine (e.g. fish:default or fish:MODEL_ID)
    - 'xtts:' prefix → XTTS v2 engine (e.g. xtts:old_emilio or xtts:default)
    - 'kokoro:' prefix → Kokoro engine (e.g. kokoro:am_adam)
    - anything else → Edge-TTS engine
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if voice_id.startswith("fish:"):
        return await _generate_fish(text, voice_id, output_filename, language)
    elif voice_id.startswith("xtts:"):
        return await _generate_xtts(text, voice_id, output_filename, speaker_wav, language)
    elif voice_id.startswith("kokoro:"):
        return await _generate_kokoro(text, voice_id, output_filename)
    else:
        return await _generate_edge_tts(text, voice_id, output_filename, rate, pitch)


# ─── Fish Audio ──────────────────────────────────────────────────────────

async def _generate_fish(text: str, voice_id: str, output_filename: str,
                         language: str = None) -> dict:
    """Generate with Fish Audio API (best quality, needs API key)."""
    from fish_audio_sdk import Session, TTSRequest

    settings = _load_settings()
    api_key = settings.get("fish_api_key", "")
    if not api_key:
        raise Exception("Fish Audio API key not configured. Get one free at https://fish.audio")

    # Model/voice ID — 'fish:default' uses Fish's default, 'fish:MODEL_ID' uses specific model
    model_id = voice_id.replace("fish:", "")
    if model_id == "default" or not model_id:
        model_id = settings.get("fish_model_id", "")  # User can set a preferred model

    session = Session(api_key)
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    mp3_path = output_path if output_path.endswith(".mp3") else output_path.rsplit(".", 1)[0] + ".mp3"

    # Build request
    tts_kwargs = {"text": text}
    if model_id:
        tts_kwargs["reference_id"] = model_id

    # Generate audio
    audio_data = b""
    for chunk in session.tts(TTSRequest(**tts_kwargs)):
        audio_data += chunk

    with open(mp3_path, "wb") as f:
        f.write(audio_data)

    duration = _get_audio_duration(mp3_path)
    return {"path": mp3_path, "duration": duration}


# ─── XTTS v2 ────────────────────────────────────────────────────────────

async def _generate_xtts(text: str, voice_id: str, output_filename: str,
                         speaker_wav: str = None, language: str = None) -> dict:
    """Generate with XTTS v2 (voice cloning, best quality)."""
    settings = _load_settings()
    xtts_settings = settings.get("xtts", {})

    # Determine language
    if not language:
        language = xtts_settings.get("language", settings.get("default_language", "es"))

    # Determine reference voice file
    if not speaker_wav:
        voice_name = voice_id.replace("xtts:", "")
        speaker_wav = _find_voice_reference(voice_name, xtts_settings)

    if not speaker_wav or not os.path.exists(speaker_wav):
        # Generate a default reference using Edge-TTS
        speaker_wav = await _create_default_reference(language)

    # Ensure reference is proper WAV format (22050Hz mono)
    speaker_wav = _prepare_reference_audio(speaker_wav)

    # Generate with XTTS
    tts = _get_xtts_model()
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    wav_path = output_path.rsplit(".", 1)[0] + "_xtts.wav"

    tts.tts_to_file(
        text=text,
        language=language,
        speaker_wav=speaker_wav,
        file_path=wav_path,
    )

    # Convert to mp3
    mp3_path = output_path if output_path.endswith(".mp3") else output_path.rsplit(".", 1)[0] + ".mp3"
    cmd = ["ffmpeg", "-y", "-i", wav_path, "-c:a", "libmp3lame", "-b:a", "192k", mp3_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        mp3_path = wav_path
    else:
        _safe_delete(wav_path)

    duration = _get_audio_duration(mp3_path)
    return {"path": mp3_path, "duration": duration}


def _find_voice_reference(voice_name: str, xtts_settings: dict) -> str:
    """Find reference audio for a voice name."""
    os.makedirs(VOICES_DIR, exist_ok=True)

    # Check explicit path in settings
    voice_refs = xtts_settings.get("voice_references", {})
    if voice_name in voice_refs:
        path = voice_refs[voice_name]
        if os.path.exists(path):
            return path

    # Check assets/voices/ directory
    for ext in [".wav", ".mp3", ".ogg", ".m4a"]:
        path = os.path.join(VOICES_DIR, voice_name + ext)
        if os.path.exists(path):
            return path

    # Check for "default" reference
    for ext in [".wav", ".mp3"]:
        path = os.path.join(VOICES_DIR, "default" + ext)
        if os.path.exists(path):
            return path

    return ""


async def _create_default_reference(language: str) -> str:
    """Create a default reference voice using Edge-TTS if none exists."""
    os.makedirs(VOICES_DIR, exist_ok=True)
    ref_path = os.path.join(VOICES_DIR, "default_ref.wav")

    if os.path.exists(ref_path):
        return ref_path

    # Generate a reference sample with Edge-TTS
    if language.startswith("es"):
        voice = "es-MX-JorgeNeural"
        text = "Esta es una voz profunda y grave, ideal para narrar historias de misterio y terror."
    else:
        voice = "en-US-GuyNeural"
        text = "This is a deep, gravelly voice, perfect for narrating tales of mystery and horror."

    communicate = edge_tts.Communicate(text, voice, rate="-5%", pitch="-8Hz")
    await communicate.save(ref_path)
    return ref_path


def _prepare_reference_audio(path: str) -> str:
    """Ensure reference audio is WAV 22050Hz mono (XTTS requirement)."""
    prepared = os.path.join(VOICES_DIR, "_prepared_ref.wav")
    cmd = ["ffmpeg", "-y", "-i", path, "-ar", "22050", "-ac", "1", "-t", "15", prepared]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        return prepared
    return path


def get_available_xtts_voices() -> list:
    """List available voice references in assets/voices/."""
    os.makedirs(VOICES_DIR, exist_ok=True)
    voices = []
    for f in os.listdir(VOICES_DIR):
        if f.startswith("_"):
            continue
        name, ext = os.path.splitext(f)
        if ext.lower() in [".wav", ".mp3", ".ogg", ".m4a"]:
            voices.append({
                "id": f"xtts:{name}",
                "name": f"XTTS: {name}",
                "file": f,
                "path": os.path.join(VOICES_DIR, f),
            })
    if not voices:
        voices.append({
            "id": "xtts:default",
            "name": "XTTS: Default (auto-generated)",
            "file": None,
            "path": None,
        })
    return voices


# ─── Edge-TTS ────────────────────────────────────────────────────────────

async def _generate_edge_tts(text: str, voice_id: str, output_filename: str,
                              rate: str, pitch: str) -> dict:
    """Generate with Edge-TTS (Microsoft)."""
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    communicate = edge_tts.Communicate(text, voice_id, rate=rate, pitch=pitch)
    await communicate.save(output_path)
    duration = _get_audio_duration(output_path)
    return {"path": output_path, "duration": duration}


# ─── Kokoro ──────────────────────────────────────────────────────────────

async def _generate_kokoro(text: str, voice_id: str, output_filename: str) -> dict:
    """Generate with Kokoro (local, high quality)."""
    import soundfile as sf

    kokoro_voice = voice_id.replace("kokoro:", "")
    pipeline = _get_kokoro_pipeline()

    settings = _load_settings()
    speed = settings.get("kokoro_speed", 0.85)

    output_path = os.path.join(OUTPUT_DIR, output_filename)
    wav_path = output_path.rsplit(".", 1)[0] + ".wav"

    all_audio = []
    for gs, ps, audio in pipeline(text, voice=kokoro_voice, speed=speed):
        all_audio.append(audio)

    if not all_audio:
        raise Exception("Kokoro generated no audio")

    import numpy as np
    combined = np.concatenate(all_audio)
    sf.write(wav_path, combined, 24000)

    mp3_path = output_path if output_path.endswith(".mp3") else output_path.rsplit(".", 1)[0] + ".mp3"
    cmd = ["ffmpeg", "-y", "-i", wav_path, "-c:a", "libmp3lame", "-b:a", "192k", mp3_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        mp3_path = wav_path
    else:
        _safe_delete(wav_path)

    duration = _get_audio_duration(mp3_path)
    return {"path": mp3_path, "duration": duration}


# ─── Shared utilities ────────────────────────────────────────────────────

async def generate_all_scenes_audio(scenes: list, voice_id: str, video_id: int,
                                    rate: str = "-10%", pitch: str = "-5Hz",
                                    speaker_wav: str = None, language: str = None) -> list:
    """Generate audio for all scenes. Returns list of {path, duration, scene_number}."""
    results = []
    for scene in scenes:
        filename = f"video_{video_id}_scene_{scene['scene_number']}.mp3"
        result = await generate_voice(
            text=scene["narration"],
            voice_id=voice_id,
            output_filename=filename,
            rate=rate,
            pitch=pitch,
            speaker_wav=speaker_wav,
            language=language,
        )
        result["scene_number"] = scene["scene_number"]
        results.append(result)
    return results


def _get_audio_duration(filepath: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries",
             "format=duration", "-of", "csv=p=0", filepath],
            capture_output=True, text=True
        )
        return float(result.stdout.strip())
    except Exception:
        return 10.0


def _safe_delete(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


async def list_voices(language: str = "en") -> list:
    """List available voices across all engines."""
    voices = []

    # Fish Audio voices
    settings = _load_settings()
    if settings.get("fish_api_key"):
        voices.append({"id": "fish:default", "name": "Fish Audio: Default", "gender": "Mixed", "engine": "fish"})
        fish_model = settings.get("fish_model_id", "")
        if fish_model:
            voices.append({"id": f"fish:{fish_model}", "name": "Fish Audio: Custom Model", "gender": "Mixed", "engine": "fish"})

    # XTTS voices
    for v in get_available_xtts_voices():
        voices.append({"id": v["id"], "name": v["name"], "gender": "Clone", "engine": "xtts"})

    # Kokoro voices (English only)
    kokoro_voices = [
        ("kokoro:am_adam", "Adam — Deep male narrator"),
        ("kokoro:am_michael", "Michael — Mature male"),
        ("kokoro:af_heart", "Heart — Warm female"),
        ("kokoro:af_sky", "Sky — Clear female"),
        ("kokoro:bm_george", "George — British male"),
        ("kokoro:bf_emma", "Emma — British female"),
    ]
    for vid, name in kokoro_voices:
        voices.append({"id": vid, "name": f"Kokoro: {name}", "gender": "Mixed", "engine": "kokoro"})

    # Edge-TTS voices
    try:
        edge_voices = await edge_tts.list_voices()
        for v in edge_voices:
            if v["Locale"].startswith(language) or v["Locale"].startswith("es") or v["Locale"].startswith("en"):
                voices.append({
                    "id": v["ShortName"],
                    "name": f"Edge: {v['FriendlyName']}",
                    "gender": v["Gender"],
                    "engine": "edge-tts",
                })
    except Exception:
        pass

    return voices
