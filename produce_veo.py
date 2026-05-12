import asyncio, os, sys, subprocess, time, urllib.request, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
_BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE)
import fal_client

with open(os.path.join(_BASE, "config", "settings.json"), "r", encoding="utf-8") as _f:
    os.environ['FAL_KEY'] = json.load(_f).get("fal_api_key", "")
OUT = 'output'

# Skeleton character description for consistency
SKEL = "a skeleton character with visible skull face, bone hands, and expressive eye sockets"

SCENES = [
    {"num": 1,
     "narr": "Y si Einstein viajara a la antigua Grecia? Imagina al genio mas grande de la historia apareciendo en medio de Atenas.",
     "vprompt": f"{SKEL} wearing a grey suit and wild white hair like Einstein, standing in the middle of an ancient Greek agora marketplace, Greek citizens in togas staring in shock, marble buildings and columns, bright sunny day, cinematic slow motion, photorealistic, 9:16 vertical"},
    {"num": 2,
     "narr": "Los griegos lo ven llegar con su traje y su pelo loco. Piensan que es un dios. O un loco. Probablemente ambos.",
     "vprompt": f"{SKEL} wearing Einstein's grey suit with messy white hair, surrounded by curious ancient Greek citizens in white togas pointing and whispering, Greek temple with tall marble columns in background, warm golden sunlight, cinematic camera push forward, photorealistic, 9:16 vertical"},
    {"num": 3,
     "narr": "Einstein se sienta con los filosofos. Socrates le pregunta que es la verdad. Einstein le responde con una ecuacion. Socrates no entiende nada.",
     "vprompt": f"{SKEL} wearing a grey suit sitting at a stone table drawing equations, surrounded by ancient Greek philosophers in togas with beards looking confused at the formulas, indoor Greek academy with scrolls and candles, warm lighting, cinematic, photorealistic, 9:16 vertical"},
    {"num": 4,
     "narr": "Quieren ganar guerras. Einstein dibuja lineas y explica la fisica de las catapultas. Los generales espartanos lo miran como si fuera un mago.",
     "vprompt": f"{SKEL} wearing a grey suit pointing at battle plans on a stone table, muscular Spartan soldiers with red capes golden helmets and spears watching intensely, ancient war room with torches, dramatic warm lighting, cinematic slow camera movement, photorealistic, 9:16 vertical"},
    {"num": 5,
     "narr": "Le ofrecen quedarse como consejero del rey. Pero Einstein sonrie y dice que el pertenece al futuro. Y desaparece.",
     "vprompt": f"{SKEL} wearing a grey suit standing alone in front of the Parthenon temple at sunset, golden hour lighting, the skeleton waves goodbye with a bone hand, ancient Athens panoramic view, epic cinematic wide shot, emotional atmosphere, photorealistic, 9:16 vertical"},
    {"num": 6,
     "narr": "Einstein no necesitaba una maquina del tiempo. Solo necesitaba una pizarra y alguien que escuchara.",
     "vprompt": f"{SKEL} wearing a grey suit standing next to a large chalkboard full of equations in an ancient Greek setting, a young Greek student sits listening in awe, soft golden light streaming through columns, peaceful cinematic atmosphere, photorealistic, 9:16 vertical"},
]


def dur(p):
    r = subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",p], capture_output=True, text=True)
    return float(r.stdout.strip())


