"""
Thumbnail downloader — uses yt-dlp to extract a thumbnail image from a video URL.
Returns raw JPEG bytes for use with Gemini Vision API.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_THUMB_BYTES = 5 * 1024 * 1024  # 5 MB


def download_thumbnail(url: str) -> tuple[bytes, str] | None:
    """
    Download a video thumbnail via yt-dlp --write-thumbnail.
    Returns (image_bytes, filename) or None on failure.
    """
    if not url or not url.startswith("http"):
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        out_template = os.path.join(tmpdir, "thumb")
        try:
            subprocess.run(
                [
                    "yt-dlp",
                    "--skip-download",
                    "--write-thumbnail",
                    "--convert-thumbnails", "jpg",
                    "-o", out_template,
                    "--no-playlist",
                    "--quiet",
                    "--no-warnings",
                    "--socket-timeout", "20",
                    url,
                ],
                capture_output=True,
                timeout=45,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug("yt-dlp thumbnail failed for %s: %s", url, e)
            return None

        for fname in os.listdir(tmpdir):
            fpath = os.path.join(tmpdir, fname)
            ext = Path(fpath).suffix.lower()
            if os.path.isfile(fpath) and ext in IMAGE_EXTS:
                size = os.path.getsize(fpath)
                if 0 < size < MAX_THUMB_BYTES:
                    with open(fpath, "rb") as f:
                        return f.read(), fname

    return None
