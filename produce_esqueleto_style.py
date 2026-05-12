"""
Video estilo "Y si..." — Comedia/Viral como el del esqueleto.
Edge-TTS es-MX-JorgeNeural, ritmo rapido, sin pausas, transiciones perfectas.
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
    "title": "Y si Cleopatra abria un salon de belleza en 2024",
    "voice": "es-MX-JorgeNeural",
    "rate": "+5%",
    "pitch": "+0Hz",
    "mood": "epic",
    "scenes": [
        {
            "scene_number": 1,
            "narration": "Y si Cleopatra, la reina mas poderosa de Egipto, abriera un salon de belleza en pleno 2024?",
            "visual_prompt": "Cleopatra in modern beauty salon, gold and black decor, neon lights, Egyptian motifs mixed with modern aesthetics, cinematic, 4K",
            "duration_seconds": 8,
        },
        {
            "scene_number": 2,
            "narration": "Primero, su tratamiento estrella seria banarse en leche de burra con miel. Pero claro, ahora lo venderia como un tratamiento premium de mil dolares.",
            "visual_prompt": "Luxury spa bathtub filled with milk, gold fixtures, Egyptian queen branding, price tag showing 1000 dollars, modern luxury aesthetic, cinematic, 4K",
            "duration_seconds": 10,
        },
        {
            "scene_number": 3,
            "narration": "Su delineado de ojos? Olvidate de tutoriales de YouTube. Ella inventaria su propia linea de maquillaje. Se llamaria Nilo Beauty y se agotaria en tres minutos.",
            "visual_prompt": "Makeup product line called Nilo Beauty with Egyptian eye designs, gold packaging, sold out signs, social media buzz graphics, cinematic, 4K",
            "duration_seconds": 10,
        },
        {
            "scene_number": 4,
            "narration": "Pero lo mejor seria su cuenta de TikTok. Imaginate a Cleopatra haciendo un Get Ready With Me mientras conquista Roma. Diez millones de seguidores en una semana.",
            "visual_prompt": "Phone screen showing TikTok profile of Cleopatra with millions of followers, GRWM video playing, Egyptian queen doing makeup, viral metrics, cinematic, 4K",
            "duration_seconds": 11,
        },
        {
            "scene_number": 5,
            "narration": "Y cuando Julio Cesar le dejara un comentario diciendo me gusta tu look, ella le responderia: Gracias, pero mi imperio no se maneja solo. Y lo bloquearia.",
            "visual_prompt": "Social media comment section, Julius Caesar profile commenting, Cleopatra blocking him, comedy scene with Egyptian and Roman aesthetics, cinematic, 4K",
            "duration_seconds": 11,
        },
        {
            "scene_number": 6,
            "narration": "Cleopatra no necesitaba un trono. Necesitaba WiFi y una ring light.",
            "visual_prompt": "Cleopatra sitting on golden throne but with ring light and laptop, modern Egyptian queen boss aesthetic, epic ending shot, cinematic, 4K",
            "duration_seconds": 5,
        },
    ],
}

CROSSFADE = 0.4


def get_dur(path):
    r = subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",path], capture_output=True, text=True)
    return float(r.stdout.strip())


async def main():
    print("=" * 50)
    print("VIDEO FACTORY — Estilo Esqueleto/Viral")
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

    # Palettes: bright, fun, not horror
    palettes = [
        (45, 30, 15),   # Gold/Egyptian
        (40, 35, 20),   # Warm luxury
        (50, 25, 30),   # Pink/beauty
        (20, 30, 50),   # Blue/tech
        (35, 20, 40),   # Purple/social
        (50, 40, 15),   # Gold epic
    ]

    # ── 1. VOICE ──
    print("\n[1/5] VOZ — Edge-TTS JorgeNeural +5%")
    audio_files = []
    for scene in SCRIPT["scenes"]:
        n = scene["scene_number"]
        result = await generate_voice(
            text=scene["narration"],
            voice_id=SCRIPT["voice"],
            output_filename=f"viral_scene_{n}.mp3",
            rate=SCRIPT["rate"],
            pitch=SCRIPT["pitch"],
        )
        audio_files.append({"scene_number": n, "path": result["path"], "duration": result["duration"]})
        print(f"  Escena {n}: {result['duration']:.2f}s")

    total_audio = sum(af["duration"] for af in audio_files)
    print(f"  TOTAL: {total_audio:.1f}s")

    # ── 2. VISUALS matched to audio ──
    print("\n[2/5] VISUALES — Matched to audio")
    clips = []
    for i, scene in enumerate(SCRIPT["scenes"]):
        n = scene["scene_number"]
        audio_dur = audio_files[i]["duration"]
        clip_dur = audio_dur + 1.0  # buffer for crossfade
        clip_path = os.path.join(clips_dir, f"viral_scene_{n}.mp4")
        img_path = os.path.join(clips_dir, f"viral_scene_{n}.png")

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
        print(f"  Escena {n}: {clip_dur:.1f}s")

    # ── 3. SYNC clips to audio ──
    print("\n[3/5] SYNC")
    synced = []
    for i in range(len(SCRIPT["scenes"])):
        n = SCRIPT["scenes"][i]["scene_number"]
        audio_dur = audio_files[i]["duration"]
        sp = os.path.join(final_dir, f"viral_synced_{n}.mp4")
        subprocess.run([
            "ffmpeg","-y","-i",clips[i]["path"],
            "-t",f"{audio_dur:.3f}",
            "-c:v","libx264","-preset","fast","-crf","18",
            "-pix_fmt","yuv420p","-an","-r","24",sp
        ], capture_output=True, text=True)
        actual = get_dur(sp)
        synced.append(sp)
        print(f"  Escena {n}: {actual:.3f}s == {audio_dur:.3f}s [{'OK' if abs(actual-audio_dur)<0.1 else 'DRIFT'}]")

    # ── 4. CROSSFADE + AUDIO + SUBS ──
    print("\n[4/5] ENSAMBLE")

    subs = generate_ass(scenes=SCRIPT["scenes"], audio_results=audio_files, video_id=4444)

    music = await generate_ambient_track(total_audio + 2, mood="epic", output_filename="viral_music.mp3")

    # Crossfade
    durs = [get_dur(p) for p in synced]
    concat_v = os.path.join(final_dir, "viral_xfade.mp4")

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
        # Fallback
        lf = os.path.join(final_dir, "viral_list.txt")
        with open(lf,"w") as f:
            for p in synced: f.write(f"file '{p.replace(chr(92),'/')}'\n")
        subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",lf,"-c","copy",concat_v], capture_output=True, text=True)

    # Concat audio
    al = os.path.join(audio_dir, "viral_alist.txt")
    with open(al,"w") as f:
        for af in audio_files: f.write(f"file '{af['path'].replace(chr(92),'/')}'\n")
    concat_a = os.path.join(audio_dir, "viral_narration.mp3")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",al,"-c","copy",concat_a], capture_output=True, text=True)

    # Mix
    mixed = os.path.join(final_dir, "viral_mixed.mp3")
    subprocess.run([
        "ffmpeg","-y","-i",concat_a,"-i",music,
        "-filter_complex","[1:a]volume=0.10[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[out]",
        "-map","[out]","-c:a","libmp3lame","-b:a","192k",mixed
    ], capture_output=True, text=True)

    # ── 5. FINAL ──
    print("\n[5/5] FINAL")
    final = os.path.join(final_dir, "VIRAL_cleopatra_salon.mp4")
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
