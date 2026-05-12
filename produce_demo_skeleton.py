"""
Demo 2: Skeleton Cartoon (Pixar style) using the new character context.

Reuses the Julio César clips already in output/clips/ (originally produced by
FLUX Schnell + Veo 3.1 Fast). Narration in Spanish matches the visuals.

Demonstrates:
  - Loading character context from config/characters/skeleton_cartoon.json
  - Word-level ASS subtitles at the new 48px viral size
  - Mixed transitions across 6 cuts
  - Sidechain audio ducking (mystery mood)
  - GPU encoding (h264_amf)
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


# Narration designed to MATCH the existing skeleton clips
# (Roman toga + laptop, Roman armor pointing at screen, etc.)
SCRIPT_SCENES = [
    {
        "scene_number": 1,
        "narration": "Imagina que Julio César tuviera un canal de YouTube. Su primer video sería épico.",
        "visual_prompt": "Skeleton in Roman toga at modern desk with laptop",
    },
    {
        "scene_number": 2,
        "narration": "Cómo conquistar las Galias en diez pasos. Tres millones de vistas el primer día.",
        "visual_prompt": "Skeleton in armor pointing at screen with views counter",
    },
    {
        "scene_number": 3,
        "narration": "Cleopatra le dejaría un corazón en los comentarios. Y Bruto comentaría con un emoji de cuchillo.",
        "visual_prompt": "Skeleton looking at phone suspiciously",
    },
    {
        "scene_number": 4,
        "narration": "Su video más viral sería un Qué hay en mi toga. Espada, corona, y mapa de conquistas.",
        "visual_prompt": "Skeleton holding sword and scroll",
    },
    {
        "scene_number": 5,
        "narration": "Pero un día subiría: Por qué ya no confío en el Senado. Y Bruto le dejaría un dislike. Solo uno.",
        "visual_prompt": "Skeleton scared looking at dislike button",
    },
    {
        "scene_number": 6,
        "narration": "Julio César no necesitaba un imperio. Solo WiFi, un micrófono, y un buen algoritmo.",
        "visual_prompt": "Skeleton on golden throne with headphones and laptop",
    },
]


async def main():
    video_id = 5555

    character = load_character("skeleton_cartoon")
    print("=" * 60)
    print("DEMO 2 — Skeleton Cartoon (context-driven)")
    print("=" * 60)
    print(f"Character:       {character['name']}")
    print(f"Voice:           {character['voice_id']}")
    print(f"Visual base:     {character['visual_prompt'][:80]}...")
    print(f"Detected encoder: {get_detected_encoder()}")
    print()

    # 1) Voice — match the character voice from JSON
    print("[1/5] Generating voice with character voice...")
    audio_results = await generate_all_scenes_audio(
        scenes=SCRIPT_SCENES,
        voice_id=character["voice_id"],          # es-MX-JorgeNeural
        video_id=video_id,
        rate="+3%",
        pitch="-2Hz",
    )
    total_audio = sum(a["duration"] for a in audio_results)
    for ar in audio_results:
        print(f"      scene {ar['scene_number']}: {ar['duration']:.2f}s")
    print(f"      total narration: {total_audio:.2f}s")
    print()

    # 2) Reuse the existing skeleton clips (Veo 3.1 Fast output)
    print("[2/5] Using existing Veo 3.1 skeleton clips...")
    video_clips = []
    for i in range(1, 7):
        clip_path = os.path.join(BASE_DIR, "output", "clips", f"final_scene_{i}.mp4")
        if not os.path.exists(clip_path):
            raise FileNotFoundError(clip_path)
        dur = _get_duration(clip_path)
        video_clips.append({"path": clip_path, "duration": dur, "scene_number": i})
        print(f"      scene {i}: {dur:.2f}s (will ping-pong to match {audio_results[i-1]['duration']:.2f}s audio)")
    print()

    # 3) Music + sidechain duck
    print("[3/5] Mystery ambient + sidechain ducking...")
    audio_dir = os.path.join(BASE_DIR, "output", "audio")
    music_name = f"demo2_music_{video_id}.mp3"
    await generate_ambient_track(total_audio + 2, "mystery", music_name)
    music_path = os.path.join(BASE_DIR, "output", "music_cache", music_name)

    narration_concat = os.path.join(audio_dir, f"video_{video_id}_narration.mp3")
    await _concat_mp3s([a["path"] for a in audio_results], narration_concat)

    mixed_audio = os.path.join(audio_dir, f"video_{video_id}_mixed.mp3")
    await mix_narration_with_music(narration_concat, music_path, mixed_audio,
                                   music_volume_db=-14)
    print(f"      mixed audio: {mixed_audio}")
    print()

    # 4) Subtitles (viral 48px preset)
    print("[4/5] Word-level ASS subtitles (viral 48px)...")
    ass_path = generate_ass(SCRIPT_SCENES, audio_results, video_id)
    print(f"      subtitles: {ass_path}")
    print()

    # 5) Assemble — mixed transitions, ping-pong on each scene
    print("[5/5] Assembling 6 scenes with mixed transitions + ping-pong...")
    single_audio = [{
        "path": mixed_audio,
        "duration": _get_duration(mixed_audio),
        "scene_number": 1,
    }]
    out = await assemble_video(
        video_clips=video_clips,
        audio_files=single_audio,
        srt_path=ass_path,
        video_id=video_id,
        transition_style="mixed",
        single_audio=True,
    )

    final_dur = _get_duration(out)
    size_mb = os.path.getsize(out) / (1024 * 1024)
    print()
    print("=" * 60)
    print(f"DONE: {out}")
    print(f"  Character: {character['name']}")
    print(f"  Duration: {final_dur:.2f}s (audio was {total_audio:.2f}s)")
    print(f"  Size:     {size_mb:.1f} MB")
    print(f"  Encoder:  {get_detected_encoder()}")
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
