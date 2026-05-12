"""
Professional subtitle engine with Whisper-based word-level timing.
- Uses Whisper to detect EXACT word timestamps from audio
- Generates ASS format with word-by-word highlight
- Perfect sync: subtitles match exactly what is spoken
"""
import os
import json
import subprocess

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "scripts")
SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")

STYLE_PRESETS = {
    "viral": {
        "font": "Arial Black", "size": 48,
        "primary_color": "&H00FFFFFF", "highlight_color": "&H0000FFFF",
        "outline_color": "&H00000000", "outline_width": 5, "shadow": 3,
        "position": "center", "margin_v": 400, "bold": True, "words_per_chunk": 2,
    },
    "classic": {
        "font": "Arial", "size": 28,
        "primary_color": "&H00FFFFFF", "highlight_color": "&H00FFFFFF",
        "outline_color": "&H00000000", "outline_width": 3, "shadow": 1,
        "position": "bottom", "margin_v": 100, "bold": False, "words_per_chunk": 8,
    },
    "bold_red": {
        "font": "Impact", "size": 52,
        "primary_color": "&H00FFFFFF", "highlight_color": "&H000000FF",
        "outline_color": "&H00000000", "outline_width": 6, "shadow": 4,
        "position": "center", "margin_v": 400, "bold": True, "words_per_chunk": 2,
    },
    "neon_green": {
        "font": "Arial Black", "size": 48,
        "primary_color": "&H00FFFFFF", "highlight_color": "&H0000FF00",
        "outline_color": "&H00000000", "outline_width": 5, "shadow": 3,
        "position": "center", "margin_v": 400, "bold": True, "words_per_chunk": 2,
    },
}


def _load_subtitle_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            settings = json.load(f)
        sub_settings = settings.get("subtitle_style", {})
        preset_name = sub_settings.get("preset", "viral")
        base = STYLE_PRESETS.get(preset_name, STYLE_PRESETS["viral"]).copy()
        for key in base:
            if key in sub_settings:
                base[key] = sub_settings[key]
        return base
    except Exception:
        return STYLE_PRESETS["viral"].copy()


def _whisper_word_timestamps(audio_path: str, original_text: str = None) -> list:
    """
    Use Whisper to get exact word-level timestamps from audio.
    If original_text is provided, uses Whisper only for timing and
    replaces transcribed words with the original text words.
    Returns list of {"word": str, "start": float, "end": float}.
    """
    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(
            audio_path,
            word_timestamps=True,
            fp16=False,
        )

        whisper_words = []
        for segment in result.get("segments", []):
            for word_info in segment.get("words", []):
                whisper_words.append({
                    "word": word_info["word"].strip(),
                    "start": word_info["start"],
                    "end": word_info["end"],
                })

        if not whisper_words:
            return []

        # If we have original text, replace Whisper's transcription with it
        # but keep the timestamps (they align to the audio)
        if original_text:
            orig_words = original_text.split()
            if len(orig_words) <= len(whisper_words):
                # Map original words to whisper timestamps proportionally
                result_words = []
                ratio = len(whisper_words) / len(orig_words)
                for i, word in enumerate(orig_words):
                    wi_start = int(i * ratio)
                    wi_end = min(int((i + 1) * ratio) - 1, len(whisper_words) - 1)
                    wi_end = max(wi_end, wi_start)
                    result_words.append({
                        "word": word,
                        "start": whisper_words[wi_start]["start"],
                        "end": whisper_words[wi_end]["end"],
                    })
                return result_words
            else:
                # More original words than whisper detected — distribute timestamps
                result_words = []
                total_dur = whisper_words[-1]["end"] - whisper_words[0]["start"]
                start = whisper_words[0]["start"]
                per_word = total_dur / len(orig_words)
                for i, word in enumerate(orig_words):
                    result_words.append({
                        "word": word,
                        "start": start + i * per_word,
                        "end": start + (i + 1) * per_word,
                    })
                return result_words

        return whisper_words
    except Exception:
        return []


def _get_audio_duration(path: str) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 10.0


