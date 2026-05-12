"""
Demo 4: AICENTURIES anatomical style — using the operator's REFERENCE images.

No fal.ai needed. Uses the anatomical reference image directly and applies
region-specific Ken Burns per scene (head zoom for brain talk, chest zoom for
heart talk, etc.) — replicating the per-organ zoom rhythm of aicenturies.

Topic: Phone addiction. The references give us the photoreal anatomical look
the operator confirmed is the actual viral style.
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
from pipeline.ken_burns import image_to_video_region

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_character(name: str) -> dict:
    with open(os.path.join(BASE_DIR, "config", "characters", f"{name}.json"),
              "r", encoding="utf-8") as f:
        return json.load(f)


# Reference image: anatomical amber translucent (Reference 1 from operator's pack)
REF_IMAGE = os.path.join(BASE_DIR, "assets", "references", "skeleton",
                         "anatomical_amber_translucent.png")

# Each scene zooms toward a different body region of the same reference.
# (x_pct, y_pct, start_zoom, end_zoom) — y_pct: 0.0=top, 1.0=bottom of body
SCRIPT_SCENES = [
    {
        "scene_number": 1,
        "narration": (
            "Tu teléfono es más adictivo que la cocaína. "
            "Y tu cuerpo ya está pagando el precio."
        ),
        "region": {"x": 0.5, "y": 0.5, "start_zoom": 1.0, "end_zoom": 1.15},
        "label": "Full body, slow push",
    },
    {
        "scene_number": 2,
        "narration": (
            "Cada notificación libera dopamina en tu cerebro. "
            "La misma dopamina que producen las drogas."
        ),
        "region": {"x": 0.5, "y": 0.10, "start_zoom": 1.2, "end_zoom": 1.7},
        "label": "Zoom to skull / brain",
    },
    {
        "scene_number": 3,
        "narration": (
            "Tu corazón se acelera con cada scroll. "
            "El cortisol sube. Vives en estrés crónico."
        ),
        "region": {"x": 0.5, "y": 0.32, "start_zoom": 1.3, "end_zoom": 1.8},
        "label": "Zoom to ribcage / heart",
    },
    {
        "scene_number": 4,
        "narration": (
            "Tu cuello se inclina veintisiete grados. "
            "El peso sobre tu columna se multiplica por cinco. "
            "Tus huesos se rompen para siempre."
        ),
        "region": {"x": 0.5, "y": 0.20, "start_zoom": 1.4, "end_zoom": 1.9},
        "label": "Zoom to neck / spine",
    },
    {
        "scene_number": 5,
        "narration": (
            "En treinta días eres otra persona. "
            "Ansiedad. Insomnio. Tu cerebro pide más. "
            "La única salida es soltarlo ahora."
        ),
        "region": {"x": 0.5, "y": 0.5, "start_zoom": 1.5, "end_zoom": 1.05},
        "label": "Pull back to full body",
    },
]


async def main():
    video_id = 4040
    character = load_character("skeleton_viral")

    print("=" * 60)
    print("DEMO 4 — Aicenturies anatomical (using YOUR references)")
    print(f"Reference image: {os.path.basename(REF_IMAGE)}")
    print(f"Character: {character['name']}")
    print(f"Detected encoder: {get_detected_encoder()}")
    print("=" * 60)
    print()

    if not os.path.exists(REF_IMAGE):
        raise FileNotFoundError(f"Reference image missing: {REF_IMAGE}")

    # 1) Voice
    print("[1/6] Voice (Edge-TTS Spanish)...")
    audio_results = await generate_all_scenes_audio(
        scenes=SCRIPT_SCENES,
        voice_id=character["voice_id"],
        video_id=video_id,
        rate="+5%",
        pitch="-3Hz",
    )
    total_audio = sum(a["duration"] for a in audio_results)
    for ar in audio_results:
        print(f"      scene {ar['scene_number']}: {ar['duration']:.2f}s")
    print(f"      total: {total_audio:.2f}s")
    print()

    # 2) Build per-scene clips from the SAME reference image, zoomed to
    #    different body regions matching the narration
    print("[2/6] Building per-scene clips with region-targeted Ken Burns...")
    clips_dir = os.path.join(BASE_DIR, "output", "clips")
    os.makedirs(clips_dir, exist_ok=True)
    video_clips = []
    for i, scene in enumerate(SCRIPT_SCENES):
        n = scene["scene_number"]
        audio_dur = audio_results[i]["duration"]
        clip_path = os.path.join(clips_dir, f"anat_v{video_id}_scene_{n}.mp4")
        r = scene["region"]
        image_to_video_region(
            image_path=REF_IMAGE,
            output_path=clip_path,
            duration=audio_dur,
            target_x_pct=r["x"], target_y_pct=r["y"],
            start_zoom=r["start_zoom"], end_zoom=r["end_zoom"],
        )
        actual = _get_duration(clip_path)
        print(f"      scene {n}: {scene['label']} -> {actual:.2f}s clip")
        video_clips.append({
            "path": clip_path,
            "duration": actual,
            "scene_number": n,
        })
    print()

    # 3) Music + sidechain duck
    print("[3/6] Mystery ambient + sidechain duck...")
    audio_dir = os.path.join(BASE_DIR, "output", "audio")
    music_name = f"demo4_music_{video_id}.mp3"
    await generate_ambient_track(total_audio + 2, "mystery", music_name)
    music_path = os.path.join(BASE_DIR, "output", "music_cache", music_name)

    narration_concat = os.path.join(audio_dir, f"video_{video_id}_narration.mp3")
    await _concat_mp3s([a["path"] for a in audio_results], narration_concat)

    mixed_audio = os.path.join(audio_dir, f"video_{video_id}_mixed.mp3")
    await mix_narration_with_music(narration_concat, music_path, mixed_audio,
                                   music_volume_db=-14)
    print(f"      ducked mix: {mixed_audio}")
    print()

    # 4) Subtitles
    print("[4/6] Word-level ASS subtitles (viral 48px)...")
    ass_path = generate_ass(SCRIPT_SCENES, audio_results, video_id)
    print()

    # 5) Assemble — snappy transitions because clips already share the image,
    #    we WANT cuts to feel punchy, not lazy
    print("[5/6] Assembling with snappy transitions...")
    out = await assemble_video(
        video_clips=video_clips,
        audio_files=audio_results,
        srt_path=ass_path,
        video_id=video_id,
        transition_style="snappy",
        merged_audio_path=mixed_audio,
    )
    print()

    # 6) Report
    final_dur = _get_duration(out)
    size_mb = os.path.getsize(out) / (1024 * 1024)
    print("=" * 60)
    print(f"DONE: {out}")
    print(f"  Style:     Aicenturies anatomical (photoreal, NOT cartoon)")
    print(f"  Source:    1 reference image, 5 region zooms")
    print(f"  Topic:     Phone addiction")
    print(f"  Duration:  {final_dur:.2f}s")
    print(f"  Size:      {size_mb:.1f} MB")
    print(f"  No fal.ai: produced 100% locally")
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
