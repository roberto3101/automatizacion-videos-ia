"""
Stock footage from Pexels (free, no rate limit for small volume).

Used as a fallback when AI video generation isn't available or fails.
Get a free API key at https://www.pexels.com/api/ — no credit card required.

Add to config/settings.json:  "pexels_api_key": "YOUR_KEY"
"""
import os
import json
import subprocess
import re
import random
import httpx

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")
PEXELS_SEARCH = "https://api.pexels.com/videos/search"

# Translate visual prompts into stock-friendly search terms.
# Pexels has 100s of clips for these but few for "old man by campfire telling horror story".
NICHE_KEYWORDS = {
    "horror": ["dark forest", "fog night", "abandoned house", "candle flame", "shadow"],
    "mystery": ["misty road", "old book", "rain window", "dark hallway"],
    "nature": ["mountains", "ocean waves", "forest light", "river flow"],
    "city": ["city night", "neon street", "skyline", "subway"],
    "tech": ["computer screen", "data flow", "circuit board", "code"],
    "history": ["ancient ruins", "old map", "candle book", "stone wall"],
}


def _load_settings() -> dict:
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_keywords(prompt: str) -> list:
    """Pull a few search-friendly terms out of a visual prompt."""
    cleaned = re.sub(r"[^a-zA-Z0-9 ]", " ", prompt.lower())
    words = cleaned.split()
    stop = {"the", "a", "an", "and", "or", "of", "with", "in", "on", "at", "by",
            "to", "from", "for", "is", "it", "this", "that", "scene", "cinematic",
            "4k", "film", "grain", "shallow", "depth", "field", "shot", "angle",
            "close", "wide", "medium"}
    keywords = [w for w in words if w not in stop and len(w) > 3]

    # Boost with niche-matched terms if the prompt mentions horror/etc.
    for niche, options in NICHE_KEYWORDS.items():
        if niche in prompt.lower():
            keywords = options + keywords
            break

    return keywords[:8] or ["abstract"]


async def fetch_clip(visual_prompt: str, duration: int, output_path: str,
                     orientation: str = "portrait") -> dict:
    """
    Search Pexels for a clip matching the prompt, download it, and trim
    to the requested duration. Vertical 9:16 by default.
    """
    settings = _load_settings()
    api_key = settings.get("pexels_api_key", "")
    if not api_key:
        raise Exception("Pexels API key not configured (settings.pexels_api_key)")

    keywords = _extract_keywords(visual_prompt)

    async with httpx.AsyncClient(timeout=60.0) as client:
        video_url = None
        # Try keyword combos until something hits
        for query in [" ".join(keywords[:3]), " ".join(keywords[:2]), keywords[0]]:
            response = await client.get(
                PEXELS_SEARCH,
                headers={"Authorization": api_key},
                params={
                    "query": query,
                    "orientation": orientation,
                    "size": "medium",
                    "per_page": 15,
                },
            )
            if response.status_code != 200:
                continue
            videos = response.json().get("videos", [])
            if not videos:
                continue

            # Pick a random video and the best vertical file
            video = random.choice(videos)
            video_files = video.get("video_files", [])
            # Prefer 1080p+ portrait files
            video_files.sort(
                key=lambda v: (v.get("height", 0) >= 1080, v.get("height", 0)),
                reverse=True
            )
            for vf in video_files:
                if vf.get("link"):
                    video_url = vf["link"]
                    break
            if video_url:
                break

        if not video_url:
            raise Exception("No matching Pexels clips found")

        # Download to a temp file then process
        temp_path = output_path + ".raw.mp4"
        download = await client.get(video_url, timeout=300.0)
        with open(temp_path, "wb") as f:
            f.write(download.content)

    # Trim and scale to 1080x1920 vertical
    _normalize_clip(temp_path, output_path, duration)

    try:
        os.remove(temp_path)
    except OSError:
        pass

    return {"path": output_path, "duration": duration}


def _normalize_clip(input_path: str, output_path: str, duration: int):
    """Scale to 1080x1920, trim/loop to exact duration, ensure 24fps."""
    src_dur = _get_duration(input_path)

    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1,fps=24"
    )

    if src_dur >= duration:
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-an",
            output_path,
        ]
    else:
        # Loop the source enough times to cover the duration
        loops = int(duration / src_dur) + 1
        cmd = [
            "ffmpeg", "-y", "-stream_loop", str(loops), "-i", input_path,
            "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-an",
            output_path,
        ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise Exception(f"FFmpeg stock normalize error: {proc.stderr[:200]}")


def _get_duration(path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True,
        )
        return float(r.stdout.strip())
    except Exception:
        return 5.0
