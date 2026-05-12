"""
Context module for autopilot and production.
Handles text and image inputs with validation.
Images are validated for format, size, and dimensions before being used.
"""
import os
import subprocess
import base64
from typing import Optional

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "uploads")

# Validation limits
MAX_IMAGE_SIZE_MB = 10
MAX_IMAGE_DIMENSION = 4096
ALLOWED_IMAGE_FORMATS = {"png", "jpg", "jpeg", "webp", "gif", "bmp"}
MAX_TEXT_LENGTH = 5000
MAX_IMAGES = 5
MAX_TEXTS = 5


class ContextValidationError(Exception):
    pass


def validate_image(file_path: str) -> dict:
    """
    Validate an uploaded image file.
    Returns image info if valid, raises ContextValidationError if not.
    """
    if not os.path.exists(file_path):
        raise ContextValidationError(f"File not found: {file_path}")

    # Check file size
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb > MAX_IMAGE_SIZE_MB:
        raise ContextValidationError(
            f"Image too large: {size_mb:.1f}MB (max {MAX_IMAGE_SIZE_MB}MB)"
        )

    # Check extension
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    if ext not in ALLOWED_IMAGE_FORMATS:
        raise ContextValidationError(
            f"Invalid format: .{ext} (allowed: {', '.join(ALLOWED_IMAGE_FORMATS)})"
        )

    # Get dimensions with ffprobe
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", file_path],
            capture_output=True, text=True,
        )
        if result.stdout.strip():
            parts = result.stdout.strip().split(",")
            width = int(parts[0])
            height = int(parts[1])
            if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                raise ContextValidationError(
                    f"Image too large: {width}x{height} (max {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION})"
                )
        else:
            width, height = 0, 0
    except (subprocess.SubprocessError, ValueError, IndexError):
        width, height = 0, 0

    return {
        "path": file_path,
        "size_mb": round(size_mb, 2),
        "width": width,
        "height": height,
        "format": ext,
    }


def validate_text(text: str, label: str = "text") -> str:
    """Validate a context text input."""
    if not text or not text.strip():
        raise ContextValidationError(f"{label} is empty")
    text = text.strip()
    if len(text) > MAX_TEXT_LENGTH:
        raise ContextValidationError(
            f"{label} too long: {len(text)} chars (max {MAX_TEXT_LENGTH})"
        )
    return text


def validate_context(texts: list, image_paths: list) -> dict:
    """
    Validate a full context payload.
    Returns cleaned context dict or raises ContextValidationError.
    """
    errors = []

    # Validate texts
    if len(texts) > MAX_TEXTS:
        errors.append(f"Too many texts: {len(texts)} (max {MAX_TEXTS})")
    validated_texts = []
    for i, t in enumerate(texts[:MAX_TEXTS]):
        try:
            validated_texts.append(validate_text(t, f"Text {i+1}"))
        except ContextValidationError as e:
            errors.append(str(e))

    # Validate images
    if len(image_paths) > MAX_IMAGES:
        errors.append(f"Too many images: {len(image_paths)} (max {MAX_IMAGES})")
    validated_images = []
    for i, path in enumerate(image_paths[:MAX_IMAGES]):
        try:
            info = validate_image(path)
            validated_images.append(info)
        except ContextValidationError as e:
            errors.append(f"Image {i+1}: {str(e)}")

    if errors:
        raise ContextValidationError("Validation errors:\n" + "\n".join(errors))

    return {
        "texts": validated_texts,
        "images": validated_images,
    }


def build_context_prompt(texts: list, image_count: int = 0) -> str:
    """
    Build a context string to prepend to the script generation prompt.
    """
    parts = []
    if texts:
        parts.append("CONTEXT PROVIDED BY USER:")
        for i, t in enumerate(texts):
            parts.append(f"--- Text {i+1} ---")
            parts.append(t)
    if image_count > 0:
        parts.append(f"\n[{image_count} reference image(s) provided — use them as visual inspiration for the scenes]")

    return "\n".join(parts)


def image_to_data_url(file_path: str) -> str:
    """Convert an image file to a base64 data URL for API usage."""
    ext = file_path.rsplit(".", 1)[-1].lower()
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp"}
    mime = mime_map.get(ext, "image/jpeg")

    with open(file_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime};base64,{data}"
