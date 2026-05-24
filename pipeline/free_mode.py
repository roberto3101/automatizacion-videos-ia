"""
Free Mode — manual asistido con Google Whisk + Grok Imagine.

Replica el workflow del tutorial de AE Creators IA pero automatiza todo lo que
NO requiere las herramientas free oficiales:

  Manual (tú haces):
    1. Google Whisk con imagen referencia → 6 imágenes
    2. Grok Imagine con cada imagen → 6 clips de 5s

  Automático (el sistema hace):
    3. Voz (Edge-TTS o ElevenLabs)
    4. Subtítulos word-level con Whisper
    5. Música + sidechain ducking
    6. Ensamble FFmpeg con transiciones
    7. Render GPU

El sistema te muestra los prompts listos, abre Whisk y Grok en tu navegador,
te abre la carpeta donde droppear los archivos, y espera detectando los
archivos automáticamente.

Tiempo aprox por video: 10-15 min (vs 60+ min full manual con CapCut).
Costo: $0 (Whisk y Grok son gratis con límites diarios; voz/subs/edit son locales).
"""
import os
import time
import webbrowser
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL_DIR = os.path.join(BASE_DIR, "output", "manual")
TOOLS = {
    "whisk": "https://labs.google/fx/tools/whisk",
    "grok": "https://grok.com/imagine",
}


def prepare_manual_workflow(scenes: list, video_id: int,
                            reference_image_path: str = None) -> str:
    """
    Crea la carpeta de trabajo, escribe el archivo PROMPTS.txt con los prompts
    organizados, y abre Whisk/Grok en el navegador.

    Devuelve la ruta a PROMPTS.txt.
    """
    work_dir = os.path.join(MANUAL_DIR, f"video_{video_id}")
    os.makedirs(work_dir, exist_ok=True)

    prompts_path = os.path.join(work_dir, "PROMPTS.txt")
    _write_prompts_file(prompts_path, scenes, reference_image_path)

    # Abrir el archivo de prompts en el editor de texto default
    try:
        os.startfile(prompts_path)
    except Exception:
        pass

    # Abrir la carpeta donde droppear archivos
    try:
        os.startfile(work_dir)
    except Exception:
        pass

    # Abrir Whisk y Grok en el navegador
    webbrowser.open(TOOLS["whisk"])
    time.sleep(1)
    webbrowser.open(TOOLS["grok"])

    print()
    print("=" * 70)
    print(" FREE MODE — Workflow manual asistido")
    print("=" * 70)
    print(f" Carpeta de trabajo: {work_dir}")
    print(f" Prompts listos en:  {prompts_path}")
    print()
    print(" Te abrí:")
    print("  - Notepad con los prompts (Whisk + Grok)")
    print("  - Carpeta donde droppear las imágenes y clips")
    print("  - Whisk en tu navegador")
    print("  - Grok Imagine en tu navegador")
    print()
    print(" Workflow:")
    print("  1. En Whisk: sube tu imagen referencia, genera las 6 imágenes")
    print(f"     usando los prompts de PROMPTS.txt. Guárdalas en {work_dir}")
    print("     como scene_1.png, scene_2.png ... scene_6.png")
    print("  2. En Grok: sube cada imagen, anímala con su Grok prompt.")
    print("     Guarda como scene_1.mp4 ... scene_6.mp4 en la misma carpeta.")
    print("  3. El sistema detecta los archivos automáticamente y continúa.")
    print("=" * 70)

    return prompts_path


