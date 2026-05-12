"""
Demo 3: AICENTURIES anatomical skeleton style — phone addiction.

Tópico Gen-Z viral: cómo el teléfono te destruye en 30 días.
Aprovecha el arco visual de los clips skel_scene_*.mp4 (skeleton anatómico
con piel cristal, órganos brillando) — el daño progresivo cuadra con
trigger → dopamina → cardiovascular → óseo → colapso total.

Estilo basado en aicenturies.com (no el cartoon Pixar).
"""
import asyncio
import os
import sys
import io
import json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from pipeline.voice import generate_all_scenes_audio
from pipeline.assembler import assemble_video, get_detected_encoder, _get_duration
from pipeline.subtitles import generate_ass
from pipeline.music import generate_ambient_track, mix_narration_with_music

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_character(name: str) -> dict:
    path = os.path.join(BASE_DIR, "config", "characters", f"{name}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# Hook fuerte → escalada → revelación → cierre que invita re-watch.
# Narración corta. Frases cortas. Pausas. Eso lo construye Whisper en los subs.
SCRIPT_SCENES = [
    {
        "scene_number": 1,
        "narration": (
            "Tu teléfono es más adictivo que la cocaína. "
            "Y tu cuerpo ya está pagando el precio. "
            "Esto es lo que pasa dentro de ti."
        ),
        "visual_prompt": "anatomical skeleton with translucent crystal skin, looking at glowing phone",
    },
    {
        "scene_number": 2,
        "narration": (
            "Cada notificación libera dopamina en tu cerebro. "
            "La misma dopamina que producen las drogas. "
            "Tu mente se vuelve adicta sin que lo sepas."
        ),
        "visual_prompt": "anatomical skeleton, brain glowing yellow with dopamine, stomach reacting",
    },
    {
        "scene_number": 3,
        "narration": (
            "Tu corazón se acelera con cada scroll. "
            "Tu cortisol sube. Tu sistema cardiovascular vive en estrés crónico. "
            "Tres horas al día son suficientes para causar daño real."
        ),
        "visual_prompt": "anatomical skeleton, heart glowing red, liver glowing orange, blood vessels stressed",
    },
    {
        "scene_number": 4,
        "narration": (
            "Tu cuello se inclina veintisiete grados hacia abajo. "
            "El peso sobre tu columna se multiplica por cinco. "
            "Tus huesos se debilitan. Tu postura se rompe para siempre."
        ),
        "visual_prompt": "anatomical skeleton with weakened cracked bones, head tilted down",
    },
    {
        "scene_number": 5,
        "narration": (
            "En treinta días eres una persona distinta. "
            "Ansiedad. Insomnio. Tu cerebro pide más dopamina. "
            "Y la única forma de salir es soltar el teléfono ahora."
        ),
        "visual_prompt": "anatomical skeleton with all organs glowing red as warning, scared expression",
    },
]


async def main():
    video_id = 3030

    character = load_character("skeleton_viral")  # anatomical aicenturies style
    print("=" * 60)
    print("DEMO 3 — Aicenturies anatomical style")
    print("Topic: Phone addiction — what your phone does to your body")
    print("=" * 60)
    print(f"Character:       {character['name']}")
    print(f"Voice:           {character['voice_id']}")
    print(f"Detected encoder: {get_detected_encoder()}")
    print()

    # 1) Voice
    print("[1/5] Voice (Edge-TTS Spanish)...")
    audio_results = await generate_all_scenes_audio(
        scenes=SCRIPT_SCENES,
        voice_id=character["voice_id"],
        video_id=video_id,
        rate="+5%",   # slightly faster — viral pace
        pitch="-3Hz", # slightly deeper — more serious
    )
    total_audio = sum(a["duration"] for a in audio_results)
    for ar in audio_results:
        print(f"      scene {ar['scene_number']}: {ar['duration']:.2f}s")
    print(f"      total: {total_audio:.2f}s")
    print()

    # 2) Reuse the anatomical skeleton clips (skel_scene_1-5)
    print("[2/5] Using anatomical aicenturies-style clips...")
    video_clips = []
    for i in range(1, 6):
        clip_path = os.path.join(BASE_DIR, "output", "clips", f"skel_scene_{i}.mp4")
        if not os.path.exists(clip_path):
            raise FileNotFoundError(clip_path)
        dur = _get_duration(clip_path)
        video_clips.append({"path": clip_path, "duration": dur, "scene_number": i})
        print(f"      scene {i}: {dur:.2f}s -> ping-pong to {audio_results[i-1]['duration']:.2f}s audio")
    print()

    # 3) Music — horror mood (darker, fits the danger framing)
    print("[3/5] Horror ambient + sidechain duck...")
    audio_dir = os.path.join(BASE_DIR, "output", "audio")
    music_name = f"demo3_music_{video_id}.mp3"
    await generate_ambient_track(total_audio + 2, "horror", music_name)
    music_path = os.path.join(BASE_DIR, "output", "music_cache", music_name)

    narration_concat = os.path.join(audio_dir, f"video_{video_id}_narration.mp3")
    await _concat_mp3s([a["path"] for a in audio_results], narration_concat)

    mixed_audio = os.path.join(audio_dir, f"video_{video_id}_mixed.mp3")
    await mix_narration_with_music(narration_concat, music_path, mixed_audio,
                                   music_volume_db=-14)
    print(f"      ducked mix: {mixed_audio}")
    print()

    # 4) Subtitles — viral preset, 48px, word-by-word
    print("[4/5] Word-level ASS subtitles (viral 48px yellow)...")
    ass_path = generate_ass(SCRIPT_SCENES, audio_results, video_id)
    print(f"      subs: {ass_path}")
    print()

    # 5) Assemble — snappy style for Gen-Z attention spans
    # snappy = 0.25s transitions, energetic mix (fadewhite, zoomin, pixelize, etc.)
    # Pass per-scene audio for sync, and the merged (ducked) audio for the final mix.
    print("[5/5] Assembling with SNAPPY transitions (0.25s, energetic)...")
    out = await assemble_video(
        video_clips=video_clips,
        audio_files=audio_results,           # per-scene for clip sync
        srt_path=ass_path,
        video_id=video_id,
        transition_style="snappy",
        merged_audio_path=mixed_audio,       # ducked master audio for final merge
    )

    final_dur = _get_duration(out)
    size_mb = os.path.getsize(out) / (1024 * 1024)
    print()
    print("=" * 60)
    print(f"DONE: {out}")
    print(f"  Style:    Aicenturies anatomical (translucent crystal skin)")
    print(f"  Topic:    Phone addiction")
    print(f"  Duration: {final_dur:.2f}s")
    print(f"  Size:     {size_mb:.1f} MB")
    print(f"  Transitions: snappy (0.25s, energetic)")
    print("=" * 60)


async def _concat_mp3s(paths, output_path):
    import subprocess
    list_path = output_path + ".list.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in paths:
            f.write(f"file '{os.path.abspath(p).replace(chr(92), '/')}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                    "-c:a", "libmp3lame", "-b:a", "192k", output_path],
                   capture_output=True, text=True)
    os.remove(list_path)


if __name__ == "__main__":
    asyncio.run(main())
