# Video Factory — AI Viral Video Pipeline

Automated pipeline that turns a JSON script into a finished vertical short (YouTube Shorts / TikTok / Reels).

Generates per-scene voice, AI video clips (or stock footage / Ken Burns fallbacks), word-by-word subtitles synced via Whisper, sidechain-ducked music, and assembles everything with mixed transitions and GPU encoding.

## Pipeline

```
Script (JSON)
   ├─→ scriptwriter.py     (Claude API / Ollama / paste)
   ├─→ voice.py            (Kokoro / Fish Audio / XTTS / Edge-TTS)
   ├─→ video_gen.py        (fal.ai: Kling 2.1, Veo 3.1 Fast, etc.) ──┐
   │                                                                  │ fallback
   ├─→ stock.py            (Pexels — free stock B-roll) ──────────────┤
   │                                                                  │ fallback
   ├─→ ken_burns.py        (animate static images with zoom/pan) ─────┘
   ├─→ subtitles.py        (Whisper word-level timestamps + ASS)
   ├─→ music.py            (synth or library track + sidechain ducking)
   └─→ assembler.py        (FFmpeg + GPU encoder + transitions)
        ↓
    output/final/*.mp4
```

## Quick start (Windows)

```
1. Doble-click en setup.bat       (instala TODO — Python, FFmpeg, deps)
2. Edita config/settings.json     (mete tus API keys)
3. Doble-click en start.bat       (cada vez que quieras correr el sistema)
```

That's it. **`setup.bat` is all-in-one:**
- Detects Python — **downloads and installs Python 3.11 if missing** (no admin needed, user-mode install)
- Detects FFmpeg — **downloads portable FFmpeg to `bin/ffmpeg/` if missing** (~140 MB, no PATH changes needed)
- Creates a virtualenv at `.venv/`
- Installs `requirements.txt` (base: FastAPI + Edge-TTS + httpx, ~50 MB)
- Optionally prompts to also install `requirements-full.txt` (Kokoro + Whisper + YouTube API, ~2 GB)
- Copies `settings.example.json` → `settings.json`
- Creates all required output directories

`start.bat` activates the venv, detects portable FFmpeg if present, kills any zombie process on port 8000, opens your browser, and launches the server at http://localhost:8000.

`update.bat` jala los últimos cambios del repo (`git pull`) y reinstala dependencias si `requirements.txt` cambió.

`install_full.bat` agrega las features avanzadas (si las saltaste en setup.bat).

## Manual setup (Linux/Mac/other)

### 1. Requirements

- Python 3.10+
- FFmpeg + ffprobe on PATH
- Optional: NVIDIA / AMD / Intel GPU (auto-detected for video encoding)

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate.bat on Windows
pip install -r requirements.txt
```

### 2. Configure API keys

Copy the example settings and fill in the keys you actually need:

```bash
cp config/settings.example.json config/settings.json
```

Edit `config/settings.json`:

| Field | What it's for | Where to get |
|---|---|---|
| `fal_api_key` | AI video + image generation | https://fal.ai (~$0.05/s for Kling 2.1) |
| `anthropic_api_key` | Auto-generate scripts | https://console.anthropic.com (optional — can paste scripts manually) |
| `youtube_api_key` | Auto-upload finished videos | https://console.cloud.google.com (YouTube Data API v3) |
| `pexels_api_key` | Stock footage fallback when AI fails | https://www.pexels.com/api (free, no credit card) |
| `fish_api_key` | Premium voice (optional) | https://fish.audio (8K credits/month free tier) |

### 3. Pick your video model

In `settings.json`, `video_model` selects which fal.ai model is used. Cost vs quality tiers:

| Setting | Model | $/sec | When to use |
|---|---|---|---|
| `kling21` ⭐ | Kling 2.1 Standard | $0.05 | **Default — best cost/quality** |
| `kling25` | Kling 2.5 Turbo Standard | $0.05 | Newer Kling, same price |
| `veo3fast` | Veo 3.1 Fast | $0.10 | Upgrade after a video proves traction |
| `kling-pro` | Kling 2.5 Turbo Pro | $0.10 | Higher quality Kling |
| `veo3` | Veo 3 Full | $0.25 | Premium hero videos only |
| `wan26` / `wan25` | Wan 2.x | $0.04 | Budget fallback |

### 4. Run

```bash
python server.py
# → http://localhost:8000
```

On Windows just double-click `start.bat`.

## Project structure

```
config/
  characters/             Character JSON presets (load on startup)
  settings.example.json   Template — copy to settings.json and fill keys
pipeline/
  scriptwriter.py         LLM script generation
  voice.py                4 TTS engines (Kokoro, Fish, XTTS, Edge)
  video_gen.py            fal.ai model registry + R2V mode
  stock.py                Pexels integration
  ken_burns.py            Static-image animation + ping-pong clip extension
  subtitles.py            Whisper word-level ASS subtitle generation
  music.py                Track preparation + sidechain ducking
  assembler.py            FFmpeg assembly with GPU detection
  publisher.py            YouTube auto-upload
  thumbnail.py            Thumbnail generation
  trends.py               Reddit / YouTube / Creepypasta / 4chan scanner
  analytics.py            Production stats + insights feedback loop
  autopilot.py            One-click trend → script → produce → publish
  scheduler.py            Cron-style automation
  context.py              Multi-image/text context input
server.py                 FastAPI web UI
database.py               SQLite + character preset loader
static/, templates/       Web UI assets
assets/music/             Drop royalty-free MP3s here by mood (gitignored)
```

## Key features

- **Per-scene clip syncing with ping-pong extension** — AI clips that come out shorter than narration are extended without freezing frames (forward + reverse + forward via filter_complex concat).
- **Word-level subtitles via Whisper** — original script text mapped onto Whisper's actual audio timestamps for perfect sync.
- **Sidechain audio ducking** — music dips automatically when narrator speaks (real `sidechaincompress`, not just volume mix).
- **Verified GPU encoding** — auto-detects h264_nvenc / h264_qsv / h264_amf and falls back to libx264 if the GPU encoder is listed but doesn't actually work (e.g. missing nvcuda.dll).
- **14 transition styles** — fade, dissolve, wipe, slide, zoomin, circleopen, pixelize, and more. Configurable per video.
- **Production-insights feedback loop** — past video success patterns are injected into the script-generation prompt automatically.

## Notes

- `config/settings.json` is gitignored. Use `config/settings.example.json` as your template.
- `output/`, `data/`, `assets/references/`, `assets/music/*/`, `assets/voices/` are gitignored (runtime / personal content).
- The system is niche-agnostic. Skeleton presets ship as examples; swap the character JSONs for any niche.
