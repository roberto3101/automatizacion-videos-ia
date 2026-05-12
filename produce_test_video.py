"""
Full video production test — Old Emilio horror story.
Runs the entire pipeline: voice → subtitles → visuals → music → assemble
"""
import asyncio
import os
import sys
import subprocess
import json
import numpy as np

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# ─── THE SCRIPT ─────────────────────────────────────────────────────────
SCRIPT = {
    "title": "The Door That Wasnt There Before",
    "character": "old_emilio",
    "voice": "kokoro:am_adam",
    "mood": "horror",
    "scenes": [
        {
            "scene_number": 1,
            "narration": "There's a door in my grandmother's house... that wasn't there last week.",
            "visual_prompt": "Dark hallway in old house, mysterious wooden door at the end, flickering warm light underneath, dust particles, cinematic, 4K, film grain, shallow depth of field",
            "duration_seconds": 7,
        },
        {
            "scene_number": 2,
            "narration": "She told me never to open it. Said it showed up the night my grandfather died.",
            "visual_prompt": "Close up of elderly woman's weathered hands gripping a rosary, dim candlelight, old wooden table, fear in the shadows, cinematic, 4K, film grain, shallow depth of field",
            "duration_seconds": 8,
        },
        {
            "scene_number": 3,
            "narration": "But last night... I heard knocking. Three slow knocks. From the other side.",
            "visual_prompt": "POV shot of dark wooden door in shadows, three scratch marks glowing faintly, cold blue moonlight through cracked window, cinematic, 4K, film grain, shallow depth of field",
            "duration_seconds": 8,
        },
        {
            "scene_number": 4,
            "narration": "And then... my grandfather's voice. Whispering my name.",
            "visual_prompt": "Extreme close up of a door handle slowly turning by itself in darkness, faint ghostly mist seeping from under the door, warm amber vs cold blue lighting, cinematic, 4K, film grain, shallow depth of field",
            "duration_seconds": 7,
        },
        {
            "scene_number": 5,
            "narration": "I opened it. And kid... I wish I hadn't. Because what was behind that door... was my own bedroom. And I was already sleeping in it.",
            "visual_prompt": "Wide shot through doorway revealing a dark bedroom with a figure sleeping in bed seen from behind, impossible recursive loop feeling, eerie green tint, fog, cinematic, 4K, film grain, shallow depth of field",
            "duration_seconds": 12,
        },
    ],
}


async def step1_generate_voice():
    """Generate voice for each scene using Kokoro."""
    print("\n🎙️  STEP 1: Generating voice with Kokoro...")
    from pipeline.voice import generate_voice

    audio_files = []
    full_text = ""
    for scene in SCRIPT["scenes"]:
        n = scene["scene_number"]
        print(f"  Scene {n}: {scene['narration'][:50]}...")
        result = await generate_voice(
            text=scene["narration"],
            voice_id=SCRIPT["voice"],
            output_filename=f"test_scene_{n}.mp3",
        )
        audio_files.append({"scene_number": n, "path": result["path"], "duration": result["duration"]})
        full_text += scene["narration"] + " "
        print(f"    ✓ Duration: {result['duration']:.1f}s → {result['path']}")

    # Also generate a single combined audio for subtitles
    print("  Generating combined audio for subtitles...")
    combined_result = await generate_voice(
        text=full_text.strip(),
        voice_id=SCRIPT["voice"],
        output_filename="test_combined.mp3",
    )
    print(f"    ✓ Combined: {combined_result['duration']:.1f}s")

    return audio_files, combined_result


async def step2_generate_subtitles(audio_files):
    """Generate word-level ASS subtitles using Whisper."""
    print("\n📝 STEP 2: Generating subtitles with Whisper...")
    from pipeline.subtitles import generate_ass

    scenes = SCRIPT["scenes"]
    # audio_results needs same format as pipeline expects
    audio_results = [
        {"scene_number": af["scene_number"], "path": af["path"], "duration": af["duration"]}
        for af in audio_files
    ]

    result = generate_ass(
        scenes=scenes,
        audio_results=audio_results,
        video_id=9999,
    )
    print(f"    ✓ Subtitles: {result}")
    return result


