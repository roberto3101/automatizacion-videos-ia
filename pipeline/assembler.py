"""
Professional video assembler using FFmpeg.

Fixes the "frozen frame between transitions" issue by:
- Using ping-pong loop or motion-interpolation instead of crude setpts slow-mo
  when AI clips are shorter than their narration.
- Variety of transitions (crossfade, zoom, whip pan) — configurable per video.
- GPU acceleration (h264_nvenc) when NVIDIA hardware is detected.
- High quality encoding (CRF 18, slow preset on CPU; CQ 19 on GPU).
- Proper aspect ratio handling and faststart for web delivery.
"""
import subprocess
import os
import json
import random

from . import ken_burns

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "final")
SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")

CROSSFADE_DURATION = 0.5  # seconds

# Available xfade transition types — variety prevents the "same fade every time"
# feel that hurts retention.
TRANSITIONS = [
    "fade",            # Soft crossfade (default)
    "fadeblack",       # Dip-to-black
    "fadewhite",       # Dip-to-white (good for hooks)
    "wipeleft",        # Wipe from right to left
    "wiperight",       # Wipe from left to right
    "slideleft",       # Slide off to the left
    "slideright",      # Slide off to the right
    "smoothleft",      # Smooth slide left
    "smoothright",     # Smooth slide right
    "zoomin",          # Zoom into next clip
    "circleopen",      # Iris open
    "circleclose",     # Iris close
    "dissolve",        # Dissolve (similar to fade but pixelated)
    "pixelize",        # Pixelize between clips
]


# ─── GPU detection (cached) ──────────────────────────────────────────────
_gpu_encoder_cache = None


