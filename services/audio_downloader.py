"""
Audio downloader — uses yt-dlp to extract audio from social media video URLs.
Runs synchronously; call from a threadpool.
"""

import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 24 * 1024 * 1024  # 24 MB — Groq Whisper limit is 25 MB


def download_audio(url: str) -> tuple[bytes, str] | None:
    """
    Download audio from a social media URL using yt-dlp.
    Returns (audio_bytes, filename) or None if download fails.
    """
    if not url or not url.startswith("http"):
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        out_template = os.path.join(tmpdir, "audio.%(ext)s")
        try:
            subprocess.run(
                [
                    "yt-dlp",
                    "-x",
                    "--audio-format", "m4a",
                    "--audio-quality", "5",
                    "-o", out_template,
                    "--no-playlist",
                    "--quiet",
                    "--no-warnings",
                    "--socket-timeout", "30",
                    url,
                ],
                capture_output=True,
                timeout=90,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug("yt-dlp failed for %s: %s", url, e)
            return None

        for fname in os.listdir(tmpdir):
            fpath = os.path.join(tmpdir, fname)
            if not os.path.isfile(fpath):
                continue
            size = os.path.getsize(fpath)
            if 0 < size < MAX_AUDIO_BYTES:
                with open(fpath, "rb") as f:
                    return f.read(), fname

    return None
