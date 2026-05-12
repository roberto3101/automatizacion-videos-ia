"""
Video viral con imagenes AI REALES — estilo Socrates/McDonalds.
FLUX 2 Schnell en fal.ai + Edge-TTS + transiciones perfectas.
"""
import asyncio
import os
import sys
import subprocess
import json
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

with open(os.path.join(BASE_DIR, "config", "settings.json"), "r", encoding="utf-8") as _f:
    os.environ['FAL_KEY'] = json.load(_f).get("fal_api_key", "")

SCRIPT = {
    "title": "Y si Julio Cesar tuviera un canal de YouTube",
    "voice": "es-MX-JorgeNeural",
    "rate": "+3%",
    "pitch": "-2Hz",
    "skeleton_base": "A translucent 3D rendered anatomical skeleton with big expressive brown eyes, visible glowing orange brain through transparent skull, smooth bone texture, translucent glass-like skin showing ribcage and bones",
    "scenes": [
        {
            "scene_number": 1,
            "narration": "Imagina que Julio Cesar, el emperador mas famoso de Roma, tuviera un canal de YouTube.",
            "visual_prompt": "{skeleton}, wearing a red Roman toga and golden laurel crown, sitting at a modern desk with a YouTube play button and microphone, ancient Roman palace with marble columns in background, warm golden cinematic lighting, 4K, photorealistic, shallow depth of field, vertical 9:16 portrait",
        },
        {
            "scene_number": 2,
            "narration": "Su primer video seria: Como conquistar las Galias en diez pasos. Y tendria tres millones de vistas en un dia.",
            "visual_prompt": "{skeleton}, wearing Roman armor and red cape, standing proudly in front of a huge glowing screen showing 3 million views, Roman soldiers in the background looking amazed, war camp with torches and smoke, dramatic cinematic lighting, 4K, photorealistic, vertical 9:16 portrait",
        },
        {
            "scene_number": 3,
            "narration": "Pero lo mejor seria su seccion de comentarios. Cleopatra le dejaria un corazon, y Bruto comentaria: Gran video hermano. Pero tengo unas sugerencias.",
            "visual_prompt": "{skeleton}, wearing golden laurel crown, looking at a giant glowing phone screen with a suspicious expression, beautiful Egyptian queen Cleopatra visible on the screen, dark Roman palace with candles, warm golden and blue phone glow lighting, 4K, photorealistic, vertical 9:16 portrait",
        },
        {
            "scene_number": 4,
            "narration": "Su video mas viral seria un Que hay en mi toga, donde mostraria su espada favorita, su corona de laurel, y un mapa de todos los territorios que quiere conquistar.",
            "visual_prompt": "{skeleton}, wearing a Roman toga, excitedly showing a golden sword and a large ancient map spread on a marble table, unboxing style scene, dramatic torchlight, ancient Roman aesthetic, 4K, photorealistic, vertical 9:16 portrait",
        },
        {
            "scene_number": 5,
            "narration": "Pero un dia subiria un video titulado: Por que no confio en mis amigos del Senado. Y Bruto le dejaria un dislike. Solo uno. Pero el mas importante de la historia.",
            "visual_prompt": "{skeleton}, wearing torn Roman toga, looking scared and worried at a phone showing a red dislike button, dark shadowy Roman Senate building in background with menacing hooded figures, dramatic red and dark tense lighting, 4K, photorealistic, vertical 9:16 portrait",
        },
        {
            "scene_number": 6,
            "narration": "Julio Cesar no necesitaba un imperio. Necesitaba un buen editor de video y WiFi.",
            "visual_prompt": "{skeleton}, sitting on a golden Roman throne wearing modern headphones and a golden laurel crown, editing on a glowing laptop, epic Roman empire map on the wall behind, dramatic golden backlighting, mix of ancient and modern, 4K, photorealistic, vertical 9:16 portrait",
        },
    ],
}

CROSSFADE = 0.4


def get_dur(path):
    r = subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",path], capture_output=True, text=True)
    return float(r.stdout.strip())


async def generate_images():
    """Generate all scene images with FLUX on fal.ai"""
    import fal_client

    imgs_dir = os.path.join(OUTPUT_DIR, "images")
    os.makedirs(imgs_dir, exist_ok=True)

    images = []
    for scene in SCRIPT["scenes"]:
        n = scene["scene_number"]
        path = os.path.join(imgs_dir, f"viral_real_scene_{n}.png")

        print(f"  Escena {n}: Generating...")
        t0 = time.time()

        # Inject skeleton description into prompt
        prompt = scene["visual_prompt"].replace("{skeleton}", SCRIPT["skeleton_base"])

        result = fal_client.subscribe('fal-ai/flux/schnell', arguments={
            'prompt': prompt,
            'image_size': {'width': 768, 'height': 1344},
            'num_images': 1,
        })

        img_url = result['images'][0]['url']
        urllib.request.urlretrieve(img_url, path)
        elapsed = time.time() - t0
        size = os.path.getsize(path) // 1024
        print(f"  Escena {n}: {size}KB ({elapsed:.1f}s)")
        images.append({"scene_number": n, "path": path})

    return images


