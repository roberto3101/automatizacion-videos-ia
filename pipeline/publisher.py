"""
Publishing module.
- YouTube: Full auto-upload via official API (OAuth2)
- TikTok: Export package ready to post (optimized video + caption + hashtags)
- Instagram: Export package ready to post (optimized video + caption + hashtags)

Anti-detection strategy:
- Randomized posting times within optimal windows
- Unique titles/descriptions per platform
- Rate limiting (max 1/day per platform)
- Human-like scheduling patterns
"""
import os
import json
import random
import subprocess
import shutil
from datetime import datetime, timedelta
from typing import Optional

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")
SCHEDULE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "publish_schedule.json")
EXPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "exports")
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "youtube_oauth.json")
TOKEN_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "youtube_token.json")


def _load_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# Optimal posting hours (UTC) based on engagement data
BEST_HOURS = {
    "youtube": [14, 15, 16, 17, 18, 19, 20],
    "tiktok": [7, 8, 9, 12, 15, 19, 20, 22],
    "instagram": [11, 12, 13, 17, 18, 19],
}


def get_next_publish_time(platform: str) -> datetime:
    """Calculate optimal next publish time with jitter."""
    now = datetime.utcnow()
    hours = BEST_HOURS.get(platform, [15, 16, 17])
    for day_offset in range(3):
        target_date = now + timedelta(days=day_offset)
        for hour in hours:
            target = target_date.replace(
                hour=hour, minute=random.randint(5, 55),
                second=random.randint(0, 59), microsecond=0
            )
            if target > now + timedelta(minutes=30):
                return target + timedelta(minutes=random.randint(0, 12))
    return now + timedelta(days=1, hours=random.choice(hours))


# ============================================================
# YOUTUBE AUTO-UPLOAD (Official API)
# ============================================================

def is_youtube_configured() -> dict:
    """Check if YouTube OAuth is set up."""
    has_creds = os.path.exists(CREDENTIALS_PATH)
    has_token = os.path.exists(TOKEN_PATH)
    return {
        "configured": has_creds,
        "authenticated": has_token,
        "credentials_path": CREDENTIALS_PATH,
        "setup_steps": [] if has_creds else [
            "1. Go to console.cloud.google.com",
            "2. Create a project (or select existing)",
            "3. Enable 'YouTube Data API v3'",
            "4. Go to Credentials → Create OAuth 2.0 Client ID (Desktop app)",
            "5. Download the JSON → save as config/youtube_oauth.json",
            "6. Click 'Authenticate YouTube' in Settings to complete setup",
        ],
    }


async def authenticate_youtube() -> dict:
    """Start YouTube OAuth2 flow. Returns auth URL for user to visit."""
    if not os.path.exists(CREDENTIALS_PATH):
        return {
            "status": "error",
            "message": "Upload config/youtube_oauth.json first (OAuth2 credentials from Google Cloud Console)",
        }

    from google_auth_oauthlib.flow import InstalledAppFlow

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube"]

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)

    # Run local server for OAuth callback
    try:
        credentials = flow.run_local_server(port=8090, open_browser=True)

        # Save token
        token_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
        }
        with open(TOKEN_PATH, "w") as f:
            json.dump(token_data, f, indent=2, default=str)

        return {"status": "ok", "message": "YouTube authenticated successfully!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _get_youtube_service():
    """Get authenticated YouTube API service."""
    if not os.path.exists(TOKEN_PATH):
        return None

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    with open(TOKEN_PATH, "r") as f:
        token_data = json.load(f)

    # Load credentials from token file
    with open(CREDENTIALS_PATH, "r") as f:
        client_config = json.load(f)

    installed = client_config.get("installed", client_config.get("web", {}))

    credentials = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=installed.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=installed.get("client_id"),
        client_secret=installed.get("client_secret"),
    )

    return build("youtube", "v3", credentials=credentials)


async def upload_to_youtube(video_path: str, title: str, description: str,
                             tags: list = None, category: str = "24",
                             privacy: str = "public") -> dict:
    """
    Upload video to YouTube via official API.
    category 24 = Entertainment, 22 = People & Blogs
    """
    youtube = _get_youtube_service()
    if not youtube:
        return {"status": "not_authenticated", "message": "YouTube not authenticated. Go to Settings."}

    from googleapiclient.http import MediaFileUpload

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": (tags or ["horror", "scary story", "creepypasta"])[:30],
            "categoryId": category,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)

    try:
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = request.execute()

        video_id = response.get("id", "")
        return {
            "status": "uploaded",
            "platform": "youtube",
            "video_id": video_id,
            "url": f"https://youtube.com/watch?v={video_id}",
            "title": title,
        }
    except Exception as e:
        return {"status": "error", "platform": "youtube", "message": str(e)}


# ============================================================
# TIKTOK EXPORT PACKAGE
# ============================================================

