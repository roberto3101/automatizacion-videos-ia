"""
Automated Scheduler — runs the full pipeline on a schedule.
Modes:
- interval: Run every N hours
- daily: Run at specific times each day
- on_start: Run immediately when started, then wait

The loop: detect trend → generate script → produce video → publish to YouTube
"""
import asyncio
import json
import os
import logging
from datetime import datetime, timedelta

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")
SCHEDULE_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "schedule.json")

logger = logging.getLogger("scheduler")


def load_schedule() -> dict:
    """Load schedule config."""
    default = {
        "enabled": False,
        "mode": "daily",                    # "daily", "interval", "on_start"
        "daily_times": ["08:00", "20:00"],   # Times to run (24h format)
        "interval_hours": 12,                # For interval mode
        "character_id": 1,                   # Default character
        "language": "en",
        "duration": 60,
        "auto_publish_youtube": False,       # Auto-publish after production
        "max_videos_per_day": 2,             # Safety limit
        "niche": "horror",                   # For trend detection
        "notify_on_complete": True,
        "videos_produced_today": 0,
        "last_run_date": "",
    }
    if os.path.exists(SCHEDULE_PATH):
        try:
            with open(SCHEDULE_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                default.update(saved)
        except Exception:
            pass
    return default


def save_schedule(config: dict):
    """Save schedule config."""
    os.makedirs(os.path.dirname(SCHEDULE_PATH), exist_ok=True)
    with open(SCHEDULE_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


async def run_scheduled_production(config: dict = None) -> dict:
    """
    Execute one full automated production cycle:
    1. Detect trending topic
    2. Generate script
    3. Produce video (voice + clips + music + subtitles + assembly + thumbnail)
    4. Optionally publish to YouTube
    Returns result dict with status and details.
    """
    if config is None:
        config = load_schedule()

    result = {"status": "started", "steps": [], "timestamp": datetime.now().isoformat()}

    try:
        # Check daily limit
        today = datetime.now().strftime("%Y-%m-%d")
        if config.get("last_run_date") != today:
            config["videos_produced_today"] = 0
            config["last_run_date"] = today

        if config["videos_produced_today"] >= config.get("max_videos_per_day", 2):
            result["status"] = "skipped"
            result["reason"] = f"Daily limit reached ({config['max_videos_per_day']} videos)"
            return result

        # Step 1: Get trending topic
        result["steps"].append({"step": "trends", "status": "running"})
        from pipeline.trends import get_best_trend
        niche = config.get("niche", "horror")
        trend = await get_best_trend(niche)
        topic = trend.get("title", "A mysterious disappearance that no one can explain")
        result["steps"][-1] = {"step": "trends", "status": "done", "topic": topic}

        # Step 2: Get character
        from database import get_db
        db = await get_db()
        char_id = config.get("character_id", 1)
        rows = await db.execute_fetchall("SELECT * FROM characters WHERE id = ?", (char_id,))
        if not rows:
            rows = await db.execute_fetchall("SELECT * FROM characters LIMIT 1")
        if not rows:
            raise Exception("No characters found. Create one first.")

        character = dict(rows[0])
        try:
            character["sample_hooks"] = json.loads(character["sample_hooks"]) if character["sample_hooks"] else []
        except (json.JSONDecodeError, TypeError):
            character["sample_hooks"] = []

        # Step 3: Generate script
        result["steps"].append({"step": "script", "status": "running"})
        from pipeline.scriptwriter import generate_script
        language = config.get("language", "en")
        duration = config.get("duration", 60)
        script = await generate_script(character, topic, duration, language)
        result["steps"][-1] = {"step": "script", "status": "done", "title": script.get("title", "")}

        # Step 4: Save to DB
        cursor = await db.execute(
            """INSERT INTO videos (character_id, title, topic, script_json, status, language, duration_target)
               VALUES (?, ?, ?, ?, 'generating', ?, ?)""",
            (char_id, script.get("title", topic), topic, json.dumps(script), language, duration),
        )
        await db.commit()
        video_id = cursor.lastrowid

        # Step 5: Load settings
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            settings = json.load(f)

        scenes = script["scenes"]
        voice_id = character.get("voice_id", "en-US-GuyNeural")

        # Step 6: Generate voice
        result["steps"].append({"step": "voice", "status": "running"})
        from pipeline.voice import generate_all_scenes_audio
        audio_results = await generate_all_scenes_audio(
            scenes, voice_id, video_id,
            rate=settings.get("tts_rate", "-10%"),
            pitch=settings.get("tts_pitch", "-5Hz"),
        )
        result["steps"][-1] = {"step": "voice", "status": "done", "files": len(audio_results)}

        # Step 7: Generate music + mix
        result["steps"].append({"step": "music", "status": "running"})
        total_duration = sum(a["duration"] for a in audio_results)
        mixed_audio_path = None
        try:
            from pipeline.music import generate_background_music, mix_audio_with_music
            if settings.get("music_enabled", True):
                music_path = await generate_background_music(
                    duration=total_duration,
                    mood=settings.get("music_mood", "horror"),
                    video_id=video_id,
                )
                from pipeline.assembler import OUTPUT_DIR as FINAL_DIR
                os.makedirs(FINAL_DIR, exist_ok=True)
                narration_concat = os.path.join(FINAL_DIR, f"video_{video_id}_narration.mp3")
                # Concat narration files
                import subprocess
                concat_file = narration_concat + ".txt"
                with open(concat_file, "w", encoding="utf-8") as cf:
                    for af in sorted(audio_results, key=lambda x: x["scene_number"]):
                        p = af["path"].replace("\\", "/").replace("'", "'\\''")
                        cf.write(f"file '{p}'\n")
                subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", narration_concat],
                               capture_output=True, text=True)
                os.remove(concat_file)

                mixed_path = os.path.join(FINAL_DIR, f"video_{video_id}_mixed.mp3")
                mixed_audio_path = await mix_audio_with_music(
                    narration_concat, music_path, mixed_path,
                    music_volume_db=settings.get("music_volume_db", -20),
                )
                os.remove(narration_concat)
        except Exception as e:
            logger.warning(f"Music mixing failed, continuing without: {e}")
        result["steps"][-1] = {"step": "music", "status": "done"}

        # Step 8: Generate video clips
        result["steps"].append({"step": "video", "status": "running"})
        from pipeline.video_gen import generate_all_scenes_video
        video_clips = await generate_all_scenes_video(
            scenes, video_id, character.get("visual_prompt", ""),
        )
        result["steps"][-1] = {"step": "video", "status": "done", "clips": len(video_clips)}

        # Step 9: Generate subtitles
        result["steps"].append({"step": "subtitles", "status": "running"})
        from pipeline.subtitles import generate_ass
        ass_path = generate_ass(scenes, audio_results, video_id)
        result["steps"][-1] = {"step": "subtitles", "status": "done"}

        # Step 10: Assemble
        result["steps"].append({"step": "assembly", "status": "running"})
        from pipeline.assembler import assemble_video
        if mixed_audio_path:
            final_path = await assemble_video(
                video_clips, audio_results, ass_path, video_id,
                resolution=settings.get("video_resolution", "1080x1920"),
                merged_audio_path=mixed_audio_path,
            )
        else:
            final_path = await assemble_video(
                video_clips, audio_results, ass_path, video_id,
                resolution=settings.get("video_resolution", "1080x1920"),
            )
        result["steps"][-1] = {"step": "assembly", "status": "done"}

        # Step 11: Thumbnail
        result["steps"].append({"step": "thumbnail", "status": "running"})
        try:
            from pipeline.thumbnail import generate_thumbnail
            await generate_thumbnail(video_id, script.get("title", ""), final_path)
        except Exception:
            pass
        result["steps"][-1] = {"step": "thumbnail", "status": "done"}

        # Update DB
        await db.execute(
            "UPDATE videos SET status = 'done', output_path = ?, updated_at = datetime('now') WHERE id = ?",
            (final_path, video_id),
        )
        await db.commit()

        # Step 12: Auto-publish if enabled
        if config.get("auto_publish_youtube", False):
            result["steps"].append({"step": "publish", "status": "running"})
            try:
                from pipeline.publisher import publish_to_youtube
                yt_result = await publish_to_youtube(video_id)
                result["steps"][-1] = {"step": "publish", "status": "done", "url": yt_result.get("url", "")}
            except Exception as e:
                result["steps"][-1] = {"step": "publish", "status": "failed", "error": str(e)}

        await db.close()

        # Update counter
        config["videos_produced_today"] = config.get("videos_produced_today", 0) + 1
        save_schedule(config)

        result["status"] = "done"
        result["video_id"] = video_id
        result["title"] = script.get("title", "")
        result["output_path"] = final_path

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        logger.error(f"Scheduled production failed: {e}")

    # Notify
    if config.get("notify_on_complete", True):
        _notify(result)

    return result


def _notify(result: dict):
    """Send desktop notification (Windows)."""
    try:
        import ctypes
        status = result.get("status", "unknown")
        title = result.get("title", "Video")
        if status == "done":
            msg = f"✅ Video produced: {title}"
        elif status == "error":
            msg = f"❌ Production failed: {result.get('error', 'Unknown error')[:100]}"
        elif status == "skipped":
            msg = f"⏭ Skipped: {result.get('reason', '')}"
        else:
            return

        # Windows toast notification
        ctypes.windll.user32.MessageBoxW(0, msg, "Video Factory", 0x40)
    except Exception:
        # Fallback: just log it
        logger.info(f"Notification: {result.get('status')}: {result.get('title', '')}")


async def scheduler_loop():
    """
    Main scheduler loop. Runs forever, executing productions at scheduled times.
    Start this as a background task or standalone script.
    """
    logger.info("Scheduler started")
    config = load_schedule()

    if not config.get("enabled", False):
        logger.info("Scheduler is disabled. Enable it in the config.")
        return

    mode = config.get("mode", "daily")

    if mode == "on_start":
        # Run immediately, then exit
        logger.info("Mode: on_start — running once now")
        await run_scheduled_production(config)
        return

    while True:
        config = load_schedule()  # Reload config each cycle
        if not config.get("enabled", False):
            logger.info("Scheduler disabled. Stopping.")
            break

        now = datetime.now()

        if mode == "daily":
            # Check if current time matches any scheduled time
            current_time = now.strftime("%H:%M")
            daily_times = config.get("daily_times", ["08:00"])

            if current_time in daily_times:
                logger.info(f"Daily trigger at {current_time}")
                await run_scheduled_production(config)
                # Sleep 61 seconds to avoid re-triggering same minute
                await asyncio.sleep(61)
            else:
                await asyncio.sleep(30)  # Check every 30 seconds

        elif mode == "interval":
            hours = config.get("interval_hours", 12)
            logger.info(f"Interval mode: running every {hours} hours")
            await run_scheduled_production(config)
            await asyncio.sleep(hours * 3600)


# === Standalone entry point ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    asyncio.run(scheduler_loop())
