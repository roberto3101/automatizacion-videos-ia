"""
SKELETON VIRAL — Prompts reales copiados de tutoriales virales.
FLUX para imagenes + Veo 3.1 Fast para video + Edge-TTS.
Consistencia: misma descripcion de esqueleto en TODOS los prompts.
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

# Descripcion EXACTA del esqueleto viral — se inyecta en cada prompt
# Basado en los tutoriales de iamaniakos.com y aicenturies.com
SKELETON_DESC = (
    "A 3D rendered anatomical human skeleton with translucent crystal-like glass skin, "
    "big round expressive cartoon-style brown eyes with white sclera, "
    "realistic white bone texture with visible teeth, ribcage, and spine, "
    "soft studio lighting with gentle shadows"
)

# Anatomia precisa (del tutorial de iamaniakos)
ANATOMY_TAG = "medically accurate anatomical placement, correct left-right orientation from skeleton perspective, organs anchored to ribs and spine"

SCRIPT = {
    "title": "Que le pasa a tu cuerpo si solo comes hamburguesas por un ano",
    "voice": "es-MX-JorgeNeural",
    "rate": "+5%",
    "pitch": "-2Hz",
    "scenes": [
        {
            "scene_number": 1,
            "narration": "Que le pasa a tu cuerpo si solo comes hamburguesas durante un ano entero?",
            "image_prompt": f"{SKELETON_DESC}, sitting at a fast food restaurant table looking at a giant hamburger with both skeletal hands, french fries on a red tray, simple red and yellow restaurant background, front view, vertical 9:16 portrait, {ANATOMY_TAG}",
            "video_prompt": "Slow cinematic push forward, the skeleton slowly reaches for the hamburger, subtle jaw movement, soft lighting",
        },
        {
            "scene_number": 2,
            "narration": "La primera semana tu estomago se expande. Tu cerebro libera dopamina y te vuelves adicto a la grasa y el azucar.",
            "image_prompt": f"{SKELETON_DESC}, front view close-up showing the stomach area glowing orange inside the ribcage, the brain visible through the transparent skull glowing bright yellow with dopamine signals, simple dark blue background, vertical 9:16 portrait, {ANATOMY_TAG}",
            "video_prompt": "Slow cinematic push forward toward the skeleton chest, stomach glows and pulses subtly, brain flickers with light, minimal movement",
        },
        {
            "scene_number": 3,
            "narration": "Al mes, tu higado comienza a acumular grasa. Tu corazon late mas rapido porque tus arterias se estan tapando.",
            "image_prompt": f"{SKELETON_DESC}, front view showing the liver area glowing red in the upper right abdomen and the heart glowing bright red in the left chest cavity, arteries visible with yellow fat buildup, simple dark blue background, vertical 9:16 portrait, {ANATOMY_TAG}",
            "video_prompt": "Slow cinematic push forward, heart pulses visibly, liver glows with warning red, subtle organic movement",
        },
        {
            "scene_number": 4,
            "narration": "A los seis meses tus huesos se debilitan. No recibes suficiente calcio. Y tu piel se vuelve palida y sin vida.",
            "image_prompt": f"{SKELETON_DESC}, front view showing cracked and weakened bones with visible fracture lines glowing, pale translucent skin looking unhealthy, sad expression in the big brown eyes, simple dark blue background, vertical 9:16 portrait, {ANATOMY_TAG}",
            "video_prompt": "Slow cinematic push forward, cracks appear on bones, skeleton looks sad, subtle head tilt down, melancholic mood",
        },
        {
            "scene_number": 5,
            "narration": "Al ano, tu cuerpo es una bomba de tiempo. Riesgo de infarto, diabetes, y dano permanente en el higado. Todo por una hamburguesa.",
            "image_prompt": f"{SKELETON_DESC}, front view showing multiple organs glowing red as warning, heart, liver, and kidneys all highlighted in dangerous red, the skeleton has a worried scared expression in its big brown eyes, dramatic red warning lighting on a dark background, vertical 9:16 portrait, {ANATOMY_TAG}",
            "video_prompt": "Slow dramatic push forward, organs pulse red like alarms, skeleton trembles slightly, tense dramatic atmosphere",
        },
    ],
}

CROSSFADE = 0.3


def get_dur(path):
    r = subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",path], capture_output=True, text=True)
    return float(r.stdout.strip())


async def main():
    import fal_client
    from pipeline.voice import generate_voice
    from pipeline.subtitles import generate_ass
    from pipeline.music import generate_ambient_track

    clips_dir = os.path.join(OUTPUT_DIR, "clips")
    audio_dir = os.path.join(OUTPUT_DIR, "audio")
    imgs_dir = os.path.join(OUTPUT_DIR, "images")
    final_dir = os.path.join(OUTPUT_DIR, "final")
    for d in [clips_dir, audio_dir, imgs_dir, final_dir]:
        os.makedirs(d, exist_ok=True)

    print("=" * 50)
    print("SKELETON VIRAL — PRODUCCION FINAL")
    print(f"'{SCRIPT['title']}'")
    print("=" * 50)

    # ── 1. VOZ ──
    print("\n[1/5] VOZ — Edge-TTS")
    audio_files = []
    for scene in SCRIPT["scenes"]:
        n = scene["scene_number"]
        result = await generate_voice(
            text=scene["narration"], voice_id=SCRIPT["voice"],
            output_filename=f"skel_scene_{n}.mp3",
            rate=SCRIPT["rate"], pitch=SCRIPT["pitch"],
        )
        audio_files.append({"scene_number": n, "path": result["path"], "duration": result["duration"]})
        print(f"  Escena {n}: {result['duration']:.1f}s")
    total_audio = sum(af["duration"] for af in audio_files)
    print(f"  Total: {total_audio:.1f}s")

    # ── 2. IMAGENES ──
    print("\n[2/5] IMAGENES — FLUX Schnell ($0.015 c/u)")
    images = []
    for scene in SCRIPT["scenes"]:
        n = scene["scene_number"]
        path = os.path.join(imgs_dir, f"skel_scene_{n}.png")
        result = fal_client.subscribe('fal-ai/flux/schnell', arguments={
            'prompt': scene["image_prompt"],
            'image_size': {'width': 768, 'height': 1344},
            'num_images': 1,
        })
        url = result['images'][0]['url']
        urllib.request.urlretrieve(url, path)
        print(f"  Escena {n}: OK")
        images.append({"scene_number": n, "path": path, "url": url})

    # ── 3. IMAGE → VIDEO con Veo 3.1 Fast ──
    print("\n[3/5] IMAGE → VIDEO — Veo 3.1 Fast ($0.10/s)")
    clips = []
    for i, scene in enumerate(SCRIPT["scenes"]):
        n = scene["scene_number"]
        clip_path = os.path.join(clips_dir, f"skel_scene_{n}.mp4")
        t0 = time.time()
        print(f"  Escena {n}: Generando video...")

        try:
            result = fal_client.subscribe('fal-ai/veo3.1/fast/image-to-video', arguments={
                'prompt': scene["video_prompt"],
                'image_url': images[i]["url"],
                'duration': '5',
                'aspect_ratio': '9:16',
            })
            video_url = result['video']['url']
        except Exception as e:
            print(f"  Veo 3.1 error: {e}")
            print(f"  Fallback: Kling 2.1...")
            result = fal_client.subscribe('fal-ai/kling-video/v2.1/standard/image-to-video', arguments={
                'prompt': scene["video_prompt"],
                'image_url': images[i]["url"],
                'duration': '5',
                'aspect_ratio': '9:16',
            })
            video_url = result['video']['url']

        urllib.request.urlretrieve(video_url, clip_path)
        elapsed = time.time() - t0
        dur = get_dur(clip_path)
        print(f"  Escena {n}: {dur:.1f}s ({elapsed:.0f}s gen)")
        clips.append({"scene_number": n, "path": clip_path, "duration": dur})

    # ── 4. SYNC + ENSAMBLE ──
    print("\n[4/5] SYNC + CROSSFADE")

    synced = []
    for i in range(len(SCRIPT["scenes"])):
        n = SCRIPT["scenes"][i]["scene_number"]
        audio_dur = audio_files[i]["duration"]
        clip_dur = clips[i]["duration"]
        sp = os.path.join(final_dir, f"skel_synced_{n}.mp4")

        speed = clip_dur / audio_dur
        subprocess.run([
            "ffmpeg","-y","-i",clips[i]["path"],
            "-vf",f"setpts={1/speed:.4f}*PTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
            "-t",f"{audio_dur:.3f}","-c:v","libx264","-preset","fast","-crf","18",
            "-pix_fmt","yuv420p","-an","-r","24",sp
        ], capture_output=True, text=True)
        actual = get_dur(sp)
        synced.append(sp)
        print(f"  Escena {n}: video={actual:.2f}s audio={audio_dur:.2f}s")

    # Subtitulos
    subs = generate_ass(scenes=SCRIPT["scenes"], audio_results=audio_files, video_id=777)

    # Musica
    music = await generate_ambient_track(total_audio + 2, mood="mystery", output_filename="skel_music.mp3")

    # Crossfade
    durs = [get_dur(p) for p in synced]
    concat_v = os.path.join(final_dir, "skel_xfade.mp4")
    inputs = " ".join(f'-i "{p}"' for p in synced)
    fp = []
    acc = durs[0]
    for j in range(1, len(synced)):
        off = max(acc - CROSSFADE, 0.1)
        if j == 1:
            fp.append(f"[0:v][1:v]xfade=transition=fade:duration={CROSSFADE}:offset={off:.2f},setpts=PTS-STARTPTS[v1]")
        else:
            fp.append(f"[v{j-1}][{j}:v]xfade=transition=fade:duration={CROSSFADE}:offset={off:.2f},setpts=PTS-STARTPTS[v{j}]")
        acc += durs[j] - CROSSFADE
    fg = ";".join(fp)
    last = f"v{len(synced)-1}"
    cmd = f'ffmpeg -y {inputs} -filter_complex "{fg}" -map "[{last}]" -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -an "{concat_v}"'
    proc = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if proc.returncode != 0:
        lf = os.path.join(final_dir, "skel_list.txt")
        with open(lf,"w") as f:
            for p in synced: f.write(f"file '{p.replace(chr(92),'/')}'\n")
        subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",lf,"-c","copy",concat_v], capture_output=True, text=True)

    # Audio
    al = os.path.join(audio_dir, "skel_alist.txt")
    with open(al,"w") as f:
        for af in audio_files: f.write(f"file '{af['path'].replace(chr(92),'/')}'\n")
    concat_a = os.path.join(audio_dir, "skel_narration.mp3")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",al,"-c","copy",concat_a], capture_output=True, text=True)

    mixed = os.path.join(final_dir, "skel_mixed.mp3")
    subprocess.run([
        "ffmpeg","-y","-i",concat_a,"-i",music,
        "-filter_complex","[1:a]volume=0.08[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[out]",
        "-map","[out]","-c:a","libmp3lame","-b:a","192k",mixed
    ], capture_output=True, text=True)

    # ── 5. FINAL ──
    print("\n[5/5] RENDER FINAL")
    final = os.path.join(final_dir, "SKELETON_hamburguesas.mp4")
    sub_esc = subs.replace("\\","/").replace(":","\\:")
    proc = subprocess.run([
        "ffmpeg","-y","-i",concat_v,"-i",mixed,
        "-vf",f"ass='{sub_esc}'",
        "-c:v","libx264","-preset","slow","-crf","18",
        "-c:a","aac","-b:a","192k",
        "-shortest","-pix_fmt","yuv420p","-movflags","+faststart",final
    ], capture_output=True, text=True)
    if proc.returncode != 0:
        subprocess.run([
            "ffmpeg","-y","-i",concat_v,"-i",mixed,
            "-c:v","libx264","-preset","slow","-crf","18",
            "-c:a","aac","-b:a","192k",
            "-shortest","-pix_fmt","yuv420p","-movflags","+faststart",final
        ], capture_output=True, text=True)

    fd = get_dur(final)
    fs = os.path.getsize(final)/(1024*1024)
    print(f"\n  Duracion: {fd:.1f}s | Peso: {fs:.1f}MB")

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
