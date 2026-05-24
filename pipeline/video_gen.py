"""
Video clip generation.

Strategy (in priority order):
1. AI video model from fal.ai (configurable: wan26, veo3, kling25, kling-pro)
2. Pexels stock footage (free, real video, fallback when AI fails or no balance)
3. Animated placeholder (Ken Burns over a generated gradient + prompt text)

The model registry below makes adding new models a one-entry change.
"""
import httpx
import os
import json
import asyncio

from . import stock

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "clips")
SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")


# ─── Model registry ──────────────────────────────────────────────────────
# Each entry: endpoint, native fps, max seconds, supports R2V, default resolution.
# num_frames is computed as duration * fps, capped to max_seconds * fps.
MODEL_REGISTRY = {
    "wan26": {
        "endpoint": "fal-ai/wan/v2.6/1080p",
        "r2v_endpoint": "fal-ai/wan/v2.6/reference-to-video",
        "fps": 16,
        "max_seconds": 5,        # Wan 2.6 hard caps at ~81 frames
        "resolution": "768x1344",
        "param_style": "frames",
        "cost_per_second_usd": 0.04,
        "tier": "budget",
    },
    "wan25": {
        "endpoint": "fal-ai/wan-25-preview/text-to-video",
        "r2v_endpoint": "fal-ai/wan-25-preview/image-to-video",
        "fps": 24,
        "max_seconds": 10,
        "resolution": "1080x1920",
        "param_style": "duration",
        "cost_per_second_usd": 0.04,
        "tier": "budget",
    },
    # Kling 2.1 Standard — RECOMMENDED for cost/quality balance on skeleton content
    "kling21": {
        "endpoint": "fal-ai/kling-video/v2.1/standard/text-to-video",
        "r2v_endpoint": "fal-ai/kling-video/v2.1/standard/image-to-video",
        "fps": 24,
        "max_seconds": 10,
        "resolution": "1080x1920",
        "param_style": "duration",
        "cost_per_second_usd": 0.05,
        "tier": "value",
    },
    # Kling 2.5 Turbo Standard — newer, slightly better motion, same price tier
    "kling25": {
        "endpoint": "fal-ai/kling-video/v2.5-turbo/standard/text-to-video",
        "r2v_endpoint": "fal-ai/kling-video/v2.5-turbo/standard/image-to-video",
        "fps": 24,
        "max_seconds": 10,
        "resolution": "1080x1920",
        "param_style": "duration",
        "cost_per_second_usd": 0.05,
        "tier": "value",
    },
    "kling-pro": {
        "endpoint": "fal-ai/kling-video/v2.5-turbo/pro/text-to-video",
        "r2v_endpoint": "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
        "fps": 30,
        "max_seconds": 10,
        "resolution": "1080x1920",
        "param_style": "duration",
        "cost_per_second_usd": 0.10,
        "tier": "premium",
    },
    # Veo 3.1 Fast — Google quality at 60% of Veo 3 Full's cost
    "veo3fast": {
        "endpoint": "fal-ai/veo3.1/fast/text-to-video",
        "r2v_endpoint": "fal-ai/veo3.1/fast/image-to-video",
        "fps": 24,
        "max_seconds": 8,
        "resolution": "1080x1920",
        "param_style": "duration",
        "cost_per_second_usd": 0.10,
        "tier": "premium",
    },
    "veo3": {
        "endpoint": "fal-ai/veo3/text-to-video",
        "r2v_endpoint": "fal-ai/veo3/image-to-video",
        "fps": 24,
        "max_seconds": 8,
        "resolution": "1080x1920",
        "param_style": "duration",
        "cost_per_second_usd": 0.25,
        "tier": "flagship",
    },
}

DEFAULT_MODEL = "wan26"


def _load_settings():
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_model_config(settings: dict) -> dict:
    name = settings.get("video_model", DEFAULT_MODEL)
    return MODEL_REGISTRY.get(name, MODEL_REGISTRY[DEFAULT_MODEL]) | {"name": name}


