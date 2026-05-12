"""
Test #5 — XTTS v2 con transiciones PERFECTAS.
Cada clip se trimea exactamente a la duracion del audio. Zero gaps.
"""
import asyncio
import os
import sys
import subprocess
import json
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

SCRIPT = {
    "title": "El Espejo Que Sonreia",
    "voice": "xtts:default",
    "language": "es",
    "mood": "horror",
    "scenes": [
        {
            "scene_number": 1,
            "narration": "Sientate mijo. Esta historia nunca se la he contado a nadie.",
            "duration_seconds": 8,
        },
        {
            "scene_number": 2,
            "narration": "Mi vecina me llamo a las tres de la manana. Dijo que su reflejo en el espejo parpadeo cuando ella no lo hizo.",
            "duration_seconds": 12,
        },
        {
            "scene_number": 3,
            "narration": "Le dije que estaba cansada. Que se fuera a dormir. Pero entonces me envio el video.",
            "duration_seconds": 10,
        },
        {
            "scene_number": 4,
            "narration": "En el video, su reflejo estaba sonriendo. Pero ella estaba gritando.",
            "duration_seconds": 9,
        },
        {
            "scene_number": 5,
            "narration": "Esa noche cubrio todos los espejos de su casa. Pero a la manana siguiente encontro uno nuevo. Uno que nunca habia visto. Y ya la estaba mirando.",
            "duration_seconds": 16,
        },
    ],
}

CROSSFADE = 0.5


def get_duration(path):
    r = subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",path], capture_output=True, text=True)
    return float(r.stdout.strip())