def _write_prompts_file(path: str, scenes: list, ref_image_path: str = None):
    """Escribe el archivo con instrucciones y prompts listos para copiar."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write(" FREE MODE — PROMPTS PARA GOOGLE WHISK + GROK IMAGINE\n")
        f.write("=" * 70 + "\n\n")

        f.write("INSTRUCCIONES GENERALES\n")
        f.write("-" * 70 + "\n")
        f.write("1. Abre Google Whisk:   https://labs.google/fx/tools/whisk\n")
        f.write("2. Inicia sesión con tu cuenta Google (gratis ilimitado).\n")
        f.write("3. En el panel 'Subject', sube tu imagen de referencia:\n")
        if ref_image_path:
            f.write(f"   {ref_image_path}\n")
        else:
            f.write("   (la imagen del personaje principal que querés usar)\n")
        f.write("4. Selecciona aspect ratio 9:16 (vertical).\n")
        f.write("5. Para cada escena de abajo:\n")
        f.write("   a) Copia el WHISK PROMPT\n")
        f.write("   b) Pégalo en Whisk\n")
        f.write("   c) Genera (puedes regenerar varias veces, elige la mejor)\n")
        f.write("   d) Descarga como scene_N.png en esta misma carpeta\n\n")

        f.write("Luego para los videos:\n")
        f.write("6. Abre Grok Imagine: https://grok.com/imagine\n")
        f.write("   (necesitas cuenta X Premium o usar el free tier diario)\n")
        f.write("7. Para cada scene_N.png:\n")
        f.write("   a) Sube la imagen\n")
        f.write("   b) Pega el GROK PROMPT correspondiente\n")
        f.write("   c) Selecciona duración 5s, formato 9:16\n")
        f.write("   d) Descarga como scene_N.mp4 en esta misma carpeta\n\n")
        f.write("Cuando los 6 .mp4 estén listos, el sistema sigue automático.\n\n")

        f.write("=" * 70 + "\n")
        f.write(" PROMPTS POR ESCENA\n")
        f.write("=" * 70 + "\n\n")

        for s in scenes:
            n = s["scene_number"]
            f.write(f"━━━ ESCENA {n} ━━━\n\n")

            narration = s.get("narration", "")
            if narration:
                f.write(f"NARRACIÓN (lo que se escucha): \n   {narration}\n\n")

            visual = s.get("image_prompt") or s.get("visual_prompt", "")
            f.write(f"▼ WHISK PROMPT (para generar scene_{n}.png):\n")
            f.write(f"{visual}\n\n")

            video_prompt = s.get("video_prompt") or s.get("animation_prompt", "")
            if not video_prompt:
                # Generar uno default desde el visual
                video_prompt = (
                    f"Subtle cinematic motion. Camera slowly pushes in. "
                    f"Character makes small natural movements. Atmosphere stays consistent."
                )
            f.write(f"▼ GROK PROMPT (para animar scene_{n}.png → scene_{n}.mp4):\n")
            f.write(f"{video_prompt}\n\n")

            f.write("─" * 60 + "\n\n")


def wait_for_files(scenes: list, video_id: int, file_type: str,
                   poll_interval: float = 3.0, timeout: float = 7200) -> list:
    """
    Bloquea hasta que el usuario haya dropeado todos los archivos esperados.

    file_type: 'image' para .png o .jpg, 'video' para .mp4
    timeout: 2 horas por default (suficiente para que el usuario haga su trabajo)

    Devuelve lista ordenada de paths a los archivos detectados.
    """
    work_dir = os.path.join(MANUAL_DIR, f"video_{video_id}")
    os.makedirs(work_dir, exist_ok=True)

    if file_type == "image":
        exts = [".png", ".jpg", ".jpeg", ".webp"]
        kind = "imágenes"
    elif file_type == "video":
        exts = [".mp4", ".mov", ".webm"]
        kind = "clips"
    else:
        raise ValueError(f"file_type debe ser 'image' o 'video', no '{file_type}'")

    expected_count = len(scenes)
    print(f"\n[Esperando] dropá {expected_count} {kind} en:")
    print(f"   {work_dir}")
    print(f"   Nombres: scene_1{exts[0]}, scene_2{exts[0]}, ... scene_{expected_count}{exts[0]}")
    print(f"   (Reviso cada {poll_interval}s. Ctrl+C para cancelar.)\n")

    start = time.time()
    last_count = -1

    while time.time() - start < timeout:
        found = {}
        for s in scenes:
            n = s["scene_number"]
            for ext in exts:
                candidate = os.path.join(work_dir, f"scene_{n}{ext}")
                if os.path.exists(candidate):
                    found[n] = candidate
                    break

        if len(found) != last_count:
            missing = [s["scene_number"] for s in scenes if s["scene_number"] not in found]
            elapsed = int(time.time() - start)
            mins, secs = elapsed // 60, elapsed % 60
            print(f"  [{mins:02d}:{secs:02d}] Detectados {len(found)}/{expected_count}. "
                  f"Faltan: {missing}")
            last_count = len(found)

        if len(found) == expected_count:
            # Espera 2s extra para asegurar que el archivo terminó de escribirse
            time.sleep(2)
            print(f"\n[OK] Todos los {kind} listos.\n")
            return [found[s["scene_number"]] for s in scenes]

        time.sleep(poll_interval)

    raise TimeoutError(
        f"Timeout: {expected_count - len(found)} archivos no llegaron en "
        f"{timeout/60:.0f} minutos. Reintenta cuando los tengas listos."
    )


def collect_manual_clips(scenes: list, video_id: int,
                        reference_image_path: str = None) -> list:
    """
    Workflow completo del modo free:
      1. Genera PROMPTS.txt, abre Whisk + Grok
      2. Espera 6 imágenes
      3. Espera 6 videos
      4. Devuelve la lista de video_clips para el assembler.
    """
    prepare_manual_workflow(scenes, video_id, reference_image_path)

    # Paso 1: imágenes (opcional — si Whisk + Grok son back-to-back, se puede
    # saltar a esperar solo los videos. Pero hago checkpoint en imágenes para
    # que el usuario pueda iterar prompts de Grok sin re-generar imágenes.)
    print("\n→ PASO 1: imágenes (Whisk)")
    image_paths = wait_for_files(scenes, video_id, "image")
    for p in image_paths:
        print(f"   {os.path.basename(p)}  ({os.path.getsize(p)//1024} KB)")

    # Paso 2: videos
    print("\n→ PASO 2: clips animados (Grok)")
    clip_paths = wait_for_files(scenes, video_id, "video")

    # Construir el formato que espera el assembler
    video_clips = []
    for i, s in enumerate(scenes):
        path = clip_paths[i]
        dur = _probe_duration(path)
        video_clips.append({
            "path": path,
            "duration": dur,
            "scene_number": s["scene_number"],
        })
        print(f"   scene {s['scene_number']}: {os.path.basename(path)} ({dur:.2f}s)")

    return video_clips


def _probe_duration(path: str) -> float:
    """Get duration via ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True,
        )
        return float(r.stdout.strip())
    except Exception:
        return 5.0
