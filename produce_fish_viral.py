"""
Video viral estilo esqueleto — Fish Audio S2 (best quality)
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
    "title": "Y si Julio Cesar tuviera un canal de YouTube",
    "voice": "es-MX-JorgeNeural",
    "rate": "+3%",
    "pitch": "-2Hz",
    "language": "es",
    "scenes": [
        {
            "scene_number": 1,
            "narration": "Imagina que Julio Cesar, el emperador mas famoso de Roma, tuviera un canal de YouTube.",
        },
        {
            "scene_number": 2,
            "narration": "Su primer video seria: Como conquistar las Galias en diez pasos. Y tendria tres millones de vistas en un dia.",
        },
        {
            "scene_number": 3,
            "narration": "Pero lo mejor seria su seccion de comentarios. Cleopatra le dejaria un corazon, y Bruto comentaria: Gran video, hermano. Pero tengo unas sugerencias.",
        },
        {
            "scene_number": 4,
            "narration": "Su video mas viral seria un Que hay en mi toga, donde mostraria su espada favorita, su corona de laurel, y un mapa de todos los territorios que quiere conquistar la proxima semana.",
        },
        {
            "scene_number": 5,
            "narration": "Pero un dia subiria un video titulado: Por que no confio en mis amigos del Senado. Y Bruto le dejaria un dislike. Solo uno. Pero el mas importante de la historia.",
        },
        {
            "scene_number": 6,
            "narration": "Julio Cesar no necesitaba un imperio. Necesitaba un buen editor de video y WiFi.",
        },
    ],
}

CROSSFADE = 0.4


def get_dur(path):
    r = subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",path], capture_output=True, text=True)
    return float(r.stdout.strip())


async def main():
    print("=" * 50)
    print("VIDEO FACTORY — Julio Cesar YouTube")
    print(f"'{SCRIPT['title']}'")
    print("=" * 50)

    from pipeline.voice import generate_voice
    from pipeline.subtitles import generate_ass
    from pipeline.music import generate_ambient_track
    from PIL import Image, ImageDraw

    clips_dir = os.path.join(OUTPUT_DIR, "clips")
    audio_dir = os.path.join(OUTPUT_DIR, "audio")
    final_dir = os.path.join(OUTPUT_DIR, "final")
    for d in [clips_dir, audio_dir, final_dir]:
        os.makedirs(d, exist_ok=True)

    palettes = [
        (50, 30, 15),   # Gold Roman
        (35, 25, 45),   # Purple imperial
        (20, 35, 50),   # Blue social
        (45, 35, 20),   # Warm toga
        (40, 15, 15),   # Red betrayal
        (50, 45, 15),   # Gold epic
    ]

    # ── 1. VOICE with Fish Audio ──
    print("\n[1/5] VOZ — Edge-TTS JorgeNeural +3%")
    audio_files = []
    for scene in SCRIPT["scenes"]:
        n = scene["scene_number"]
        t0 = time.time()
        result = await generate_voice(
            text=scene["narration"],
            voice_id=SCRIPT["voice"],
            output_filename=f"fish_scene_{n}.mp3",
            rate=SCRIPT.get("rate", "+0%"),
            pitch=SCRIPT.get("pitch", "+0Hz"),
        )
        elapsed = time.time() - t0
        audio_files.append({"scene_number": n, "path": result["path"], "duration": result["duration"]})
        print(f"  Escena {n}: {result['duration']:.2f}s (gen {elapsed:.1f}s)")

    total_audio = sum(af["duration"] for af in audio_files)
    print(f"  TOTAL: {total_audio:.1f}s")

    # ── 2. VISUALS matched to audio ──
    print("\n[2/5] VISUALES")
    clips = []
    for i, scene in enumerate(SCRIPT["scenes"]):
        n = scene["scene_number"]
        audio_dur = audio_files[i]["duration"]
        clip_dur = audio_dur + 1.0
        clip_path = os.path.join(clips_dir, f"fish_scene_{n}.mp4")
        img_path = os.path.join(clips_dir, f"fish_scene_{n}.png")

        base = palettes[n-1]
        img = Image.new("RGB", (1404, 2496), base)
        draw = ImageDraw.Draw(img)
        cx, cy = 702, 1248
        for y in range(0, 2496, 8):
            for x in range(0, 1404, 8):
                dist = ((x-cx)**2 + (y-cy)**2)**0.5
                f = max(0.3, 1.0 - 0.7*(dist/1420))
                draw.rectangle([x,y,x+8,y+8], fill=(int(base[0]*f),int(base[1]*f),int(base[2]*f)))
        img.save(img_path)

        frames = int(clip_dur * 24)
        subprocess.run([
            "ffmpeg","-y","-loop","1","-i",img_path,
            "-vf",f"zoompan=z='1+0.002*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=24,format=yuv420p",
            "-t",str(clip_dur),"-c:v","libx264","-preset","fast","-crf","20","-pix_fmt","yuv420p",clip_path
        ], capture_output=True, text=True)
        clips.append({"scene_number": n, "path": clip_path})
        os.remove(img_path)

    # ── 3. SYNC ──
    print("\n[3/5] SYNC")
    synced = []
    for i in range(len(SCRIPT["scenes"])):
        n = SCRIPT["scenes"][i]["scene_number"]
        audio_dur = audio_files[i]["duration"]
        sp = os.path.join(final_dir, f"fish_synced_{n}.mp4")
        subprocess.run([
            "ffmpeg","-y","-i",clips[i]["path"],
            "-t",f"{audio_dur:.3f}",
            "-c:v","libx264","-preset","fast","-crf","18",
            "-pix_fmt","yuv420p","-an","-r","24",sp
        ], capture_output=True, text=True)
        synced.append(sp)
        actual = get_dur(sp)
        print(f"  Escena {n}: {actual:.3f}s == {audio_dur:.3f}s [{'OK' if abs(actual-audio_dur)<0.1 else 'DRIFT'}]")

    # ── 4. ASSEMBLE ──
    print("\n[4/5] ENSAMBLE")
    subs = generate_ass(scenes=SCRIPT["scenes"], audio_results=audio_files, video_id=3333)
    music = await generate_ambient_track(total_audio + 2, mood="epic", output_filename="fish_music.mp3")

    # Crossfade
    durs = [get_dur(p) for p in synced]
    concat_v = os.path.join(final_dir, "fish_xfade.mp4")
    inputs = " ".join(f'-i "{p}"' for p in synced)
    fp = []
    acc = durs[0]
    off = max(acc - CROSSFADE, 0.1)
    fp.append(f"[0:v][1:v]xfade=transition=fade:duration={CROSSFADE}:offset={off:.2f},setpts=PTS-STARTPTS[v1]")
    acc += durs[1] - CROSSFADE
    for j in range(2, len(synced)):
        off = max(acc - CROSSFADE, 0.1)
        fp.append(f"[v{j-1}][{j}:v]xfade=transition=fade:duration={CROSSFADE}:offset={off:.2f},setpts=PTS-STARTPTS[v{j}]")
        acc += durs[j] - CROSSFADE
    fg = ";".join(fp)
    last = f"v{len(synced)-1}"
    cmd = f'ffmpeg -y {inputs} -filter_complex "{fg}" -map "[{last}]" -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -an "{concat_v}"'
    proc = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if proc.returncode != 0:
        lf = os.path.join(final_dir, "fish_list.txt")
        with open(lf,"w") as f:
            for p in synced: f.write(f"file '{p.replace(chr(92),'/')}'\n")
        subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",lf,"-c","copy",concat_v], capture_output=True, text=True)

    # Audio concat
    al = os.path.join(audio_dir, "fish_alist.txt")
    with open(al,"w") as f:
        for af in audio_files: f.write(f"file '{af['path'].replace(chr(92),'/')}'\n")
    concat_a = os.path.join(audio_dir, "fish_narration.mp3")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",al,"-c","copy",concat_a], capture_output=True, text=True)

    # Mix
    mixed = os.path.join(final_dir, "fish_mixed.mp3")
    subprocess.run([
        "ffmpeg","-y","-i",concat_a,"-i",music,
        "-filter_complex","[1:a]volume=0.10[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[out]",
        "-map","[out]","-c:a","libmp3lame","-b:a","192k",mixed
    ], capture_output=True, text=True)

    # ── 5. FINAL ──
    print("\n[5/5] FINAL")
    final = os.path.join(final_dir, "FISH_julio_cesar_youtube.mp4")
    sub_esc = subs.replace("\\","/").replace(":","\\:")
    proc = subprocess.run([
        "ffmpeg","-y","-i",concat_v,"-i",mixed,
        "-vf",f"ass='{sub_esc}'",
        "-c:v","libx264","-preset","slow","-crf","18",
        "-c:a","aac","-b:a","192k",
        "-shortest","-pix_fmt","yuv420p","-movflags","+faststart",final
    ], capture_output=True, text=True)

    if proc.returncode != 0:
        print(f"  Error subs: {proc.stderr[:200]}")
        subprocess.run([
            "ffmpeg","-y","-i",concat_v,"-i",mixed,
            "-c:v","libx264","-preset","slow","-crf","18",
            "-c:a","aac","-b:a","192k",
            "-shortest","-pix_fmt","yuv420p","-movflags","+faststart",final
        ], capture_output=True, text=True)

    fd = get_dur(final)
    fs = os.path.getsize(final)/(1024*1024)
    print(f"  Duracion: {fd:.1f}s | Peso: {fs:.1f}MB")

    # Cleanup
    for f in [concat_v, concat_a, mixed, al]:
        try: os.remove(f)
        except: pass
    for p in synced:
        try: os.remove(p)
        except: pass

    print(f"\nLISTO: {final}")
    subprocess.Popen(["cmd", "/c", "start", "", final])


if __name__ == "__main__":
    asyncio.run(main())
