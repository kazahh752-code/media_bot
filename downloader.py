import logging
import os
import uuid
from pathlib import Path

import yt_dlp

logger = logging.getLogger(__name__)


def _unique_path(temp_dir: str, ext: str) -> str:
    return str(Path(temp_dir) / f"{uuid.uuid4().hex}.{ext}")


# ── Instagram ─────────────────────────────────────────────────────────────────

def download_instagram(url: str, temp_dir: str) -> str | None:
    out_path = str(Path(temp_dir) / f"{uuid.uuid4().hex}.%(ext)s")

    ydl_opts = {
        "outtmpl": out_path,
        "format": "mp4/best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        # Instagram часто требует cookies — без них работает для публичных постов
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
            )
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Find the downloaded file
            ext = info.get("ext", "mp4")
            filename = ydl.prepare_filename(info)
            # Handle merged output
            if not os.path.exists(filename):
                filename = filename.rsplit(".", 1)[0] + ".mp4"
            return filename if os.path.exists(filename) else _find_latest(temp_dir)
    except Exception as e:
        logger.error(f"Instagram download error: {e}")
        return None


# ── YouTube Video ─────────────────────────────────────────────────────────────

def download_youtube_video(url: str, temp_dir: str) -> str | None:
    out_path = str(Path(temp_dir) / f"{uuid.uuid4().hex}.%(ext)s")

    ydl_opts = {
        "outtmpl": out_path,
        # Best quality that fits within ~50MB for Telegram
        # Prefer mp4, max 720p to keep size reasonable
        "format": (
            "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]"
            "/bestvideo[height<=720]+bestaudio"
            "/best[height<=720][ext=mp4]"
            "/best[height<=720]"
            "/best"
        ),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if not os.path.exists(filename):
                filename = filename.rsplit(".", 1)[0] + ".mp4"
            return filename if os.path.exists(filename) else _find_latest(temp_dir)
    except Exception as e:
        logger.error(f"YouTube video download error: {e}")
        return None


# ── YouTube Audio ─────────────────────────────────────────────────────────────

def download_youtube_audio(url: str, temp_dir: str) -> str | None:
    out_path = str(Path(temp_dir) / f"{uuid.uuid4().hex}.%(ext)s")

    ydl_opts = {
        "outtmpl": out_path,
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # After FFmpeg conversion it becomes .mp3
            mp3_path = filename.rsplit(".", 1)[0] + ".mp3"
            return mp3_path if os.path.exists(mp3_path) else _find_latest(temp_dir, ext=".mp3")
    except Exception as e:
        logger.error(f"YouTube audio download error: {e}")
        return None


# ── Helper ────────────────────────────────────────────────────────────────────

def _find_latest(temp_dir: str, ext: str = None) -> str | None:
    """Fallback: find the most recently created file in temp_dir."""
    try:
        files = list(Path(temp_dir).iterdir())
        if ext:
            files = [f for f in files if f.suffix == ext]
        if not files:
            return None
        return str(max(files, key=lambda f: f.stat().st_mtime))
    except Exception:
        return None
