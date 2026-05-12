"""
VIDEO FINAL — Esqueleto viral + Image-to-Video real + Edge-TTS
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

SKELETON = "cute 3D rendered cartoon skeleton character with big round expressive brown eyes, smooth white bone texture, visible ribcage and spine, translucent skin, Pixar style, friendly expression"

SCRIPT = {
    "title": "Y si Julio Cesar tuviera YouTube",
    "voice": "es-MX-JorgeNeural",
    "rate": "+3%",
    "pitch": "-2Hz",
    "scenes": [
        {
            "scene_number": 1,
            "narration": "Imagina que Julio Cesar, el emperador mas famoso de Roma, tuviera un canal de YouTube.",
            "image_prompt": f"{SKELETON}, wearing a red Roman toga and golden laurel crown, sitting at a modern desk with laptop and microphone, purple and blue neon lighting, modern studio background",
            "video_prompt": "The skeleton gestures excitedly while sitting at the desk, subtle head movement, cinematic",
        },
        {
            "scene_number": 2,
            "narration": "Su primer video seria: Como conquistar las Galias en diez pasos. Tres millones de vistas en un dia.",
            "image_prompt": f"{SKELETON}, wearing Roman armor and red cape, standing proudly pointing at a large glowing screen showing millions of views, epic golden lighting, Roman camp background with torches",
            "video_prompt": "The skeleton points at the screen proudly, slight body movement, cinematic lighting",
        },
        {
            "scene_number": 3,
            "narration": "Cleopatra le dejaria un corazon en los comentarios. Y Bruto comentaria: Gran video hermano. Tengo unas sugerencias.",
            "image_prompt": f"{SKELETON}, wearing golden laurel crown, looking at a giant glowing phone with suspicious expression, dark Roman palace with warm candle lighting, gold decorations",
            "video_prompt": "The skeleton looks at the phone suspiciously, eyes narrowing, subtle movement",
        },
        {
            "scene_number": 4,
            "narration": "Su video mas viral seria un Que hay en mi toga. Mostraria su espada, su corona, y un mapa de conquistas.",
            "image_prompt": f"{SKELETON}, wearing white Roman toga, excitedly holding up a golden sword in one hand and a scroll map in the other, marble table with Roman artifacts, warm dramatic lighting",
            "video_prompt": "The skeleton holds up the sword excitedly, slight rotation, cinematic",
        },
        {
            "scene_number": 5,
            "narration": "Pero un dia subiria: Por que no confio en el Senado. Y Bruto le dejaria un dislike. Solo uno. El mas importante de la historia.",
            "image_prompt": f"{SKELETON}, wearing torn Roman toga, looking scared at a phone showing a red dislike button, dark menacing shadows behind, red and dark dramatic lighting, tense atmosphere",
            "video_prompt": "The skeleton looks worried, trembling slightly, dark atmosphere, cinematic",
        },
        {
            "scene_number": 6,
            "narration": "Julio Cesar no necesitaba un imperio. Necesitaba WiFi y un buen editor de video.",
            "image_prompt": f"{SKELETON}, sitting on a golden throne wearing modern headphones and laurel crown, laptop on lap, epic Roman map on wall, golden backlighting, mix of ancient and modern",
            "video_prompt": "The skeleton types on laptop on the throne, epic subtle movement, cinematic",
        },
    ],
}

CROSSFADE = 0.4

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
    print("PRODUCCION FINAL — Esqueleto Viral")
    print("=" * 50)

    # ── 1. VOZ ──
    print("\n[1/5] VOZ")
    audio_files = []
    for scene in SCRIPT["scenes"]:
        n = scene["scene_number"]
        result = await generate_voice(
            text=scene["narration"], voice_id=SCRIPT["voice"],
            output_filename=f"final_scene_{n}.mp3",
            rate=SCRIPT["rate"], pitch=SCRIPT["pitch"],
        )
        audio_files.append({"scene_number": n, "path": result["path"], "duration": result["duration"]})
        print(f"  Escena {n}: {result['duration']:.1f}s")

    # ── 2. IMAGENES AI ──
    print("\n[2/5] IMAGENES — FLUX Schnell")
    images = []
    for scene in SCRIPT["scenes"]:
        n = scene["scene_number"]
        path = os.path.join(imgs_dir, f"final_scene_{n}.png")
        t0 = time.time()
        result = fal_client.subscribe('fal-ai/flux/schnell', arguments={
            'prompt': scene["image_prompt"],
            'image_size': {'width': 768, 'height': 1344},
            'num_images': 1,
        })
        urllib.request.urlretrieve(result['images'][0]['url'], path)
        print(f"  Escena {n}: {time.time()-t0:.1f}s")
        images.append({"scene_number": n, "path": path, "url": result['images'][0]['url']})

    # ── 3. IMAGE → VIDEO (Kling) ──
    print("\n[3/5] IMAGE → VIDEO — Kling 2.1")
    clips = []
    for i, scene in enumerate(SCRIPT["scenes"]):
        n = scene["scene_number"]
        clip_path = os.path.join(clips_dir, f"final_scene_{n}.mp4")
        t0 = time.time()
        print(f"  Escena {n}: Generating video...")

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
        print(f"  Escena {n}: {dur:.1f}s video ({elapsed:.0f}s gen)")
        clips.append({"scene_number": n, "path": clip_path, "duration": dur})

    # ── 4. SYNC + ASSEMBLE ──
    print("\n[4/5] SYNC + ENSAMBLE")

    # Each clip is ~5s but audio varies. Trim or speed-adjust clips to match audio.
    synced = []
    for i in range(len(SCRIPT["scenes"])):
        n = SCRIPT["scenes"][i]["scene_number"]
        audio_dur = audio_files[i]["duration"]
        clip_dur = clips[i]["duration"]
        sp = os.path.join(final_dir, f"final_synced_{n}.mp4")

        if abs(clip_dur - audio_dur) < 0.3:
            # Close enough — just trim
            subprocess.run([
                "ffmpeg","-y","-i",clips[i]["path"],
                "-t",f"{audio_dur:.3f}","-c:v","libx264","-preset","fast","-crf","18",
                "-pix_fmt","yuv420p","-an","-r","24",
                "-vf","scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
                sp
            ], capture_output=True, text=True)
        else:
            # Speed adjust clip to match audio duration
            speed = clip_dur / audio_dur
            subprocess.run([
                "ffmpeg","-y","-i",clips[i]["path"],
                "-vf",f"setpts={1/speed:.4f}*PTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
                "-t",f"{audio_dur:.3f}","-c:v","libx264","-preset","fast","-crf","18",
                "-pix_fmt","yuv420p","-an","-r","24",sp
            ], capture_output=True, text=True)

        actual = get_dur(sp)
        synced.append(sp)
        print(f"  Escena {n}: video={actual:.2f}s audio={audio_dur:.2f}s [{'OK' if abs(actual-audio_dur)<0.3 else 'ADJUST'}]")

    # Subtitles
    subs = generate_ass(scenes=SCRIPT["scenes"], audio_results=audio_files, video_id=999)

    # Music
    total_audio = sum(af["duration"] for af in audio_files)
    music = await generate_ambient_track(total_audio + 2, mood="epic", output_filename="final_music.mp3")

    # Crossfade video
    durs = [get_dur(p) for p in synced]
    concat_v = os.path.join(final_dir, "final_xfade.mp4")
    inputs = " ".join(f'-i "{p}"' for p in synced)
    fp = []
    acc = durs[0]
    for j in range(1, len(synced)):
        off = max(acc - CROSSFADE, 0.1)
        prev = f"v{j-1}" if j > 1 else "0:v"
        curr = f"v{j}"
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
        # Fallback concat
        lf = os.path.join(final_dir, "final_list.txt")
        with open(lf,"w") as f:
            for p in synced: f.write(f"file '{p.replace(chr(92),'/')}'\n")
        subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",lf,"-c","copy",concat_v], capture_output=True, text=True)

    # Audio
    al = os.path.join(audio_dir, "final_alist.txt")
    with open(al,"w") as f:
        for af in audio_files: f.write(f"file '{af['path'].replace(chr(92),'/')}'\n")
    concat_a = os.path.join(audio_dir, "final_narration.mp3")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",al,"-c","copy",concat_a], capture_output=True, text=True)

    mixed = os.path.join(final_dir, "final_mixed.mp3")
    subprocess.run([
        "ffmpeg","-y","-i",concat_a,"-i",music,
        "-filter_complex","[1:a]volume=0.10[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[out]",
        "-map","[out]","-c:a","libmp3lame","-b:a","192k",mixed
    ], capture_output=True, text=True)

    # ── 5. FINAL ──
    print("\n[5/5] RENDER FINAL")
    final = os.path.join(final_dir, "VIRAL_SKELETON_julio_cesar.mp4")
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

    # Cleanup
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