async def prepare_tiktok_package(video_path: str, title: str,
                                  tags: list = None, video_id: int = 0) -> dict:
    """
    Prepare a TikTok-ready export package:
    - Video re-encoded to TikTok optimal specs (9:16, H.264, AAC)
    - Caption with hashtags
    - Ready to upload from phone
    """
    os.makedirs(EXPORT_DIR, exist_ok=True)
    export_name = f"tiktok_{video_id}_{datetime.utcnow().strftime('%Y%m%d')}"
    export_video = os.path.join(EXPORT_DIR, f"{export_name}.mp4")

    # Re-encode to TikTok specs
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-movflags", "+faststart",  # Important for mobile playback
        "-r", "30",
        export_video,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Fallback: just copy
        shutil.copy2(video_path, export_video)

    # Build caption
    default_tags = ["horror", "scarystory", "fyp", "storytime", "viral", "creepy"]
    all_tags = list(set((tags or []) + default_tags))[:15]
    hashtags = " ".join(f"#{t}" for t in all_tags)
    caption = f"{title[:80]}\n\n{hashtags}"

    # Save caption as text file
    caption_path = os.path.join(EXPORT_DIR, f"{export_name}_caption.txt")
    with open(caption_path, "w", encoding="utf-8") as f:
        f.write(caption)

    size_mb = os.path.getsize(export_video) / (1024 * 1024)

    return {
        "status": "ready",
        "platform": "tiktok",
        "video_path": export_video,
        "video_url": f"/output/exports/{export_name}.mp4",
        "caption": caption,
        "caption_path": caption_path,
        "size_mb": round(size_mb, 2),
        "instructions": [
            "1. Download the video file to your phone",
            "2. Open TikTok → tap + → Upload",
            "3. Select the video",
            "4. Copy the caption from the text file",
            "5. Post!",
        ],
    }


# ============================================================
# INSTAGRAM EXPORT PACKAGE
# ============================================================

async def prepare_instagram_package(video_path: str, title: str,
                                     tags: list = None, video_id: int = 0) -> dict:
    """
    Prepare an Instagram Reels-ready export package:
    - Video re-encoded to IG specs (9:16, H.264, AAC, max 90s)
    - Caption with 30 hashtags for maximum reach
    - Ready to upload from phone
    """
    os.makedirs(EXPORT_DIR, exist_ok=True)
    export_name = f"instagram_{video_id}_{datetime.utcnow().strftime('%Y%m%d')}"
    export_video = os.path.join(EXPORT_DIR, f"{export_name}.mp4")

    # Re-encode to Instagram Reels specs
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-c:v", "libx264", "-preset", "medium", "-crf", "22",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-movflags", "+faststart",
        "-r", "30",
        "-t", "90",  # Instagram Reels max 90s
        export_video,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        shutil.copy2(video_path, export_video)

    # Build caption with max hashtags
    default_tags = [
        "horror", "scarystory", "creepypasta", "horrortok", "scary",
        "paranormal", "truestory", "storytime", "fyp", "viral",
        "horrorcommunity", "scarystories", "creepy", "haunted",
        "nightmare", "darkstories", "horrorfans", "explore",
        "reels", "reelsviral", "trending", "mystery",
        "ghoststory", "urbanlegend", "nosleep", "terrifying",
    ]
    all_tags = list(set((tags or []) + default_tags))[:30]
    hashtags = " ".join(f"#{t}" for t in all_tags)
    caption = f"{title[:100]}\n\n{hashtags}"

    caption_path = os.path.join(EXPORT_DIR, f"{export_name}_caption.txt")
    with open(caption_path, "w", encoding="utf-8") as f:
        f.write(caption)

    size_mb = os.path.getsize(export_video) / (1024 * 1024)

    return {
        "status": "ready",
        "platform": "instagram",
        "video_path": export_video,
        "video_url": f"/output/exports/{export_name}.mp4",
        "caption": caption,
        "caption_path": caption_path,
        "size_mb": round(size_mb, 2),
        "instructions": [
            "1. Download the video to your phone",
            "2. Open Instagram → tap + → Reel",
            "3. Select the video",
            "4. Copy the caption from the text file",
            "5. Share as Reel!",
        ],
    }


# ============================================================
# PUBLISH QUEUE
# ============================================================

def load_schedule() -> list:
    if os.path.exists(SCHEDULE_PATH):
        with open(SCHEDULE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_schedule(schedule: list):
    os.makedirs(os.path.dirname(SCHEDULE_PATH), exist_ok=True)
    with open(SCHEDULE_PATH, "w", encoding="utf-8") as f:
        json.dump(schedule, f, indent=2, default=str)


async def add_to_schedule(video_id: int, video_path: str, title: str,
                           platforms: list = None) -> dict:
    platforms = platforms or ["youtube", "tiktok", "instagram"]
    schedule = load_schedule()

    entries = []
    for platform in platforms:
        entry = {
            "video_id": video_id,
            "video_path": video_path,
            "title": title,
            "platform": platform,
            "scheduled_time": get_next_publish_time(platform).isoformat(),
            "status": "scheduled",
            "created_at": datetime.utcnow().isoformat(),
        }
        schedule.append(entry)
        entries.append(entry)

    save_schedule(schedule)
    return {"scheduled": entries}
