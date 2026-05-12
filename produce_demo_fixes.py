"""
Demo of the May 2026 pipeline overhaul.

Exercises:
  - Ping-pong clip extension (audio longer than AI clip)
  - Mixed transitions (14 styles)
  - Sidechain audio ducking
  - Word-level ASS subtitles, viral preset 48px
  - GPU encoder auto-detection (verified)
  - Production insights would also kick in if a DB context is passed
"""
import asyncio
import os
import sys
import io

# Force UTF-8 on Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from pipeline.voice import generate_all_scenes_audio
from pipeline.assembler import assemble_video, get_detected_encoder, _get_duration
from pipeline.subtitles import generate_ass
from pipeline.music import generate_ambient_track, mix_narration_with_music


# A 3-scene script with narration deliberately longer than the 5s AI clips
# in output/clips/ so the ping-pong fix is exercised.
SCRIPT = {
    "title": "The Door That Wasn't There",
    "scenes": [
        {
            "scene_number": 1,
            "narration": (
                "There's a door at the end of my hallway. "
                "It wasn't there yesterday. "
                "I checked the blueprints. The wall is solid."
            ),
            "visual_prompt": "dark hallway, dim light, mysterious",
            "duration_seconds": 8,
        },
        {
            "scene_number": 2,
            "narration": (
                "I touched the handle. It was warm. "
                "Warm like a hand that just let go. "
                "And then I heard breathing from the other side."
            ),
            "visual_prompt": "close-up on door handle, shadow",
            "duration_seconds": 9,
        },
        {
            "scene_number": 3,
            "narration": (
                "I opened it. And what was inside... "
                "was my bedroom. But everything was reversed. "
                "And someone was already in my bed, asleep, breathing my name."
            ),
            "visual_prompt": "reversed bedroom interior, eerie",
            "duration_seconds": 10,
        },
    ],
}


async def main():
    video_id = 7777
    base_dir = os.path.dirname(__file__)

    print("=" * 60)
    print("DEMO BUILD — Pipeline overhaul May 2026")
    print("=" * 60)
    print(f"Detected encoder: {get_detected_encoder()}")
    print()

    # 1) Voice generation with Kokoro (free, local, sounds natural)
    print("[1/5] Generating voice with Kokoro am_adam...")
    audio_results = await generate_all_scenes_audio(
        scenes=SCRIPT["scenes"],
        voice_id="kokoro:am_adam",
        video_id=video_id,
    )
    for ar in audio_results:
        print(f"      scene {ar['scene_number']}: {ar['duration']:.2f}s — {ar['path']}")

    total_audio = sum(a["duration"] for a in audio_results)
    print(f"      total narration: {total_audio:.2f}s")
    print()

    # 2) Reuse existing AI clips. They are ~5s each — audio is longer,
    #    so the ping-pong path will be triggered.
    print("[2/5] Mapping audio to existing AI clips...")
    video_clips = []
    for i, scene in enumerate(SCRIPT["scenes"], start=1):
        clip_path = os.path.join(base_dir, "output", "clips", f"final_scene_{i}.mp4")
        if not os.path.exists(clip_path):
            raise FileNotFoundError(f"Missing source clip: {clip_path}")
        clip_dur = _get_duration(clip_path)
        video_clips.append({
            "path": clip_path,
            "duration": clip_dur,
            "scene_number": i,
        })
        print(f"      scene {i}: clip={clip_dur:.2f}s — ping-pong fills {clip_dur:.2f}s → audio length")
    print()

    # 3) Generate background music + sidechain duck under the narration
    print("[3/5] Synthesizing horror ambient + sidechain ducking...")
    audio_dir = os.path.join(base_dir, "output", "audio")
    music_path = await _build_track(audio_dir, video_id, total_audio + 2)

    # Concat narration into one mp3, then duck music under it
    narration_concat = os.path.join(audio_dir, f"video_{video_id}_narration.mp3")
    await _concat_mp3s([a["path"] for a in audio_results], narration_concat)
    mixed_audio = os.path.join(audio_dir, f"video_{video_id}_mixed.mp3")
    await mix_narration_with_music(narration_concat, music_path, mixed_audio,
                                   music_volume_db=-16)
    print(f"      ducked mix: {mixed_audio}")
    print()

    # 4) Word-level ASS subtitles with Whisper
    print("[4/5] Generating word-by-word ASS subtitles (viral preset)...")
    ass_path = generate_ass(SCRIPT["scenes"], audio_results, video_id)
    print(f"      subtitles: {ass_path}")
    print()

    # 5) Assemble — mixed transitions, ping-pong sync, GPU encoder
    print("[5/5] Assembling with mixed transitions + ping-pong sync...")
    mixed_dur = _get_duration(mixed_audio)
    single_audio = [{
        "path": mixed_audio,
        "duration": mixed_dur,
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
    final_size_mb = os.path.getsize(out) / 1024 / 1024
    print()
    print("=" * 60)
    print(f"DONE: {out}")
    print(f"  duration: {final_dur:.2f}s (audio was {total_audio:.2f}s)")
    print(f"  size:     {final_size_mb:.1f} MB")
    print(f"  encoder:  {get_detected_encoder()}")
    print("=" * 60)


async def _build_track(audio_dir: str, video_id: int, duration: float) -> str:
    track_name = f"ambient_video_{video_id}.mp3"
    await generate_ambient_track(duration, "horror", track_name)
    return os.path.join(os.path.dirname(__file__), "output", "music_cache", track_name)


async def _concat_mp3s(paths: list, output_path: str):
    """Concat per-scene narration mp3s into one stream for ducking."""
    import subprocess
    list_path = output_path + ".list.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in paths:
            f.write(f"file '{os.path.abspath(p).replace(chr(92), '/')}'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
           "-c:a", "libmp3lame", "-b:a", "192k", output_path]
    subprocess.run(cmd, capture_output=True, text=True)
    os.remove(list_path)


if __name__ == "__main__":
    asyncio.run(main())
