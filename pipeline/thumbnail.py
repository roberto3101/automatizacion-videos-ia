"""
Professional thumbnail generator.
Extracts the most visually interesting frame from the video,
applies color grading, vignette, and bold text overlay.
"""
import subprocess
import os
import re

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "thumbnails")

STYLES = {
    "horror": {"text_color": "white", "outline": "red", "brightness": -0.15, "contrast": 1.4, "saturation": 0.8},
    "mystery": {"text_color": "white", "outline": "#FFD700", "brightness": -0.1, "contrast": 1.3, "saturation": 0.9},
    "calm": {"text_color": "white", "outline": "#00FF88", "brightness": 0, "contrast": 1.1, "saturation": 1.1},
    "epic": {"text_color": "white", "outline": "#FF6600", "brightness": -0.05, "contrast": 1.3, "saturation": 1.2},
}


async def generate_thumbnail(title: str, video_path: str = None,
                              output_filename: str = "thumb.jpg",
                              style: str = "horror") -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    s = STYLES.get(style, STYLES["horror"])

    # Format title: max 2 lines, uppercase, clean
    display_text = _format_title(title)

    if video_path and os.path.exists(video_path):
        # Extract frame at 30% of video (usually the most interesting part)
        duration = _get_duration(video_path)
        seek_time = max(0.5, duration * 0.3)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(seek_time),
            "-i", video_path,
            "-vf", (
                f"scale=1280:720:force_original_aspect_ratio=decrease,"
                f"pad=1280:720:(ow-iw)/2:(oh-ih)/2:black,"
                # Color grading for dramatic look
                f"eq=brightness={s['brightness']}:contrast={s['contrast']}:saturation={s['saturation']},"
                # Vignette for cinematic feel
                f"vignette=PI/3.5,"
                # Dark gradient overlay at bottom for text readability
                f"drawbox=x=0:y=ih*0.55:w=iw:h=ih*0.45:color=black@0.6:t=fill,"
                # Main title text — large, bold, centered
                f"drawtext=text='{display_text}':"
                f"fontcolor={s['text_color']}:fontsize=62:"
                f"borderw=4:bordercolor={s['outline']}:"
                f"x=(w-text_w)/2:y=h*0.62:"
                f"shadowcolor=black@0.8:shadowx=3:shadowy=3"
            ),
            "-frames:v", "1",
            "-q:v", "1",  # Highest JPEG quality
            output_path,
        ]
    else:
        # No video: dark background with text
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=0x080808:s=1280x720:d=1",
            "-vf", (
                f"vignette=PI/3,"
                f"drawbox=x=0:y=ih*0.5:w=iw:h=ih*0.5:color=black@0.5:t=fill,"
                f"drawtext=text='{display_text}':"
                f"fontcolor={s['text_color']}:fontsize=68:"
                f"borderw=5:bordercolor={s['outline']}:"
                f"x=(w-text_w)/2:y=(h-text_h)/2:"
                f"shadowcolor=black@0.9:shadowx=4:shadowy=4"
            ),
            "-frames:v", "1",
            "-q:v", "1",
            output_path,
        ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise Exception(f"Thumbnail error: {proc.stderr[:200]}")

    return output_path


def _format_title(title: str) -> str:
    """Format title for thumbnail: uppercase, max 2 lines, clean chars."""
    title = title.upper()
    # Remove chars that break FFmpeg
    title = re.sub(r"[^A-Z0-9 \-!?.]", "", title).strip()
    if not title:
        title = "WATCH THIS"

    words = title.split()
    # Split into 2 lines max
    mid = len(words) // 2
    if len(words) > 4:
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
        return f"{line1}\\n{line2}"
    return title


def _get_duration(path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True,
        )
        return float(r.stdout.strip())
    except Exception:
        return 5.0