async def main():
    from pipeline.voice import generate_voice
    from pipeline.subtitles import generate_ass
    from pipeline.music import generate_ambient_track

    for d in [f"{OUT}/clips", f"{OUT}/audio", f"{OUT}/final"]:
        os.makedirs(d, exist_ok=True)

    print("=" * 50)
    print("SKELETON + EINSTEIN EN GRECIA")
    print("Veo 3.1 Fast — 6 escenas x 8s")
    print("=" * 50)

    # Upload reference
    print("\nUploading skeleton reference...")
    ref = fal_client.upload_file("assets/skeleton_ref/Reference images/Reference 2.png")
    print(f"  OK")

    # 1. VOZ
    print("\n[1/4] VOZ")
    af = []
    for s in SCENES:
        r = await generate_voice(s["narr"], "es-MX-JorgeNeural", f"vf_{s['num']}.mp3", rate="+5%", pitch="-2Hz")
        af.append({"scene_number": s["num"], "path": r["path"], "duration": r["duration"]})
        print(f"  {s['num']}: {r['duration']:.1f}s")
    total = sum(a["duration"] for a in af)
    print(f"  Total: {total:.1f}s")

    # 2. VIDEO con Veo 3.1 Fast
    print("\n[2/4] VIDEO — Veo 3.1 Fast i2v (8s clips)")
    clips = []
    for s in SCENES:
        n = s["num"]
        cp = f"{OUT}/clips/vf_{n}.mp4"
        print(f"  {n}: Generando...")
        t0 = time.time()
        try:
            result = fal_client.subscribe("fal-ai/veo3.1/fast/image-to-video", arguments={
                "prompt": s["vprompt"],
                "image_url": ref,
                "duration": "8s",
                "aspect_ratio": "9:16",
            })
            urllib.request.urlretrieve(result["video"]["url"], cp)
            print(f"  {n}: {dur(cp):.1f}s ({time.time()-t0:.0f}s)")
        except Exception as e:
            print(f"  {n}: Veo error: {str(e)[:80]}")
            print(f"  {n}: Fallback Kling...")
            result = fal_client.subscribe("fal-ai/kling-video/v2.1/standard/image-to-video", arguments={
                "prompt": s["vprompt"],
                "image_url": ref,
                "duration": "5",
                "aspect_ratio": "9:16",
            })
            urllib.request.urlretrieve(result["video"]["url"], cp)
            print(f"  {n}: {dur(cp):.1f}s Kling ({time.time()-t0:.0f}s)")
        clips.append({"scene_number": n, "path": cp})

    # 3. SYNC + ASSEMBLE
    print("\n[3/4] SYNC")
    synced = []
    for i, s in enumerate(SCENES):
        n = s["num"]
        ad = af[i]["duration"]
        cd = dur(clips[i]["path"])
        sp = f"{OUT}/final/vf_s_{n}.mp4"
        speed = cd / ad
        subprocess.run([
            "ffmpeg","-y","-i",clips[i]["path"],
            "-vf",f"setpts={1/speed:.4f}*PTS,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
            "-t",f"{ad:.3f}","-c:v","libx264","-preset","fast","-crf","18",
            "-pix_fmt","yuv420p","-an","-r","24",sp
        ], capture_output=True, text=True)
        synced.append(sp)
        print(f"  {n}: v={dur(sp):.1f}s a={ad:.1f}s")

    subs = generate_ass(
        scenes=[{"scene_number": s["num"], "narration": s["narr"]} for s in SCENES],
        audio_results=af, video_id=222
    )
    music = await generate_ambient_track(total + 2, mood="epic", output_filename="vf_music.mp3")

    # Crossfade
    CF = 0.3
    ds = [dur(p) for p in synced]
    cv = f"{OUT}/final/vf_xf.mp4"
    inp = " ".join(f'-i "{p}"' for p in synced)
    fp = []
    acc = ds[0]
    for j in range(1, len(synced)):
        off = max(acc - CF, 0.1)
        if j == 1:
            fp.append(f"[0:v][1:v]xfade=transition=fade:duration={CF}:offset={off:.2f},setpts=PTS-STARTPTS[v1]")
        else:
            fp.append(f"[v{j-1}][{j}:v]xfade=transition=fade:duration={CF}:offset={off:.2f},setpts=PTS-STARTPTS[v{j}]")
        acc += ds[j] - CF
    fg = ";".join(fp)
    last = f"v{len(synced)-1}"
    cmd = f'ffmpeg -y {inp} -filter_complex "{fg}" -map "[{last}]" -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -an "{cv}"'
    r = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if r.returncode != 0:
        lf = f"{OUT}/final/vf_l.txt"
        with open(lf, "w") as f:
            for p in synced:
                f.write(f"file '{p.replace(chr(92),'/')}'\n")
        subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",lf,"-c","copy",cv], capture_output=True, text=True)

    al = f"{OUT}/audio/vf_al.txt"
    with open(al, "w") as f:
        for a in af:
            f.write(f"file '{a['path'].replace(chr(92),'/')}'\n")
    ca = f"{OUT}/audio/vf_narr.mp3"
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",al,"-c","copy",ca], capture_output=True, text=True)

    mx = f"{OUT}/final/vf_mx.mp3"
    subprocess.run([
        "ffmpeg","-y","-i",ca,"-i",music,
        "-filter_complex","[1:a]volume=0.10[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[out]",
        "-map","[out]","-c:a","libmp3lame","-b:a","192k",mx
    ], capture_output=True, text=True)

    # 4. FINAL
    print("\n[4/4] RENDER")
    final = f"{OUT}/final/EINSTEIN_GRECIA_FINAL.mp4"
    se = subs.replace("\\", "/").replace(":", "\\:")
    r = subprocess.run([
        "ffmpeg","-y","-i",cv,"-i",mx,
        "-vf",f"ass='{se}'",
        "-c:v","libx264","-preset","slow","-crf","18",
        "-c:a","aac","-b:a","192k",
        "-shortest","-pix_fmt","yuv420p","-movflags","+faststart",final
    ], capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run([
            "ffmpeg","-y","-i",cv,"-i",mx,
            "-c:v","libx264","-preset","slow","-crf","18",
            "-c:a","aac","-b:a","192k",
            "-shortest","-pix_fmt","yuv420p","-movflags","+faststart",final
        ], capture_output=True, text=True)

    fd = dur(final)
    fs = os.path.getsize(final) / (1024*1024)
    print(f"\n  Duracion: {fd:.1f}s | Peso: {fs:.1f}MB")

    for f in [cv, ca, mx, al]:
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
