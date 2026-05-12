"""
Test #3 — Old Emilio en ESPAÑOL con Edge-TTS (mucho más natural que Kokoro)
Voice: es-MX-JorgeNeural, rate -20%, pitch -8Hz
Subtitles: Size 42
"""
import asyncio
import os
import sys
import subprocess
import json

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

SCRIPT = {
    "title": "El Espejo Que Sonreia",
    "voice": "es-MX-JorgeNeural",
    "rate": "-8%",
    "pitch": "-6Hz",
    "mood": "horror",
    "scenes": [
        {
            "scene_number": 1,
            "narration": "Sientate, mijo... Esta historia... nunca se la he contado a nadie.",
            "visual_prompt": "Old man sitting by campfire in dark forest, worn leather hat, shadows dancing on weathered face, cinematic, 4K, film grain, shallow depth of field",
            "duration_seconds": 7,
        },
        {
            "scene_number": 2,
            "narration": "Mi vecina me llamo a las tres de la manana. Dijo que su reflejo en el espejo... parpadeo... cuando ella no lo hizo.",
            "visual_prompt": "Woman frozen in front of bathroom mirror at night, reflection slightly different, cold blue moonlight, cinematic, 4K, film grain, shallow depth of field",
            "duration_seconds": 10,
        },
        {
            "scene_number": 3,
            "narration": "Le dije que estaba cansada. Que se fuera a dormir. Pero entonces... me envio el video.",
            "visual_prompt": "Close up of phone screen glowing in darkness showing grainy video, eerie green light on old hands, cinematic, 4K, film grain, shallow depth of field",
            "duration_seconds": 8,
        },
        {
            "scene_number": 4,
            "narration": "En el video... su reflejo estaba sonriendo. Pero ella... estaba gritando.",
            "visual_prompt": "Split view of terrified woman and her calm smiling reflection in cracked mirror, red and blue horror lighting, cinematic, 4K, film grain, shallow depth of field",
            "duration_seconds": 8,
        },
        {
            "scene_number": 5,
            "narration": "Esa noche, cubrio todos los espejos de su casa. Pero a la manana siguiente... encontro uno nuevo. Uno que nunca habia visto. Y ya la estaba mirando.",
            "visual_prompt": "Dark hallway with sheets covering mirrors, one uncovered mirror at end glowing faintly, mysterious silhouette inside reflection, fog, cinematic, 4K, film grain, shallow depth of field",
            "duration_seconds": 14,
        },
    ],
}


async def step1_voice():
    print("\n[1/5] VOZ — Edge-TTS es-MX-JorgeNeural (-8%, -6Hz)")
    from pipeline.voice import generate_voice

    audio_files = []
    for scene in SCRIPT["scenes"]:
        n = scene["scene_number"]
        result = await generate_voice(
            text=scene["narration"],
            voice_id=SCRIPT["voice"],
            output_filename=f"test3_scene_{n}.mp3",
            rate=SCRIPT["rate"],
            pitch=SCRIPT["pitch"],
        )
        audio_files.append({"scene_number": n, "path": result["path"], "duration": result["duration"]})
        print(f"  Escena {n}: {result['duration']:.1f}s")
    return audio_files


async def step2_subtitles(audio_files):
    print("\n[2/5] SUBTITULOS — Size 42, palabra por palabra")
    from pipeline.subtitles import generate_ass
    result = generate_ass(scenes=SCRIPT["scenes"], audio_results=audio_files, video_id=7777)
    print(f"  Archivo: {result}")
    return result


async def step3_visuals():
    print("\n[3/5] VISUALES — Placeholder + Ken Burns")
    from PIL import Image, ImageDraw

    clips_dir = os.path.join(OUTPUT_DIR, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    clips = []
    palettes = [
        (35, 22, 12),   # Campfire warm
        (15, 20, 35),   # Cold blue bathroom
        (20, 30, 18),   # Green phone
        (40, 12, 15),   # Red horror
        (18, 15, 28),   # Purple fog
    ]

    for scene in SCRIPT["scenes"]:
        n = scene["scene_number"]
        dur = scene["duration_seconds"]
        clip_path = os.path.join(clips_dir, f"test3_scene_{n}.mp4")
        img_path = os.path.join(clips_dir, f"test3_scene_{n}.png")

        img_w, img_h = 1404, 2496
        base = palettes[n - 1]
        img = Image.new("RGB", (img_w, img_h), base)
        draw = ImageDraw.Draw(img)

        cx, cy = img_w // 2, img_h // 2
        for y in range(0, img_h, 6):
            for x in range(0, img_w, 6):
                dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                max_dist = (cx ** 2 + cy ** 2) ** 0.5
                factor = max(0.2, 1.0 - 0.8 * (dist / max_dist))
                r = int(base[0] * factor)
                g = int(base[1] * factor)
                b = int(base[2] * factor)
                draw.rectangle([x, y, x + 6, y + 6], fill=(r, g, b))

        img.save(img_path)

        fps = 24
        frames = dur * fps
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", img_path,
            "-vf", f"zoompan=z='1+0.0015*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps={fps},format=yuv420p",
            "-t", str(dur), "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", clip_path
        ], capture_output=True, text=True)

        clips.append({"scene_number": n, "path": clip_path})
        print(f"  Escena {n}: {dur}s")
        os.remove(img_path)

    return clips