async def step3_generate_visuals():
    """Generate placeholder video clips from colored frames with Ken Burns effect."""
    print("\n🎨 STEP 3: Generating visual clips (placeholder + Ken Burns)...")
    from PIL import Image, ImageDraw, ImageFont

    clips_dir = os.path.join(OUTPUT_DIR, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    clips = []
    # Color palettes for each scene (dark horror tones)
    palettes = [
        (30, 20, 15),    # Scene 1: Dark warm brown
        (25, 15, 10),    # Scene 2: Candlelight dark
        (10, 15, 30),    # Scene 3: Cold blue moonlight
        (20, 18, 25),    # Scene 4: Dark purple mist
        (15, 25, 20),    # Scene 5: Eerie green
    ]

    for scene in SCRIPT["scenes"]:
        n = scene["scene_number"]
        dur = scene["duration_seconds"]
        clip_path = os.path.join(clips_dir, f"test_scene_{n}.mp4")
        img_path = os.path.join(clips_dir, f"test_scene_{n}.png")

        # Create a moody image with text overlay
        W, H = 1080, 1920
        # Make image larger for Ken Burns zoom
        img_w, img_h = int(W * 1.3), int(H * 1.3)
        base_color = palettes[n - 1]
        img = Image.new("RGB", (img_w, img_h), base_color)
        draw = ImageDraw.Draw(img)

        # Add gradient effect (darker at top and bottom)
        for y in range(img_h):
            factor = 1.0 - 0.4 * abs(y - img_h // 2) / (img_h // 2)
            for x in range(0, img_w, 20):  # Step by 20 for speed
                r = int(base_color[0] * factor)
                g = int(base_color[1] * factor)
                b = int(base_color[2] * factor)
                draw.rectangle([x, y, x + 20, y + 1], fill=(r, g, b))

        # Add scene text (visual prompt as atmosphere indicator)
        try:
            font = ImageFont.truetype("arial.ttf", 36)
            font_small = ImageFont.truetype("arial.ttf", 24)
        except OSError:
            font = ImageFont.load_default()
            font_small = font

        # Scene number
        draw.text((img_w // 2, img_h // 2 - 100), f"Scene {n}", fill=(255, 255, 255), font=font, anchor="mm")
        # Short visual description
        short_desc = scene["visual_prompt"][:60] + "..."
        draw.text((img_w // 2, img_h // 2 + 50), short_desc, fill=(180, 180, 180), font=font_small, anchor="mm")

        img.save(img_path)

        # Create video with Ken Burns (slow zoom in) effect using FFmpeg
        # zoompan: zoom from 1.0 to 1.3 over duration, panning slightly
        fps = 24
        total_frames = dur * fps
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img_path,
            "-vf", (
                f"zoompan=z='1+0.002*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={total_frames}:s=1080x1920:fps={fps},"
                f"format=yuv420p"
            ),
            "-t", str(dur),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            clip_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"    ✗ Scene {n} failed: {proc.stderr[:200]}")
            # Fallback: simple static frame video
            cmd_fallback = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", img_path,
                "-t", str(dur),
                "-vf", "scale=1080:1920,format=yuv420p",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-r", "24",
                clip_path,
            ]
            subprocess.run(cmd_fallback, capture_output=True, text=True)

        clips.append({"scene_number": n, "path": clip_path})
        print(f"    ✓ Scene {n}: {dur}s clip → {clip_path}")

        # Clean up temp image
        os.remove(img_path)

    return clips


async def step4_generate_music(total_duration):
    """Generate background music."""
    print("\n🎵 STEP 4: Generating background music...")
    from pipeline.music import generate_ambient_track

    music_path = await generate_ambient_track(
        duration=total_duration + 2,  # Extra 2s for fade out
        mood="horror",
        output_filename="test_ambient.mp3",
    )
    print(f"    ✓ Music: {music_path}")
    return music_path


async def step5_assemble(clips, audio_files, subtitle_path, music_path):
    """Assemble everything into final video."""
    print("\n🎬 STEP 5: Assembling final video...")

    # First: concat all scene audios into one
    audio_dir = os.path.join(OUTPUT_DIR, "audio")
    final_dir = os.path.join(OUTPUT_DIR, "final")
    os.makedirs(final_dir, exist_ok=True)

    # Concat audio files
    audio_list_path = os.path.join(audio_dir, "test_concat_list.txt")
    with open(audio_list_path, "w") as f:
        for af in sorted(audio_files, key=lambda x: x["scene_number"]):
            p = af["path"].replace("\\", "/")
            f.write(f"file '{p}'\n")

    concat_audio = os.path.join(audio_dir, "test_narration_full.mp3")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", audio_list_path, "-c", "copy", concat_audio]
    subprocess.run(cmd, capture_output=True, text=True)

    # Concat video clips (simple concat since they're same resolution)
    video_list_path = os.path.join(final_dir, "test_video_list.txt")
    with open(video_list_path, "w") as f:
        for clip in sorted(clips, key=lambda x: x["scene_number"]):
            p = clip["path"].replace("\\", "/")
            f.write(f"file '{p}'\n")

    concat_video = os.path.join(final_dir, "test_video_concat.mp4")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", video_list_path, "-c", "copy", concat_video]
    subprocess.run(cmd, capture_output=True, text=True)

    # Mix narration + music (music at -20dB under narration)
    mixed_audio = os.path.join(final_dir, "test_mixed_audio.mp3")
    cmd = [
        "ffmpeg", "-y",
        "-i", concat_audio,
        "-i", music_path,
        "-filter_complex",
        "[1:a]volume=0.08[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[out]",
        "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k",
        mixed_audio,
    ]
    subprocess.run(cmd, capture_output=True, text=True)

    # Final merge: video + mixed audio + subtitles
    final_output = os.path.join(final_dir, "OLD_EMILIO_the_door.mp4")
    sub_escaped = subtitle_path.replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-i", concat_video,
        "-i", mixed_audio,
        "-vf", f"ass='{sub_escaped}'",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        final_output,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"    ✗ Assembly failed: {proc.stderr[:500]}")
        # Try without subtitles
        print("    Retrying without subtitles...")
        cmd_nosub = [
            "ffmpeg", "-y",
            "-i", concat_video,
            "-i", mixed_audio,
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            final_output,
        ]
        proc = subprocess.run(cmd_nosub, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"    ✗ Assembly without subs also failed: {proc.stderr[:300]}")
            return None

    print(f"\n    ✅ FINAL VIDEO: {final_output}")

    # Get file info
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration,size", "-of", "json", final_output],
        capture_output=True, text=True,
    )
    if probe.returncode == 0:
        info = json.loads(probe.stdout)
        dur = float(info["format"]["duration"])
        size = int(info["format"]["size"]) / (1024 * 1024)
        print(f"    Duration: {dur:.1f}s | Size: {size:.1f}MB")

    return final_output


async def main():
    print("=" * 60)
    print("🎬 VIDEO FACTORY — Full Production Test")
    print(f"📖 \"{SCRIPT['title']}\" — Old Emilio")
    print("=" * 60)

    # Step 1: Voice
    audio_files, combined_audio = await step1_generate_voice()

    # Step 2: Subtitles
    subtitle_path = await step2_generate_subtitles(audio_files)

    # Step 3: Visuals
    clips = await step3_generate_visuals()

    # Step 4: Music
    total_dur = sum(s["duration_seconds"] for s in SCRIPT["scenes"])
    music_path = await step4_generate_music(total_dur)

    # Step 5: Assemble
    final = await step5_assemble(clips, audio_files, subtitle_path, music_path)

    if final:
        print("\n" + "=" * 60)
        print("✅ PRODUCTION COMPLETE!")
        print(f"📁 Open: {final}")
        print("=" * 60)
    else:
        print("\n❌ Production failed. Check errors above.")


if __name__ == "__main__":
    asyncio.run(main())
