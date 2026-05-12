"""
Ken Burns effect for static images.

Converts a still image into a video clip with slow zoom/pan, producing
the cinematic motion that prevents "frozen frame" artifacts in transitions.

Used when:
- The user provides a static image instead of a video clip
- AI video generation fails and we want to use a fal.ai-generated image
- A reference image (R2V) needs to be turned into a moving clip
"""
import os
import subprocess
import random


# Pan/zoom patterns. Each produces a different feel:
# - "zoom_in":    slow push into the subject
# - "zoom_out":   slow pull back, reveals context
# - "pan_left":   tracks left across frame
# - "pan_right":  tracks right across frame
# - "diag_up":    pan up-right while zooming in
PATTERNS = ["zoom_in", "zoom_out", "pan_left", "pan_right", "diag_up"]


def image_to_video_region(image_path: str, output_path: str, duration: float,
                          target_x_pct: float, target_y_pct: float,
                          start_zoom: float = 1.0, end_zoom: float = 1.6,
                          resolution: str = "1080x1920") -> str:
    """
    Ken Burns that zooms toward a SPECIFIC region of the source image.

    target_x_pct, target_y_pct: 0.0–1.0 — the region of the image to zoom into.
        e.g. (0.5, 0.15) targets the head, (0.5, 0.35) the chest, (0.5, 0.5) the
        belly, (0.5, 0.8) the legs. The skeleton references are full-body
        portraits, so these percentages let one image power many scenes.
    start_zoom, end_zoom: how far we begin and end zoomed in.

    Used to fake the "different organ zoom per scene" look of aicenturies
    explainers when only one anatomical reference image is available.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    w, h = resolution.split("x")
    fps = 24
    total_frames = max(int(duration * fps), 24)

    # Upsize the source so zoom stays sharp
    canvas_w, canvas_h = int(w) * 4, int(h) * 4

    # Animate zoom from start_zoom to end_zoom over total_frames.
    # iw,ih are the SCALED canvas dimensions inside the zoompan filter.
    # x and y are the top-left of the visible window.
    z = f"'min(zoom+{(end_zoom-start_zoom)/total_frames:.5f},{end_zoom})'"

    # Keep the target point centered as we zoom in.
    # iw/zoom is the visible width at current zoom — so the top-left is
    # (target_x_pct * iw) - (iw/zoom)/2.
    x = f"'iw*{target_x_pct} - (iw/zoom)/2'"
    y = f"'ih*{target_y_pct} - (ih/zoom)/2'"

    vf = (
        f"scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=increase,"
        f"crop={canvas_w}:{canvas_h},"
        f"zoompan=z={z}:x={x}:y={y}:d={total_frames}:s={w}x{h}:fps={fps}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-an",
        "-r", str(fps),
        output_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise Exception(f"image_to_video_region failed: {proc.stderr[-400:]}")
    return output_path


def image_to_video(image_path: str, output_path: str, duration: float,
                   pattern: str = "auto", resolution: str = "1080x1920") -> str:
    """
    Convert a still image into a smoothly animated video clip.

    pattern: one of PATTERNS, or "auto" for random selection.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    if pattern == "auto" or pattern not in PATTERNS:
        pattern = random.choice(PATTERNS)

    w, h = resolution.split("x")
    fps = 24
    total_frames = max(int(duration * fps), 24)

    # zoompan operates on a higher-res canvas to keep zoom sharp.
    # We scale the image up first, then zoompan does the motion.
    canvas_w, canvas_h = int(w) * 4, int(h) * 4

    if pattern == "zoom_in":
        z = f"'min(zoom+0.0010,1.30)'"
        x = f"'iw/2-(iw/zoom/2)'"
        y = f"'ih/2-(ih/zoom/2)'"
    elif pattern == "zoom_out":
        z = f"'if(lte(zoom,1.0),1.30,max(1.0,zoom-0.0012))'"
        x = f"'iw/2-(iw/zoom/2)'"
        y = f"'ih/2-(ih/zoom/2)'"
    elif pattern == "pan_left":
        z = "1.20"
        x = f"'(iw-iw/zoom)*(1-on/{total_frames})'"
        y = f"'ih/2-(ih/zoom/2)'"
    elif pattern == "pan_right":
        z = "1.20"
        x = f"'(iw-iw/zoom)*(on/{total_frames})'"
        y = f"'ih/2-(ih/zoom/2)'"
    else:  # diag_up
        z = f"'min(zoom+0.0008,1.25)'"
        x = f"'(iw-iw/zoom)*(on/{total_frames})'"
        y = f"'(ih-ih/zoom)*(1-on/{total_frames})'"

    vf = (
        f"scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=increase,"
        f"crop={canvas_w}:{canvas_h},"
        f"zoompan=z={z}:x={x}:y={y}:d={total_frames}:s={w}x{h}:fps={fps}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-an",
        "-r", str(fps),
        output_path,
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Fallback: simple zoom-in on smaller canvas
        cmd2 = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-vf", (
                f"scale=2160:3840:force_original_aspect_ratio=increase,"
                f"crop=2160:3840,"
                f"zoompan=z='min(zoom+0.0010,1.25)':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={total_frames}:s={w}x{h}:fps={fps}"
            ),
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an",
            "-r", str(fps),
            output_path,
        ]
        proc2 = subprocess.run(cmd2, capture_output=True, text=True)
        if proc2.returncode != 0:
            raise Exception(f"Ken Burns failed: {proc2.stderr[:200]}")

    return output_path


