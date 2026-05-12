"""
Background music module.
Priority:
1. Real tracks from assets/music/{mood}/ (highest quality)
2. FFmpeg synthesis (fallback, zero cost)

Users can drop royalty-free MP3/WAV files into assets/music/horror/, assets/music/mystery/, etc.
The system picks randomly from available tracks.
"""
import subprocess
import os
import random

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "music_cache")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "music")

MOODS = ["horror", "mystery", "calm", "epic"]
VOLUME_MAP = {"horror": -20, "mystery": -18, "calm": -16, "epic": -18}


def _find_real_track(mood: str) -> str:
    """Look for real music files in assets/music/{mood}/."""
    mood_dir = os.path.join(ASSETS_DIR, mood)
    if not os.path.isdir(mood_dir):
        return ""
    tracks = [f for f in os.listdir(mood_dir) if f.endswith((".mp3", ".wav", ".ogg", ".m4a"))]
    if not tracks:
        return ""
    return os.path.join(mood_dir, random.choice(tracks))


async def generate_ambient_track(duration: float, mood: str = "horror",
                                  output_filename: str = "ambient.mp3") -> str:
    """
    Get background music track.
    1. Try real tracks from assets/music/{mood}/
    2. Fall back to FFmpeg synthesis
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    # Priority 1: Real track
    real_track = _find_real_track(mood)
    if real_track:
        # Trim/loop the real track to match video duration
        await _prepare_track(real_track, output_path, duration)
        return output_path

    # Priority 2: FFmpeg synthesis (improved quality)
    await _synthesize_track(output_path, duration, mood)
    return output_path


async def _prepare_track(source: str, output: str, duration: float):
    """Prepare a real music track: loop if too short, trim if too long, fade in/out."""
    src_dur = _get_duration(source)

    if src_dur >= duration:
        # Trim + fade
        cmd = [
            "ffmpeg", "-y", "-i", source,
            "-t", str(duration),
            "-af", f"afade=t=in:d=2,afade=t=out:st={max(0, duration-4)}:d=4",
            "-c:a", "libmp3lame", "-b:a", "192k",
            output,
        ]
    else:
        # Loop + trim + fade
        loops = int(duration / src_dur) + 2
        cmd = [
            "ffmpeg", "-y", "-stream_loop", str(loops), "-i", source,
            "-t", str(duration),
            "-af", f"afade=t=in:d=2,afade=t=out:st={max(0, duration-4)}:d=4",
            "-c:a", "libmp3lame", "-b:a", "192k",
            output,
        ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Copy as-is if processing fails
        import shutil
        shutil.copy2(source, output)


async def _synthesize_track(output: str, duration: float, mood: str):
    """Improved FFmpeg synthesis — layered drones with movement."""
    if mood == "horror":
        freq1 = random.choice([55, 65, 73, 82])
        freq2 = freq1 * 1.5
        freq3 = freq1 * 0.5
        fc = (
            f"sine=frequency={freq1}:duration={duration}[s1];"
            f"sine=frequency={freq2}:duration={duration}[s2];"
            f"sine=frequency={freq3}:duration={duration}[s3];"
            f"anoisesrc=duration={duration}:color=brown:amplitude=0.02[noise];"
            f"[s1]volume=0.3[v1];[s2]volume=0.15[v2];[s3]volume=0.4[v3];"
            f"[v1][v2][v3][noise]amix=inputs=4:duration=first[raw];"
            f"[raw]tremolo=f=0.07:d=0.5,lowpass=f=350,"
            f"afade=t=in:d=3,afade=t=out:st={max(0,duration-5)}:d=5,volume=0.5[out]"
        )
    elif mood == "mystery":
        freq1 = random.choice([110, 130, 146])
        freq2 = freq1 * 1.26
        fc = (
            f"sine=frequency={freq1}:duration={duration}[s1];"
            f"sine=frequency={freq2}:duration={duration}[s2];"
            f"anoisesrc=duration={duration}:color=pink:amplitude=0.01[noise];"
            f"[s1]volume=0.25[v1];[s2]volume=0.2[v2];"
            f"[v1][v2][noise]amix=inputs=3:duration=first[raw];"
            f"[raw]tremolo=f=0.12:d=0.3,lowpass=f=500,"
            f"afade=t=in:d=2,afade=t=out:st={max(0,duration-4)}:d=4,volume=0.4[out]"
        )
    elif mood == "epic":
        freq1 = random.choice([65, 82, 98])
        freq2 = freq1 * 2
        fc = (
            f"sine=frequency={freq1}:duration={duration}[s1];"
            f"sine=frequency={freq2}:duration={duration}[s2];"
            f"anoisesrc=duration={duration}:color=brown:amplitude=0.015[noise];"
            f"[s1]volume=0.35[v1];[s2]volume=0.2[v2];"
            f"[v1][v2][noise]amix=inputs=3:duration=first[raw];"
            f"[raw]lowpass=f=450,"
            f"afade=t=in:d=3,afade=t=out:st={max(0,duration-5)}:d=5,volume=0.5[out]"
        )
    else:  # calm
        freq1 = random.choice([220, 261, 293])
        freq2 = freq1 * 1.5
        fc = (
            f"sine=frequency={freq1}:duration={duration}[s1];"
            f"sine=frequency={freq2}:duration={duration}[s2];"
            f"[s1]volume=0.2[v1];[s2]volume=0.15[v2];"
            f"[v1][v2]amix=inputs=2:duration=first[raw];"
            f"[raw]tremolo=f=0.06:d=0.2,lowpass=f=700,"
            f"afade=t=in:d=3,afade=t=out:st={max(0,duration-4)}:d=4,volume=0.35[out]"
        )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-filter_complex", fc,
        "-map", "[out]",
        "-t", str(duration),
        "-c:a", "libmp3lame", "-b:a", "128k",
        output,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Ultra fallback: simple drone
        cmd2 = [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=80:duration={duration}",
            "-af", f"volume=0.15,afade=t=in:d=2,afade=t=out:st={max(0,duration-3)}:d=3",
            "-c:a", "libmp3lame", "-b:a", "128k", output,
        ]
        subprocess.run(cmd2, capture_output=True, text=True)


async def mix_narration_with_music(narration_path: str, music_path: str,
                                    output_path: str, music_volume_db: int = -20) -> str:
    """
    Mix narration with background music using REAL sidechain ducking.

    When the narrator speaks, the music automatically dips ~12dB below the
    base volume. When the narrator is silent (pauses), music swells back up.
    This is the same technique used in professional podcasts and ads — far
    better than a flat volume mix.

    music_volume_db: base music volume relative to 0dB (negative = quieter).
                     During speech, music ducks an additional 12dB below this.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    dur = _get_duration(narration_path)
    fade_start = max(0, dur - 3)

    # sidechaincompress params explained:
    # - threshold=0.05: music starts ducking when narration audio exceeds this level
    # - ratio=8: every 8dB of narration above threshold pushes music down 1dB
    # - attack=5: how fast the duck engages (ms) — fast for tight ducking
    # - release=300: how fast music returns when narration drops (ms)
    # - makeup=0: don't boost output after compression
    # The asplit on narration is needed because sidechaincompress consumes it
    # as a control signal AND we need it as a mix input.
    filter_complex = (
        f"[0:a]asplit=2[voice][voice_sc];"
        f"[1:a]volume={music_volume_db}dB,"
        f"afade=t=in:d=1,afade=t=out:st={fade_start}:d=3[music_base];"
        f"[music_base][voice_sc]sidechaincompress="
        f"threshold=0.05:ratio=8:attack=5:release=300:makeup=0[music_ducked];"
        f"[voice][music_ducked]amix=inputs=2:duration=first:dropout_transition=0,"
        f"loudnorm=I=-14:TP=-1.5:LRA=11[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", narration_path, "-i", music_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "libmp3lame", "-b:a", "192k",
        output_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Fallback: simpler mix without ducking (still better than copy)
        fallback_filter = (
            f"[1:a]volume={music_volume_db}dB,"
            f"afade=t=in:d=1,afade=t=out:st={fade_start}:d=3[music];"
            f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=3[out]"
        )
        cmd2 = [
            "ffmpeg", "-y",
            "-i", narration_path, "-i", music_path,
            "-filter_complex", fallback_filter,
            "-map", "[out]",
            "-c:a", "libmp3lame", "-b:a", "192k",
            output_path,
        ]
        proc2 = subprocess.run(cmd2, capture_output=True, text=True)
        if proc2.returncode != 0:
            import shutil
            shutil.copy2(narration_path, output_path)
    return output_path


def _get_duration(path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True,
        )
        return float(r.stdout.strip())
    except Exception:
        return 60.0


def get_mood_volume(mood: str) -> int:
    return VOLUME_MAP.get(mood, -20)