async def step4_music(total_dur):
    print("\n[4/5] MUSICA — Horror ambient")
    from pipeline.music import generate_ambient_track
    path = await generate_ambient_track(total_dur + 2, mood="horror", output_filename="test3_ambient.mp3")
    print(f"  Archivo: {path}")
    return path


async def step5_assemble(clips, audio_files, subs, music):
    print("\n[5/5] ENSAMBLANDO...")
    audio_dir = os.path.join(OUTPUT_DIR, "audio")
    final_dir = os.path.join(OUTPUT_DIR, "final")
    os.makedirs(final_dir, exist_ok=True)

    # Concat audio
    alist = os.path.join(audio_dir, "test3_list.txt")
    with open(alist, "w") as f:
        for af in sorted(audio_files, key=lambda x: x["scene_number"]):
            f.write(f"file '{af['path'].replace(chr(92), '/')}'\n")
    concat_a = os.path.join(audio_dir, "test3_narration.mp3")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", alist, "-c", "copy", concat_a], capture_output=True, text=True)

    # Concat video
    vlist = os.path.join(final_dir, "test3_vlist.txt")
    with open(vlist, "w") as f:
        for c in sorted(clips, key=lambda x: x["scene_number"]):
            f.write(f"file '{c['path'].replace(chr(92), '/')}'\n")
    concat_v = os.path.join(final_dir, "test3_vconcat.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", vlist, "-c", "copy", concat_v], capture_output=True, text=True)

    # Mix
    mixed = os.path.join(final_dir, "test3_mixed.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-i", concat_a, "-i", music,
        "-filter_complex", "[1:a]volume=0.06[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[out]",
        "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k", mixed
    ], capture_output=True, text=True)

    # Final
    final = os.path.join(final_dir, "OLD_EMILIO_espejo_esp.mp4")
    sub_esc = subs.replace("\\", "/").replace(":", "\\:")

    proc = subprocess.run([
        "ffmpeg", "-y", "-i", concat_v, "-i", mixed,
        "-vf", f"ass='{sub_esc}'",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-pix_fmt", "yuv420p", "-movflags", "+faststart", final
    ], capture_output=True, text=True)

    if proc.returncode != 0:
        print(f"  Error subs: {proc.stderr[:200]}")
        subprocess.run([
            "ffmpeg", "-y", "-i", concat_v, "-i", mixed,
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-pix_fmt", "yuv420p", "-movflags", "+faststart", final
        ], capture_output=True, text=True)

    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration,size", "-of", "json", final],
        capture_output=True, text=True)
    if probe.returncode == 0:
        info = json.loads(probe.stdout)
        print(f"  Duracion: {float(info['format']['duration']):.1f}s | Peso: {int(info['format']['size'])/(1024*1024):.1f}MB")

    for f in [concat_a, concat_v, mixed, alist, vlist]:
        try: os.remove(f)
        except: pass

    return final


async def main():
    print("=" * 50)
    print("VIDEO FACTORY — Test #3 ESPAÑOL")
    print(f"'{SCRIPT['title']}' — Old Emilio")
    print("Voz: Edge-TTS es-MX-JorgeNeural -8% -6Hz")
    print("Subtitulos: Size 42")
    print("=" * 50)

    audio = await step1_voice()
    subs = await step2_subtitles(audio)
    clips = await step3_visuals()
    music = await step4_music(sum(s["duration_seconds"] for s in SCRIPT["scenes"]))
    final = await step5_assemble(clips, audio, subs, music)

    if final:
        print(f"\nLISTO: {final}")
        subprocess.Popen(["cmd", "/c", "start", "", final])


if __name__ == "__main__":
    asyncio.run(main())