async def main():
    print("=" * 50)
    print("VIDEO FACTORY — PRIMER VIDEO REAL")
    print(f"'{SCRIPT['title']}'")
    print("FLUX AI images + Edge-TTS + Perfect sync")
    print("=" * 50)

    from pipeline.voice import generate_voice
    from pipeline.subtitles import generate_ass
    from pipeline.music import generate_ambient_track

    clips_dir = os.path.join(OUTPUT_DIR, "clips")
    audio_dir = os.path.join(OUTPUT_DIR, "audio")
    final_dir = os.path.join(OUTPUT_DIR, "final")
    for d in [clips_dir, audio_dir, final_dir]:
        os.makedirs(d, exist_ok=True)

    # ── 1. VOICE ──
    print("\n[1/6] VOZ")
    audio_files = []
    for scene in SCRIPT["scenes"]:
        n = scene["scene_number"]
        result = await generate_voice(
            text=scene["narration"],
            voice_id=SCRIPT["voice"],
            output_filename=f"real_scene_{n}.mp3",
            rate=SCRIPT["rate"],
            pitch=SCRIPT["pitch"],
        )
        audio_files.append({"scene_number": n, "path": result["path"], "duration": result["duration"]})
        print(f"  Escena {n}: {result['duration']:.2f}s")
    total_audio = sum(af["duration"] for af in audio_files)

    # ── 2. AI IMAGES ──
    print("\n[2/6] IMAGENES AI — FLUX 2 Schnell")
    images = await generate_images()

    # ── 3. IMAGE → VIDEO (Ken Burns) ──
    print("\n[3/6] IMAGE → VIDEO (Ken Burns zoom)")
    clips = []
    for i, scene in enumerate(SCRIPT["scenes"]):
        n = scene["scene_number"]
        audio_dur = audio_files[i]["duration"]
        clip_dur = audio_dur + 1.0  # buffer
        img_path = images[i]["path"]
        clip_path = os.path.join(clips_dir, f"real_scene_{n}.mp4")

        frames = int(clip_dur * 24)
        # Zoom in slowly from 1.0 to ~1.15
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", img_path,
            "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='1+0.001*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=24,format=yuv420p",
            "-t", str(clip_dur),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p", clip_path
        ], capture_output=True, text=True)
        clips.append({"scene_number": n, "path": clip_path})
        print(f"  Escena {n}: {clip_dur:.1f}s")

    # ── 4. SYNC clips to audio ──
    print("\n[4/6] SYNC")
    synced = []
    for i in range(len(SCRIPT["scenes"])):
        n = SCRIPT["scenes"][i]["scene_number"]
        audio_dur = audio_files[i]["duration"]
        sp = os.path.join(final_dir, f"real_synced_{n}.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-i", clips[i]["path"],
            "-t", f"{audio_dur:.3f}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-an", "-r", "24", sp
        ], capture_output=True, text=True)
        synced.append(sp)
        actual = get_dur(sp)
        print(f"  Escena {n}: {actual:.3f}s == {audio_dur:.3f}s [{'OK' if abs(actual-audio_dur)<0.1 else 'DRIFT'}]")

    # ── 5. ASSEMBLE ──
    print("\n[5/6] ENSAMBLE")
    subs = generate_ass(scenes=SCRIPT["scenes"], audio_results=audio_files, video_id=1111)
    music = await generate_ambient_track(total_audio + 2, mood="epic", output_filename="real_music.mp3")

    # Crossfade
    durs = [get_dur(p) for p in synced]
    concat_v = os.path.join(final_dir, "real_xfade.mp4")
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
    subprocess.run(cmd, capture_output=True, text=True, shell=True)

    # Audio concat
    al = os.path.join(audio_dir, "real_alist.txt")
    with open(al, "w") as f:
        for af in audio_files: f.write(f"file '{af['path'].replace(chr(92),'/')}'\n")
    concat_a = os.path.join(audio_dir, "real_narration.mp3")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",al,"-c","copy",concat_a], capture_output=True, text=True)

    # Mix narration + music
    mixed = os.path.join(final_dir, "real_mixed.mp3")
    subprocess.run([
        "ffmpeg","-y","-i",concat_a,"-i",music,
        "-filter_complex","[1:a]volume=0.10[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[out]",
        "-map","[out]","-c:a","libmp3lame","-b:a","192k",mixed
    ], capture_output=True, text=True)

    # ── 6. FINAL ──
    print("\n[6/6] FINAL")
    final = os.path.join(final_dir, "VIRAL_julio_cesar_REAL.mp4")
    sub_esc = subs.replace("\\","/").replace(":","\\:")

    proc = subprocess.run([
        "ffmpeg","-y","-i",concat_v,"-i",mixed,
        "-vf",f"ass='{sub_esc}'",
        "-c:v","libx264","-preset","slow","-crf","18",
        "-c:a","aac","-b:a","192k",
        "-shortest","-pix_fmt","yuv420p","-movflags","+faststart",final
    ], capture_output=True, text=True)

    if proc.returncode != 0:
        print(f"  Error subs, retrying without...")
        subprocess.run([
            "ffmpeg","-y","-i",concat_v,"-i",mixed,
            "-c:v","libx264","-preset","slow","-crf","18",
            "-c:a","aac","-b:a","192k",
            "-shortest","-pix_fmt","yuv420p","-movflags","+faststart",final
        ], capture_output=True, text=True)

    fd = get_dur(final)
    fs = os.path.getsize(final)/(1024*1024)
    print(f"  Duracion: {fd:.1f}s | Peso: {fs:.1f}MB")
    print(f"  Costo imagenes: ~$0.09 (6 x $0.015)")

    # Cleanup temp
    for f in [concat_v, concat_a, mixed, al]:
        try: os.remove(f)
        except: pass
    for p in synced:
        try: os.remove(p)
        except: pass

    print(f"\n{'='*50}")
    print(f"LISTO: {final}")
    print(f"{'='*50}")
    subprocess.Popen(["cmd", "/c", "start", "", final])


if __name__ == "__main__":
    asyncio.run(main())