def _encoder_actually_works(codec: str) -> bool:
    """
    Encode a 1-frame test clip to verify the encoder isn't just listed but
    actually runnable. Catches the "h264_nvenc is compiled in but nvcuda.dll
    is missing" case where ffmpeg -encoders lies.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.1:r=24",
             "-c:v", codec, "-f", "null", "-"],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False


def _detect_encoder() -> tuple:
    """
    Detect best encoder that actually WORKS (not just declared in -encoders).
    Returns (codec_name, extra_args).
    """
    global _gpu_encoder_cache
    if _gpu_encoder_cache is not None:
        return _gpu_encoder_cache

    settings = _load_settings()
    mode = settings.get("gpu_acceleration", "auto")  # auto | on | off

    if mode == "off":
        _gpu_encoder_cache = ("libx264", ["-preset", "slow", "-crf", "18"])
        return _gpu_encoder_cache

    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10
        )
        encoders = result.stdout
    except Exception:
        encoders = ""

    # Probe in priority order, but verify each actually works
    if "h264_nvenc" in encoders and _encoder_actually_works("h264_nvenc"):
        _gpu_encoder_cache = ("h264_nvenc",
                              ["-preset", "p5", "-tune", "hq", "-rc", "vbr",
                               "-cq", "19", "-b:v", "8M", "-maxrate", "12M",
                               "-bufsize", "16M"])
    elif "h264_qsv" in encoders and _encoder_actually_works("h264_qsv"):
        _gpu_encoder_cache = ("h264_qsv",
                              ["-preset", "slow", "-global_quality", "20"])
    elif "h264_amf" in encoders and _encoder_actually_works("h264_amf"):
        _gpu_encoder_cache = ("h264_amf",
                              ["-quality", "quality", "-rc", "cqp",
                               "-qp_i", "19", "-qp_p", "19"])
    else:
        _gpu_encoder_cache = ("libx264", ["-preset", "slow", "-crf", "18"])

    return _gpu_encoder_cache


def _fast_encode_args() -> list:
    """Encoder args for intermediate (non-final) renders. Speed over quality."""
    codec, _ = _detect_encoder()
    if codec == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p1", "-rc", "vbr",
                "-cq", "23", "-b:v", "4M", "-maxrate", "8M"]
    if codec == "h264_qsv":
        return ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "23"]
    if codec == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "speed", "-qp_i", "23"]
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "20"]


def _final_encode_args() -> list:
    """Encoder args for the final master file. Quality over speed."""
    codec, extra = _detect_encoder()
    return ["-c:v", codec] + extra


def _load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ─── Public API ──────────────────────────────────────────────────────────

async def assemble_video(video_clips: list, audio_files: list, srt_path: str,
                         video_id: int, resolution: str = "1080x1920",
                         single_audio: bool = False,
                         merged_audio_path: str = None,
                         transition_style: str = None) -> str:
    """
    Assemble the final video.

    audio_files: MUST be per-scene with {path, duration, scene_number}.
        These per-scene durations drive the clip sync (ping-pong / interpolate).

    merged_audio_path: optional. If provided, this single audio file is used as
        the final master audio (typically after sidechain ducking). If omitted,
        audio_files are concatenated.

    single_audio (legacy): kept for backwards compatibility — when True and
        audio_files has a single entry, that entry's path is used as the merged
        audio. New code should use merged_audio_path instead.

    transition_style:
        None         → use the value from settings (default: "mixed")
        "crossfade"  → always 0.5s fade
        "mixed"      → vary transitions per cut for visual interest
        "snappy"     → short 0.25s cuts with energetic transitions (hook style)
        "smooth"     → only smooth/slide transitions
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    final_path = os.path.join(OUTPUT_DIR, f"video_{video_id}_final.mp4")
    w, h = resolution.split("x")

    settings = _load_settings()
    if transition_style is None:
        transition_style = settings.get("transition_style", "mixed")

    video_clips.sort(key=lambda x: x["scene_number"])
    audio_files.sort(key=lambda x: x["scene_number"])

    # Step 1: match each clip to its audio duration WITHOUT freezing frames
    synced_paths = await _sync_clips_to_audio(video_clips, audio_files, video_id,
                                              int(w), int(h))

    # Step 2: join with transitions
    concat_video_path = os.path.join(OUTPUT_DIR, f"video_{video_id}_concat.mp4")
    await _join_clips(synced_paths, concat_video_path, int(w), int(h),
                      transition_style)

    # Step 3: resolve final audio source
    if merged_audio_path and os.path.exists(merged_audio_path):
        concat_audio_path = merged_audio_path
        owns_audio = False
    elif single_audio and audio_files:
        concat_audio_path = audio_files[0]["path"]
        owns_audio = False
    else:
        concat_audio_path = os.path.join(OUTPUT_DIR, f"video_{video_id}_audio.mp3")
        await _concat_audio(audio_files, concat_audio_path)
        owns_audio = True

    # Step 4: final merge with subtitles
    await _merge_final(concat_video_path, concat_audio_path, srt_path, final_path,
                       int(w), int(h))

    # Cleanup intermediates
    _safe_delete(concat_video_path)
    if owns_audio:
        _safe_delete(concat_audio_path)
    for p in synced_paths:
        _safe_delete(p)

    return final_path


# ─── Step 1: sync clips to audio duration ────────────────────────────────

async def _sync_clips_to_audio(clips: list, audio_files: list, video_id: int,
                               w: int, h: int) -> list:
    """
    Match each clip's duration to its narration audio.

    Strategy:
    - If clip is LONGER than audio → trim
    - If clip is SHORTER than audio by <15% → motion interpolation (smooth slow-mo)
    - If clip is SHORTER by >=15% → ping-pong extend (forward + reverse loop)
        This is the KEY fix for the "static frame between transitions" issue.
        Crude setpts slow-mo on AI video creates visible frame duplication
        because source fps is low. Ping-pong always has real motion.
    """
    audio_dur_map = {}
    for af in audio_files:
        audio_dur_map[af["scene_number"]] = af.get("duration", _get_duration(af["path"]))

    synced = []
    for i, clip in enumerate(clips):
        scene_num = clip["scene_number"]
        audio_dur = audio_dur_map.get(scene_num, _get_duration(clip["path"]))
        clip_dur = _get_duration(clip["path"])

        scaled = os.path.join(OUTPUT_DIR, f"video_{video_id}_synced_{i}.mp4")

        if clip_dur >= audio_dur + 0.1:
            # Trim to audio length
            _scale_and_trim(clip["path"], scaled, w, h, audio_dur)
        elif clip_dur >= audio_dur * 0.85:
            # Within 15% — use motion interpolation (smoother than ping-pong here)
            try:
                scaled_pre = os.path.join(OUTPUT_DIR, f"video_{video_id}_scaledpre_{i}.mp4")
                _scale_only(clip["path"], scaled_pre, w, h)
                ken_burns.extend_short_clip(scaled_pre, scaled, audio_dur,
                                            method="interpolate")
                _safe_delete(scaled_pre)
            except Exception as e:
                print(f"[assembler] scene {scene_num} interpolate failed: {e}")
                _scale_and_trim(clip["path"], scaled, w, h, audio_dur)
        else:
            # Significantly shorter — ping-pong. Fixes the "frozen frame at
            # transitions" artifact caused by crude setpts slow-mo on AI clips.
            try:
                scaled_pre = os.path.join(OUTPUT_DIR, f"video_{video_id}_scaledpre_{i}.mp4")
                _scale_only(clip["path"], scaled_pre, w, h)
                ken_burns.extend_short_clip(scaled_pre, scaled, audio_dur,
                                            method="pingpong")
                _safe_delete(scaled_pre)
            except Exception as e:
                print(f"[assembler] scene {scene_num} pingpong failed: {e}")
                _scale_and_trim(clip["path"], scaled, w, h, audio_dur)

        synced.append(scaled)

    return synced