async def main():
    print("=" * 50)
    print("VIDEO FACTORY — Test #5 PERFECT SYNC")
    print("XTTS v2 + Crossfade + Zero gaps")
    print("=" * 50)

    from pipeline.voice import generate_voice
    from pipeline.subtitles import generate_ass
    from pipeline.music import generate_ambient_track
    from PIL import Image, ImageDraw

    clips_dir = os.path.join(OUTPUT_DIR, "clips")
    audio_dir = os.path.join(OUTPUT_DIR, "audio")
    final_dir = os.path.join(OUTPUT_DIR, "final")
    os.makedirs(clips_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    palettes = [(35,22,12), (15,20,35), (20,30,18), (40,12,15), (18,15,28)]

    # ── STEP 1: Generate all audio first ──
    print("\n[1/5] VOZ — XTTS v2")
    audio_files = []
    for scene in SCRIPT["scenes"]:
        n = scene["scene_number"]
        t0 = time.time()
        result = await generate_voice(
            text=scene["narration"],
            voice_id=SCRIPT["voice"],
            output_filename=f"test5_scene_{n}.mp3",
            language=SCRIPT["language"],
        )
        elapsed = time.time() - t0
        audio_files.append({"scene_number": n, "path": result["path"], "duration": result["duration"]})
        print(f"  Escena {n}: audio={result['duration']:.2f}s (gen {elapsed:.1f}s)")

    # ── STEP 2: Generate clips MATCHED to audio duration ──
    print("\n[2/5] VISUALES — Matched to audio")
    clips = []
    for i, scene in enumerate(SCRIPT["scenes"]):
        n = scene["scene_number"]
        audio_dur = audio_files[i]["duration"]
        # Generate clip slightly longer than audio (buffer for crossfade)
        clip_dur = audio_dur + 1.0
        clip_path = os.path.join(clips_dir, f"test5_scene_{n}.mp4")
        img_path = os.path.join(clips_dir, f"test5_scene_{n}.png")

        base = palettes[n-1]
        img = Image.new("RGB", (1404, 2496), base)
        draw = ImageDraw.Draw(img)
        cx, cy = 702, 1248
        for y in range(0, 2496, 6):
            for x in range(0, 1404, 6):
                dist = ((x-cx)**2 + (y-cy)**2)**0.5
                f = max(0.2, 1.0 - 0.8*(dist/1420))
                draw.rectangle([x,y,x+6,y+6], fill=(int(base[0]*f),int(base[1]*f),int(base[2]*f)))
        img.save(img_path)

        frames = int(clip_dur * 24)
        subprocess.run([
            "ffmpeg","-y","-loop","1","-i",img_path,
            "-vf",f"zoompan=z='1+0.0015*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=24,format=yuv420p",
            "-t",str(clip_dur),"-c:v","libx264","-preset","fast","-crf","20","-pix_fmt","yuv420p",clip_path
        ], capture_output=True, text=True)

        clips.append({"scene_number": n, "path": clip_path})
        print(f"  Escena {n}: clip={clip_dur:.2f}s (audio={audio_dur:.2f}s)")
        os.remove(img_path)

    # ── STEP 3: Trim each clip to EXACT audio duration ──
    print("\n[3/5] SYNC — Trimming clips to audio")
    synced_clips = []
    for i, scene in enumerate(SCRIPT["scenes"]):
        n = scene["scene_number"]
        audio_dur = audio_files[i]["duration"]
        src = clips[i]["path"]
        synced_path = os.path.join(final_dir, f"test5_synced_{n}.mp4")

        subprocess.run([
            "ffmpeg","-y","-i",src,
            "-t",f"{audio_dur:.3f}",
            "-c:v","libx264","-preset","fast","-crf","18",
            "-pix_fmt","yuv420p","-an","-r","24",
            synced_path
        ], capture_output=True, text=True)

        actual = get_duration(synced_path)
        synced_clips.append(synced_path)
        diff = abs(actual - audio_dur)
        status = "OK" if diff < 0.1 else f"DRIFT {diff:.3f}s"
        print(f"  Escena {n}: video={actual:.3f}s audio={audio_dur:.3f}s [{status}]")

    # ── STEP 4: Crossfade all synced clips ──
    print("\n[4/5] CROSSFADE + MUSIC + SUBS")

    # Subtitles
    subs = generate_ass(scenes=SCRIPT["scenes"], audio_results=audio_files, video_id=5555)

    # Music
    total_audio_dur = sum(af["duration"] for af in audio_files)
    music = await generate_ambient_track(total_audio_dur + 2, mood="horror", output_filename="test5_ambient.mp3")

    # Crossfade video clips
    durations = [get_duration(p) for p in synced_clips]
    concat_video = os.path.join(final_dir, "test5_xfade.mp4")

    if len(synced_clips) >= 3:
        # Build xfade chain
        inputs = " ".join(f'-i "{p}"' for p in synced_clips)
        filter_parts = []
        accumulated = durations[0]

        offset = max(accumulated - CROSSFADE, 0.1)
        filter_parts.append(f"[0:v][1:v]xfade=transition=fade:duration={CROSSFADE}:offset={offset:.2f},setpts=PTS-STARTPTS[v1]")
        accumulated += durations[1] - CROSSFADE

        for j in range(2, len(synced_clips)):
            offset = max(accumulated - CROSSFADE, 0.1)
            filter_parts.append(f"[v{j-1}][{j}:v]xfade=transition=fade:duration={CROSSFADE}:offset={offset:.2f},setpts=PTS-STARTPTS[v{j}]")
            accumulated += durations[j] - CROSSFADE

        filtergraph = ";".join(filter_parts)
        last = f"v{len(synced_clips)-1}"
        cmd = f'ffmpeg -y {inputs} -filter_complex "{filtergraph}" -map "[{last}]" -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -an "{concat_video}"'
        proc = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        if proc.returncode != 0:
            print(f"  Crossfade failed, using simple concat: {proc.stderr[:200]}")
            listfile = os.path.join(final_dir, "test5_list.txt")
            with open(listfile,"w") as f:
                for p in synced_clips:
                    f.write(f"file '{p.replace(chr(92),'/')}'\n")
            subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",listfile,"-c","copy",concat_video], capture_output=True, text=True)
    else:
        listfile = os.path.join(final_dir, "test5_list.txt")
        with open(listfile,"w") as f:
            for p in synced_clips:
                f.write(f"file '{p.replace(chr(92),'/')}'\n")
        subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",listfile,"-c","copy",concat_video], capture_output=True, text=True)

    # Concat audio
    alist = os.path.join(audio_dir, "test5_alist.txt")
    with open(alist,"w") as f:
        for af in audio_files:
            f.write(f"file '{af['path'].replace(chr(92),'/')}'\n")
    concat_audio = os.path.join(audio_dir, "test5_narration.mp3")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",alist,"-c","copy",concat_audio], capture_output=True, text=True)

    # Mix audio + music
    mixed = os.path.join(final_dir, "test5_mixed.mp3")
    subprocess.run([
        "ffmpeg","-y","-i",concat_audio,"-i",music,
        "-filter_complex","[1:a]volume=0.06[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[out]",
        "-map","[out]","-c:a","libmp3lame","-b:a","192k",mixed
    ], capture_output=True, text=True)

    # ── STEP 5: Final merge ──
    print("\n[5/5] FINAL MERGE")
    final = os.path.join(final_dir, "OLD_EMILIO_xtts_perfect.mp4")
    sub_esc = subs.replace("\\","/").replace(":","\\:")

    proc = subprocess.run([
        "ffmpeg","-y","-i",concat_video,"-i",mixed,
        "-vf",f"ass='{sub_esc}'",
        "-c:v","libx264","-preset","slow","-crf","18",
        "-c:a","aac","-b:a","192k",
        "-shortest","-pix_fmt","yuv420p","-movflags","+faststart",final
    ], capture_output=True, text=True)

    if proc.returncode != 0:
        print(f"  Subs error, retrying without: {proc.stderr[:200]}")
        subprocess.run([
            "ffmpeg","-y","-i",concat_video,"-i",mixed,
            "-c:v","libx264","-preset","slow","-crf","18",
            "-c:a","aac","-b:a","192k",
            "-shortest","-pix_fmt","yuv420p","-movflags","+faststart",final
        ], capture_output=True, text=True)

    # Verify
    final_dur = get_duration(final)
    final_size = os.path.getsize(final) / (1024*1024)
    video_dur = get_duration(concat_video)
    audio_total = get_duration(concat_audio)
    print(f"  Video track: {video_dur:.2f}s")
    print(f"  Audio track: {audio_total:.2f}s")
    print(f"  Drift: {abs(video_dur - audio_total):.3f}s")
    print(f"  Final: {final_dur:.1f}s | {final_size:.1f}MB")

    # Cleanup
    for f in [concat_video, concat_audio, mixed, alist]:
        try: os.remove(f)
        except: pass
    for p in synced_clips:
        try: os.remove(p)
        except: pass

    print(f"\nLISTO: {final}")
    subprocess.Popen(["cmd", "/c", "start", "", final])


if __name__ == "__main__":
    asyncio.run(main())