def generate_ass(scenes: list, audio_results: list, video_id: int,
                 style: dict = None, audio_dir: str = None) -> str:
    """
    Generate ASS subtitles. Uses Whisper for exact timing when audio files exist.
    Falls back to calculated timing if Whisper fails.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ass_path = os.path.join(OUTPUT_DIR, f"video_{video_id}.ass")

    if style is None:
        style = _load_subtitle_settings()

    # Try Whisper-based timing first (pass scenes for original text matching)
    word_timestamps = _get_all_word_timestamps(audio_results, scenes=scenes)

    if word_timestamps:
        events = _build_events_whisper(word_timestamps, style)
    else:
        events = _build_events_calculated(scenes, audio_results, style)

    header = _build_ass_header(style)

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")

    return ass_path


def _get_all_word_timestamps(audio_results: list, scenes: list = None) -> list:
    """Get word timestamps from all scene audio files using Whisper."""
    all_words = []
    time_offset = 0.0

    # Build a lookup for original narration text per scene
    scene_text = {}
    if scenes:
        for s in scenes:
            scene_text[s["scene_number"]] = s.get("narration", "")

    for ar in sorted(audio_results, key=lambda x: x["scene_number"]):
        audio_path = ar.get("path", "")
        if not audio_path or not os.path.exists(audio_path):
            return []

        original = scene_text.get(ar["scene_number"], None)
        words = _whisper_word_timestamps(audio_path, original_text=original)
        if not words:
            return []

        # Offset timestamps for this scene
        for w in words:
            all_words.append({
                "word": w["word"],
                "start": w["start"] + time_offset,
                "end": w["end"] + time_offset,
            })

        time_offset += ar.get("duration", _get_audio_duration(audio_path))

    return all_words


def _build_events_whisper(words: list, style: dict) -> list:
    """Build ASS events from Whisper word timestamps — perfectly synced."""
    events = []
    words_per = style.get("words_per_chunk", 2)

    for i in range(0, len(words), words_per):
        chunk = words[i:i + words_per]
        chunk_start = chunk[0]["start"]
        chunk_end = chunk[-1]["end"]

        if words_per <= 3:
            # Word-by-word highlight mode
            for j, word_info in enumerate(chunk):
                parts = []
                for k, w in enumerate(chunk):
                    if k == j:
                        parts.append(f"{{\\rHighlight}}{w['word']}{{\\rDefault}}")
                    else:
                        parts.append(w["word"])
                text = " ".join(parts)
                events.append(
                    f"Dialogue: 0,{_format_ass_time(word_info['start'])},{_format_ass_time(word_info['end'])},Default,,0,0,0,,{text}"
                )
        else:
            # Sentence mode
            text = " ".join(w["word"] for w in chunk)
            events.append(
                f"Dialogue: 0,{_format_ass_time(chunk_start)},{_format_ass_time(chunk_end)},Default,,0,0,0,,{text}"
            )

    return events


def _build_events_calculated(scenes: list, audio_results: list, style: dict) -> list:
    """Fallback: build events from calculated timing (duration / word count)."""
    events = []
    words_per = style.get("words_per_chunk", 2)

    duration_map = {ar["scene_number"]: ar["duration"] for ar in audio_results}
    current_time = 0.0

    for scene in scenes:
        narration = scene["narration"]
        scene_duration = duration_map.get(scene["scene_number"], scene.get("duration_seconds", 10))
        words = narration.split()

        if not words:
            current_time += scene_duration
            continue

        time_per_word = scene_duration / len(words)

        for i in range(0, len(words), words_per):
            chunk_words = words[i:i + words_per]
            chunk_start = current_time + (i * time_per_word)

            if words_per <= 3:
                for j, word in enumerate(chunk_words):
                    word_start = chunk_start + (j * time_per_word)
                    word_end = chunk_start + ((j + 1) * time_per_word)
                    parts = []
                    for k, w in enumerate(chunk_words):
                        if k == j:
                            parts.append(f"{{\\rHighlight}}{w}{{\\rDefault}}")
                        else:
                            parts.append(w)
                    events.append(
                        f"Dialogue: 0,{_format_ass_time(word_start)},{_format_ass_time(word_end)},Default,,0,0,0,,{' '.join(parts)}"
                    )
            else:
                chunk_end = current_time + ((i + len(chunk_words)) * time_per_word)
                events.append(
                    f"Dialogue: 0,{_format_ass_time(chunk_start)},{_format_ass_time(chunk_end)},Default,,0,0,0,,{' '.join(chunk_words)}"
                )

        current_time += scene_duration

    return events


def _build_ass_header(style: dict) -> str:
    font = style.get("font", "Arial Black")
    size = style.get("size", 18)
    primary = style.get("primary_color", "&H00FFFFFF")
    highlight = style.get("highlight_color", "&H0000FFFF")
    outline_c = style.get("outline_color", "&H00000000")
    outline_w = style.get("outline_width", 3)
    shadow = style.get("shadow", 2)
    margin_v = style.get("margin_v", 400)
    bold = -1 if style.get("bold", True) else 0
    position = style.get("position", "center")
    alignment = 5
    if position == "bottom":
        alignment = 2
        margin_v = 60
    elif position == "top":
        alignment = 8
        margin_v = 60

    return f"""[Script Info]
Title: Video Factory Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{primary},{primary},{outline_c},&H80000000,{bold},0,0,0,100,100,0,0,1,{outline_w},{shadow},{alignment},40,40,{margin_v},1
Style: Highlight,{font},{size},{highlight},{highlight},{outline_c},&H80000000,{bold},0,0,0,100,100,0,0,1,{outline_w},{shadow},{alignment},40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def generate_srt(scenes: list, audio_results: list, video_id: int) -> str:
    """Legacy SRT generation for compatibility."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    srt_path = os.path.join(OUTPUT_DIR, f"video_{video_id}.srt")
    duration_map = {ar["scene_number"]: ar["duration"] for ar in audio_results}
    entries = []
    current_time = 0.0
    idx = 1
    for scene in scenes:
        narration = scene["narration"]
        dur = duration_map.get(scene["scene_number"], 10)
        words = narration.split()
        chunks = []
        chunk = []
        for word in words:
            chunk.append(word)
            if len(chunk) >= 8 and (word.endswith(('.', '!', '?', ',')) or len(chunk) >= 12):
                chunks.append(" ".join(chunk))
                chunk = []
        if chunk:
            chunks.append(" ".join(chunk))
        if not chunks:
            chunks = [narration]
        chunk_dur = dur / len(chunks)
        for text in chunks:
            entries.append(f"{idx}\n{_format_srt_time(current_time)} --> {_format_srt_time(current_time + chunk_dur)}\n{text}\n")
            idx += 1
            current_time += chunk_dur
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(entries))
    return srt_path


def generate_preview_ass(text: str, style: dict, duration: float = 8.0) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    scenes = [{"scene_number": 1, "narration": text, "duration_seconds": duration}]
    audio_results = [{"scene_number": 1, "duration": duration}]
    return generate_ass(scenes, audio_results, video_id=0, style=style)


def _format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def get_style_presets() -> dict:
    return {k: {**v, "name": k} for k, v in STYLE_PRESETS.items()}