def _scale_only(input_path: str, output_path: str, w: int, h: int):
    """Scale clip to target resolution, preserve duration."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1,fps=24"
        ),
    ] + _fast_encode_args() + [
        "-pix_fmt", "yuv420p", "-an",
        output_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise Exception(f"FFmpeg scale error: {proc.stderr[-500:]}")


def _scale_and_trim(input_path: str, output_path: str, w: int, h: int,
                    duration: float):
    """Scale + trim to a specific duration."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1,fps=24"
        ),
        "-t", f"{duration:.3f}",
    ] + _fast_encode_args() + [
        "-pix_fmt", "yuv420p", "-an", "-r", "24",
        output_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise Exception(f"FFmpeg scale+trim error: {proc.stderr[-500:]}")


# ─── Step 2: join clips with transitions ─────────────────────────────────

def _pick_transitions(num_cuts: int, style: str) -> list:
    """Pick a list of (transition_name, duration) for each cut."""
    if style == "crossfade":
        return [("fade", CROSSFADE_DURATION)] * num_cuts

    if style == "snappy":
        snappy = ["fade", "fadewhite", "wipeleft", "wiperight", "zoomin", "pixelize"]
        return [(random.choice(snappy), 0.25) for _ in range(num_cuts)]

    if style == "smooth":
        smooth = ["fade", "dissolve", "smoothleft", "smoothright", "circleopen"]
        return [(random.choice(smooth), 0.5) for _ in range(num_cuts)]

    # "mixed" (default): use variety, slightly favoring fade for safety
    mixed_pool = (
        ["fade"] * 3 +
        ["dissolve", "smoothleft", "smoothright", "circleopen",
         "wipeleft", "wiperight", "zoomin"]
    )
    return [(random.choice(mixed_pool), CROSSFADE_DURATION) for _ in range(num_cuts)]


async def _join_clips(clip_paths: list, output_path: str, w: int, h: int,
                      transition_style: str):
    """Join clips with the chosen transition style."""
    if len(clip_paths) == 1:
        cmd = ["ffmpeg", "-y", "-i", clip_paths[0], "-c", "copy", output_path]
        subprocess.run(cmd, capture_output=True, text=True)
        return

    transitions = _pick_transitions(len(clip_paths) - 1, transition_style)
    durations = [_get_duration(p) for p in clip_paths]

    if len(clip_paths) == 2:
        trans_name, trans_dur = transitions[0]
        offset = max(durations[0] - trans_dur, 0.1)
        cmd = [
            "ffmpeg", "-y",
            "-i", clip_paths[0], "-i", clip_paths[1],
            "-filter_complex",
            f"[0:v][1:v]xfade=transition={trans_name}:duration={trans_dur}:"
            f"offset={offset:.2f},setpts=PTS-STARTPTS[v]",
            "-map", "[v]",
        ] + _fast_encode_args() + [
            "-pix_fmt", "yuv420p", "-an",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            await _simple_concat(clip_paths, output_path)
        return

    # 3+ clips — chain xfade
    inputs = []
    for p in clip_paths:
        inputs.extend(["-i", p])

    filter_parts = []
    accumulated = durations[0]

    trans_name, trans_dur = transitions[0]
    offset = max(accumulated - trans_dur, 0.1)
    filter_parts.append(
        f"[0:v][1:v]xfade=transition={trans_name}:duration={trans_dur}:"
        f"offset={offset:.2f},setpts=PTS-STARTPTS[v1]"
    )
    accumulated = accumulated + durations[1] - trans_dur

    for i in range(2, len(clip_paths)):
        trans_name, trans_dur = transitions[i - 1]
        prev = f"v{i-1}"
        curr = f"v{i}"
        offset = max(accumulated - trans_dur, 0.1)
        filter_parts.append(
            f"[{prev}][{i}:v]xfade=transition={trans_name}:duration={trans_dur}:"
            f"offset={offset:.2f},setpts=PTS-STARTPTS[{curr}]"
        )
        accumulated = accumulated + durations[i] - trans_dur

    last_label = f"v{len(clip_paths)-1}"
    filtergraph = ";".join(filter_parts)

    cmd = (
        ["ffmpeg", "-y"] + inputs +
        ["-filter_complex", filtergraph,
         "-map", f"[{last_label}]"] +
        _fast_encode_args() +
        ["-pix_fmt", "yuv420p", "-an", output_path]
    )

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Some transitions can fail with certain pixel formats — retry with plain fade
        if transition_style != "crossfade":
            print(f"[assembler] mixed transitions failed, retrying with crossfade")
            await _join_clips(clip_paths, output_path, w, h, "crossfade")
        else:
            await _simple_concat(clip_paths, output_path)


async def _simple_concat(clip_paths: list, output_path: str):
    """Fallback: simple concatenation without transitions."""
    concat_file = output_path + ".txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for p in clip_paths:
            abs_p = os.path.abspath(p).replace("\\", "/")
            f.write(f"file '{abs_p}'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
           "-c", "copy", output_path]
    subprocess.run(cmd, capture_output=True, text=True)
    _safe_delete(concat_file)


# ─── Step 3: concat narration audio ──────────────────────────────────────

async def _concat_audio(audio_files: list, output_path: str):
    """Concatenate per-scene audio files into one continuous narration track."""
    concat_file = output_path + ".txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for af in audio_files:
            abs_p = os.path.abspath(af["path"]).replace("\\", "/")
            f.write(f"file '{abs_p}'\n")

    # Re-encode rather than -c copy: per-scene files may have different headers
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
           "-c:a", "libmp3lame", "-b:a", "192k", output_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise Exception(f"FFmpeg audio concat error: {proc.stderr[-500:]}")
    _safe_delete(concat_file)


# ─── Step 4: final merge with subtitles ──────────────────────────────────

async def _merge_final(video_path: str, audio_path: str, srt_path: str,
                       output_path: str, w: int, h: int):
    """Final master render: video + audio + burned subtitles."""
    sub_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
    is_ass = srt_path.endswith(".ass")

    vf = f"ass='{sub_escaped}'" if is_ass else (
        f"subtitles='{sub_escaped}':"
        f"force_style='FontSize=24,FontName=Arial,PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,Outline=2,Shadow=1,MarginV=60'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-vf", vf,
    ] + _final_encode_args() + [
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # GPU encoders sometimes fail with certain filtergraphs — retry with libx264
        codec, _ = _detect_encoder()
        if codec != "libx264":
            print(f"[assembler] {codec} merge failed, retrying with libx264")
            cmd_cpu = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", audio_path,
                "-vf", vf,
                "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                output_path,
            ]
            proc = subprocess.run(cmd_cpu, capture_output=True, text=True)
            if proc.returncode != 0:
                raise Exception(f"FFmpeg merge error (CPU fallback): {proc.stderr[-500:]}")
        else:
            raise Exception(f"FFmpeg merge error: {proc.stderr[-500:]}")


# ─── Helpers ─────────────────────────────────────────────────────────────

def _get_duration(filepath: str) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", filepath],
            capture_output=True, text=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 5.0


def _safe_delete(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def get_detected_encoder() -> str:
    """Exposed for UI/diagnostics."""
    codec, _ = _detect_encoder()
    return codec