def _build_payload(prompt: str, duration: int, model: dict,
                   reference_image_url: str = None) -> dict:
    """Build the API payload according to the model's parameter style."""
    # Clamp duration to model's hard limit
    max_sec = model["max_seconds"]
    effective_dur = min(duration, max_sec)

    payload = {
        "prompt": prompt,
        "resolution": model["resolution"],
        "enable_safety_checker": False,
    }

    if model["param_style"] == "frames":
        payload["num_frames"] = int(effective_dur * model["fps"])
    else:  # "duration"
        payload["duration"] = effective_dur

    if reference_image_url:
        payload["image_url"] = reference_image_url
        payload["reference_image_url"] = reference_image_url  # some models use this name

    return payload


# ─── Public API ──────────────────────────────────────────────────────────

async def generate_video_clip(visual_prompt: str, duration: int, output_filename: str) -> dict:
    """Single-clip generation (used by older code paths). Returns {path, duration}."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    settings = _load_settings()

    if settings.get("fal_api_key"):
        try:
            return await _generate_with_fal(visual_prompt, duration, output_path, settings)
        except Exception as e:
            print(f"[video_gen] fal.ai failed ({e}); trying stock footage")

    if settings.get("pexels_api_key"):
        try:
            return await stock.fetch_clip(visual_prompt, duration, output_path)
        except Exception as e:
            print(f"[video_gen] Pexels failed ({e}); using animated placeholder")

    return await _generate_placeholder(visual_prompt, duration, output_path)


async def generate_all_scenes_video(scenes: list, video_id: int, character_visual: str = "",
                                    reference_image_url: str = "",
                                    reference_image_path: str = "",
                                    mode: str = None) -> list:
    """
    Generate video clips for all scenes.

    mode:
        None or "auto"  → AI via fal.ai (paid). Tries:
                          1. AI video (R2V if reference, else T2V)
                          2. Pexels stock footage fallback
                          3. Animated placeholder
        "free"          → Manual workflow: opens Whisk + Grok in browser,
                          user generates images and clips, drops them in
                          output/manual/video_{id}/, system waits and uses them.
                          (Free, ~10 min user work per video.)

    reference_image_path: local file path (for free mode instructions).
    reference_image_url:  URL accessible to AI APIs (for fal.ai R2V).
    """
    settings = _load_settings()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if mode is None:
        mode = settings.get("production_mode", "auto")

    # ── FREE MODE: manual workflow with Whisk + Grok ────────────────
    if mode == "free":
        from . import free_mode
        return free_mode.collect_manual_clips(
            scenes, video_id, reference_image_path=reference_image_path,
        )

    # ── AUTO MODE: fal.ai (paid) ────────────────────────────────────
    has_ai = bool(settings.get("fal_api_key"))
    has_stock = bool(settings.get("pexels_api_key"))
    use_r2v = bool(has_ai and reference_image_url)

    results = []
    for scene in scenes:
        prompt = scene["visual_prompt"]
        if character_visual:
            prompt = f"{character_visual}. Scene: {prompt}"

        duration = scene.get("duration_seconds", 10)
        filename = f"video_{video_id}_scene_{scene['scene_number']}.mp4"
        output_path = os.path.join(OUTPUT_DIR, filename)

        result = None

        # Tier 1: AI
        if has_ai:
            try:
                if use_r2v:
                    result = await _generate_with_fal(
                        prompt, duration, output_path, settings,
                        reference_image_url=reference_image_url,
                    )
                else:
                    result = await _generate_with_fal(prompt, duration, output_path, settings)
            except Exception as e:
                print(f"[video_gen] scene {scene['scene_number']}: AI failed — {e}")

        # Tier 2: Stock
        if result is None and has_stock:
            try:
                result = await stock.fetch_clip(prompt, duration, output_path)
            except Exception as e:
                print(f"[video_gen] scene {scene['scene_number']}: stock failed — {e}")

        # Tier 3: Animated placeholder
        if result is None:
            result = await _generate_placeholder(prompt, duration, output_path)

        result["scene_number"] = scene["scene_number"]
        results.append(result)

    return results


# ─── fal.ai ──────────────────────────────────────────────────────────────

async def _generate_with_fal(prompt: str, duration: int, output_path: str,
                             settings: dict, reference_image_url: str = None) -> dict:
    """Generate a clip via fal.ai using the configured model."""
    model = _get_model_config(settings)
    api_key = settings["fal_api_key"]

    endpoint = model["r2v_endpoint"] if reference_image_url else model["endpoint"]
    payload = _build_payload(prompt, duration, model, reference_image_url)

    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(
            f"https://queue.fal.run/{endpoint}",
            headers={
                "Authorization": f"Key {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        if response.status_code == 200:
            data = response.json()
            video_url = data.get("video", {}).get("url", "")
            if video_url:
                return await _download(client, video_url, output_path, duration)

        if response.status_code in (200, 202):
            request_id = response.json().get("request_id", "")
            if request_id:
                return await _poll_fal_result(client, request_id, output_path, duration,
                                              api_key, endpoint)

        raise Exception(f"fal.ai {endpoint} returned {response.status_code}: {response.text[:200]}")


async def _poll_fal_result(client, request_id: str, output_path: str, duration: int,
                           api_key: str, endpoint: str) -> dict:
    """Poll fal.ai for queued result. Max ~10 minutes."""
    for _ in range(120):
        await asyncio.sleep(5)
        response = await client.get(
            f"https://queue.fal.run/{endpoint}/requests/{request_id}/status",
            headers={"Authorization": f"Key {api_key}"},
        )
        data = response.json()
        status = data.get("status", "")

        if status == "COMPLETED":
            result_response = await client.get(
                f"https://queue.fal.run/{endpoint}/requests/{request_id}",
                headers={"Authorization": f"Key {api_key}"},
            )
            result = result_response.json()
            video_url = result.get("video", {}).get("url", "")
            if video_url:
                return await _download(client, video_url, output_path, duration)
            raise Exception("Video URL missing in completed response")

        if status == "FAILED":
            raise Exception(f"fal.ai generation failed: {data}")

    raise Exception("fal.ai generation timed out after 10 minutes")


async def _download(client, video_url: str, output_path: str, requested_dur: int) -> dict:
    """Download a generated video to disk."""
    response = await client.get(video_url, timeout=120.0)
    with open(output_path, "wb") as f:
        f.write(response.content)
    return {"path": output_path, "duration": requested_dur}


# ─── Animated placeholder ────────────────────────────────────────────────

async def _generate_placeholder(prompt: str, duration: int, output_path: str) -> dict:
    """
    Animated placeholder when no AI / stock available.
    Slow zoom on a dark color background with the prompt text overlaid —
    far less obviously fake than a flat color screen. Crucially, it has
    constant motion so transitions don't expose it as a static frame.
    """
    import subprocess
    import re

    display_text = re.sub(r"[^a-zA-Z0-9 ]", "", prompt[:80]).strip() or "Scene"
    palette = ["0x0a0a1a", "0x1a0a0a", "0x0a1a1a", "0x1a1a0a", "0x150a20"]
    color = palette[abs(hash(prompt)) % len(palette)]

    total_frames = max(int(duration * 24), 24)
    vf = (
        f"zoompan=z='if(lte(zoom,1.0),1.15,max(1.0,zoom-0.0015))':"
        f"d={total_frames}:s=1080x1920:fps=24,"
        f"drawtext=text='{display_text}':fontcolor=white@0.85:fontsize=44:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:borderw=3:bordercolor=black@0.7"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={color}:s=1080x1920:d={duration}:r=24",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-t", str(duration),
        output_path
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Last-resort: just a moving color, no text
        cmd2 = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={color}:s=1080x1920:d={duration}:r=24",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-t", str(duration),
            output_path
        ]
        proc2 = subprocess.run(cmd2, capture_output=True, text=True)
        if proc2.returncode != 0:
            raise Exception(f"FFmpeg placeholder error: {proc2.stderr[:200]}")

    return {"path": output_path, "duration": duration}


# ─── Legacy compatibility (R2V function) ─────────────────────────────────

async def _generate_with_r2v(prompt: str, duration: int, output_path: str,
                              api_key: str, reference_image_url: str) -> dict:
    """Kept for backwards compatibility; new code should use generate_all_scenes_video."""
    settings = _load_settings()
    settings["fal_api_key"] = api_key
    return await _generate_with_fal(prompt, duration, output_path, settings,
                                    reference_image_url=reference_image_url)
