"""
Full video production test #2 — Old Emilio horror story.
Fixes: bigger subtitles (42), slower voice (0.8), Kokoro am_adam
"""
import asyncio
import os
import sys
import subprocess
import json
import numpy as np

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

OUTPUT_DIR = os.path.join(BASE_DIR, "output")

SCRIPT = {
    "title": "The Mirror Smiled Back",
    "character": "old_emilio",
    "voice": "kokoro:am_adam",
    "mood": "horror",
    "scenes": [
        {
            "scene_number": 1,
            "narration": "Kid... have you ever looked in a mirror... and noticed something wrong?",
            "visual_prompt": "Dark bathroom, cracked antique mirror reflecting dim candlelight, water droplets on glass, fog, cinematic, 4K, film grain, shallow depth of field",
            "duration_seconds": 6,
        },
        {
            "scene_number": 2,
            "narration": "My neighbor called me at three in the morning. Said her reflection... blinked... when she didn't.",
            "visual_prompt": "Woman standing frozen in front of bathroom mirror at night, her reflection slightly different pose, cold blue light from window, cinematic, 4K, film grain, shallow depth of field",
            "duration_seconds": 9,
        },
        {
            "scene_number": 3,
            "narration": "I told her she was tired. Seeing things. But then she sent me the video.",
            "visual_prompt": "Close up of old phone screen showing grainy video footage in darkness, eerie green glow from screen illuminating weathered hands, cinematic, 4K, film grain, shallow depth of field",
            "duration_seconds": 7,
        },
        {
            "scene_number": 4,
            "narration": "In the video... her reflection was smiling. But she was screaming.",
            "visual_prompt": "Split frame showing terrified woman on one side and her calm smiling reflection on the other side of a mirror, horror contrast, red and blue lighting, cinematic, 4K, film grain, shallow depth of field",
            "duration_seconds": 7,
        },
        {
            "scene_number": 5,
            "narration": "She covered every mirror in the house that night. But the next morning... she found a new one. One she had never seen before. And it was already looking at her.",
            "visual_prompt": "Dark hallway with sheets covering mirrors on walls, one uncovered mirror at the end glowing faintly, silhouette visible inside the reflection that doesnt match anything in the room, fog, cinematic, 4K, film grain, shallow depth of field",
            "duration_seconds": 14,
        },
    ],
}


async def step1_voice():
    print("\n[1/5] VOICE — Kokoro am_adam, speed 0.8")
    from pipeline.voice import generate_voice

    audio_files = []
    for scene in SCRIPT["scenes"]:
        n = scene["scene_number"]
        result = await generate_voice(
            text=scene["narration"],
            voice_id=SCRIPT["voice"],
            output_filename=f"test2_scene_{n}.mp3",
        )
        audio_files.append({"scene_number": n, "path": result["path"], "duration": result["duration"]})
        print(f"  Scene {n}: {result['duration']:.1f}s")

    return audio_files


async def step2_subtitles(audio_files):
    print("\n[2/5] SUBTITLES — Size 42, word-by-word")
    from pipeline.subtitles import generate_ass

    result = generate_ass(
        scenes=SCRIPT["scenes"],
        audio_results=audio_files,
        video_id=8888,
    )
    # Verify the size in the generated file
    with open(result, "r") as f:
        header = f.readline()
        for line in f:
            if line.startswith("Style:"):
                print(f"  Style: {line.strip()[:100]}")
                break
    print(f"  Output: {result}")
    return result


async def step3_visuals():
    print("\n[3/5] VISUALS — Placeholder + Ken Burns")
    from PIL import Image, ImageDraw, ImageFont

    clips_dir = os.path.join(OUTPUT_DIR, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    clips = []
    palettes = [
        (20, 25, 35),   # Scene 1: Dark cold blue (bathroom)
        (15, 20, 35),   # Scene 2: Colder blue
        (20, 30, 20),   # Scene 3: Green phone glow
        (35, 15, 20),   # Scene 4: Red horror
        (18, 18, 25),   # Scene 5: Dark purple fog
    ]

    for scene in SCRIPT["scenes"]:
        n = scene["scene_number"]
        dur = scene["duration_seconds"]
        clip_path = os.path.join(clips_dir, f"test2_scene_{n}.mp4")
        img_path = os.path.join(clips_dir, f"test2_scene_{n}.png")

        W, H = 1080, 1920
        img_w, img_h = int(W * 1.3), int(H * 1.3)
        base = palettes[n - 1]
        img = Image.new("RGB", (img_w, img_h), base)
        draw = ImageDraw.Draw(img)

        # Radial gradient from center
        cx, cy = img_w // 2, img_h // 2
        for y in range(0, img_h, 4):
            for x in range(0, img_w, 4):
                dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                max_dist = (cx ** 2 + cy ** 2) ** 0.5
                factor = max(0.3, 1.0 - 0.7 * (dist / max_dist))
                r = int(base[0] * factor)
                g = int(base[1] * factor)
                b = int(base[2] * factor)
                draw.rectangle([x, y, x + 4, y + 4], fill=(r, g, b))

        img.save(img_path)

        fps = 24
        total_frames = dur * fps
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", img_path,
            "-vf", (
                f"zoompan=z='1+0.0015*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={total_frames}:s=1080x1920:fps={fps},format=yuv420p"
            ),
            "-t", str(dur),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p", clip_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            cmd2 = [
                "ffmpeg", "-y", "-loop", "1", "-i", img_path,
                "-t", str(dur), "-vf", "scale=1080:1920,format=yuv420p",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-r", "24", clip_path,
            ]
            subprocess.run(cmd2, capture_output=True, text=True)

        clips.append({"scene_number": n, "path": clip_path})
        print(f"  Scene {n}: {dur}s")
        os.remove(img_path)

    return clips