def extend_short_clip(clip_path: str, output_path: str, target_duration: float,
                      method: str = "pingpong") -> str:
    """
    Extend a clip that's shorter than its target duration WITHOUT introducing
    frozen frames. This is the fix for the "static image between transitions"
    problem the user reported.

    Methods:
    - "pingpong":   play forward, then reverse, then forward again. Natural motion.
    - "interpolate": motion-compensated frame interpolation. Smoother but slower.
    - "loop_fade":  loop with a short crossfade at the seam.
    """
    src_dur = _get_duration(clip_path)

    if src_dur >= target_duration:
        # Just trim
        cmd = [
            "ffmpeg", "-y", "-i", clip_path,
            "-t", str(target_duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-an",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise Exception(f"Trim failed: {proc.stderr[:200]}")
        return output_path

    if method == "interpolate":
        # Slow the clip down with motion interpolation
        speed = src_dur / target_duration
        target_fps = 24
        vf = (
            f"minterpolate=fps={target_fps}:mi_mode=mci:mc_mode=aobmc:"
            f"me_mode=bidir:vsbmc=1,"
            f"setpts={1/speed:.4f}*PTS"
        )
        cmd = [
            "ffmpeg", "-y", "-i", clip_path,
            "-vf", vf,
            "-t", str(target_duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-an",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            return output_path
        # Fall through to pingpong if minterpolate fails

    if method == "loop_fade":
        loops = int(target_duration / src_dur) + 1
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", str(loops), "-i", clip_path,
            "-t", str(target_duration),
            "-vf", "fps=24",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-an",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            return output_path
        # Fall through to pingpong

    # Default: pingpong (forward + reverse, repeat as needed)
    # This is the safest — never freezes, always has natural motion.
    return _pingpong_extend(clip_path, output_path, target_duration, src_dur)


def _pingpong_extend(clip_path: str, output_path: str,
                     target_duration: float, src_dur: float) -> str:
    """
    Build a ping-pong loop using filter_complex concat.

    The concat DEMUXER is unreliable when one of the inputs is a reversed
    clip — it can drop the reversed segment entirely. The filter_complex
    concat re-encodes from raw streams, so it handles reversed PTS cleanly.
    """
    cycle_dur = src_dur * 2  # forward + reverse
    cycles_needed = max(int(target_duration / cycle_dur) + 1, 1)

    # Build a filter graph that takes the clip N times, reverses every other,
    # then concats. Cap at 6 inputs to keep command line and graph sane.
    cycles_needed = min(cycles_needed, 3)
    total_inputs = cycles_needed * 2

    inputs = []
    for _ in range(total_inputs):
        inputs.extend(["-i", clip_path])

    filter_parts = []
    for j in range(total_inputs):
        if j % 2 == 0:
            # forward
            filter_parts.append(f"[{j}:v]fps=24,setpts=PTS-STARTPTS[v{j}]")
        else:
            # reversed
            filter_parts.append(f"[{j}:v]reverse,fps=24,setpts=PTS-STARTPTS[v{j}]")

    concat_inputs = "".join(f"[v{j}]" for j in range(total_inputs))
    filter_parts.append(
        f"{concat_inputs}concat=n={total_inputs}:v=1:a=0[outv]"
    )

    filtergraph = ";".join(filter_parts)

    cmd = (
        ["ffmpeg", "-y"] + inputs +
        ["-filter_complex", filtergraph,
         "-map", "[outv]",
         "-t", str(target_duration),
         "-c:v", "libx264", "-preset", "fast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-an", "-r", "24",
         output_path]
    )

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise Exception(f"Pingpong filter_complex failed: {proc.stderr[-400:]}")

    return output_path


def _get_duration(path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True,
        )
        return float(r.stdout.strip())
    except Exception:
        return 5.0