async def step4_music(total_duration):
    print("\n[4/5] MUSIC — Horror ambient")
    from pipeline.music import generate_ambient_track
    path = await generate_ambient_track(total_duration + 2, mood="horror", output_filename="test2_ambient.mp3")
    print(f"  Output: {path}")
    return path


async def step5_assemble(clips, audio_files, subtitle_path, music_path):
    print("\n[5/5] ASSEMBLING...")
    audio_dir = os.path.join(OUTPUT_DIR, "audio")
    final_dir = os.path.join(OUTPUT_DIR, "final")
    os.makedirs(final_dir, exist_ok=True)

    # Concat audio
    audio_list = os.path.join(audio_dir, "test2_list.txt")
    with open(audio_list, "w") as f:
        for af in sorted(audio_files, key=lambda x: x["scene_number"]):
            f.write(f"file '{af['path'].replace(chr(92), '/')}'\n")
    concat_audio = os.path.join(audio_dir, "test2_narration.mp3")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", audio_list, "-c", "copy", concat_audio],
                   capture_output=True, text=True)

    # Concat video
    video_list = os.path.join(final_dir, "test2_vlist.txt")
    with open(video_list, "w") as f:
        for c in sorted(clips, key=lambda x: x["scene_number"]):
            f.write(f"file '{c['path'].replace(chr(92), '/')}'\n")
    concat_video = os.path.join(final_dir, "test2_vconcat.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", video_list, "-c", "copy", concat_video],
                   capture_output=True, text=True)

    # Mix audio + music
    mixed = os.path.join(final_dir, "test2_mixed.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-i", concat_audio, "-i", music_path,
        "-filter_complex", "[1:a]volume=0.07[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[out]",
        "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k", mixed
    ], capture_output=True, text=True)

    # Final: video + audio + subtitles
    final_output = os.path.join(final_dir, "OLD_EMILIO_the_mirror.mp4")
    sub_esc = subtitle_path.replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y", "-i", concat_video, "-i", mixed,
        "-vf", f"ass='{sub_esc}'",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        final_output,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.returncode != 0:
        print(f"  ERROR with subs: {proc.stderr[:300]}")
        print("  Retrying without subs...")
        cmd_nosub = [
            "ffmpeg", "-y", "-i", concat_video, "-i", mixed,
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            final_output,
        ]
        subprocess.run(cmd_nosub, capture_output=True, text=True)

    # Info
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration,size", "-of", "json", final_output],
        capture_output=True, text=True,
    )
    if probe.returncode == 0:
        info = json.loads(probe.stdout)
        dur = float(info["format"]["duration"])
        size = int(info["format"]["size"]) / (1024 * 1024)
        print(f"  Duration: {dur:.1f}s | Size: {size:.1f}MB")

    # Cleanup temp files
    for f in [concat_audio, concat_video, mixed, audio_list, video_list]:
        try: os.remove(f)
        except: pass

    return final_output


async def main():
    print("=" * 50)
    print("VIDEO FACTORY — Test #2")
    print(f"'{SCRIPT['title']}' — Old Emilio (am_adam)")
    print("Subtitle size: 42 | Voice speed: 0.8")
    print("=" * 50)

    audio = await step1_voice()
    subs = await step2_subtitles(audio)
    clips = await step3_visuals()
    total_dur = sum(s["duration_seconds"] for s in SCRIPT["scenes"])
    music = await step4_music(total_dur)
    final = await step5_assemble(clips, audio, subs, music)

    if final:
        print(f"\nDONE: {final}")
        # Auto open
        subprocess.Popen(["cmd", "/c", "start", "", final])
    else:
        print("\nFAILED")


if __name__ == "__main__":
    asyncio.run(main())
