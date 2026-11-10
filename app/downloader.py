import asyncio
import os
import socket
import ipaddress
from urllib.parse import urlparse
from pathlib import Path
import yt_dlp

from .config import settings

_download_slots = asyncio.Semaphore(
    max(1, settings.max_concurrent)
)

def validate_url(raw_url):
    url = raw_url.strip()
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Noto‘g‘ri havola.")

    host = parsed.hostname.lower().rstrip(".")

    try:
        addresses = socket.getaddrinfo(host, None)
        for item in addresses:
            ip = ipaddress.ip_address(item[4][0])
            if not ip.is_global:
                raise ValueError("Bu manzilga ruxsat yo‘q.")
    except socket.gaierror:
        raise ValueError("Sayt topilmadi.")

    if settings.allowed_domains:
        if not any(
            host == d or host.endswith("." + d)
            for d in settings.allowed_domains
        ):
            raise ValueError("Bu platformaga ruxsat yo‘q.")

    return url

def _download_sync(url, mode):
    os.makedirs(settings.download_dir, exist_ok=True)

    max_bytes = settings.max_upload_mb * 1024 * 1024

    output = str(
        Path(settings.download_dir) /
        "%(id)s_%(title).80s.%(ext)s"
    )

    if mode == "audio":
        fmt = "bestaudio/best"
        postprocessors = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192"
        }]
    else:
        fmt = (
            f"best[height<={settings.max_height}]"
            f"/best"
        )
        postprocessors = []

    options = {
        "format": fmt,
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "postprocessors": postprocessors,
        "socket_timeout": 20,
        "retries": 2
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = Path(ydl.prepare_filename(info))

        if mode == "audio":
            filename = filename.with_suffix(".mp3")

        if not filename.exists():
            files = sorted(
                Path(settings.download_dir).glob(
                    f"{info.get('id')}*"
                ),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            if not files:
                raise RuntimeError("Fayl topilmadi.")
            filename = files[0]

        if filename.stat().st_size > max_bytes:
            filename.unlink(missing_ok=True)
            raise ValueError("Fayl hajmi limitdan katta.")

        return {
            "path": str(filename),
            "title": info.get("title", "Media"),
            "duration": info.get("duration"),
            "height": info.get("height"),
            "host": urlparse(url).hostname,
            "size": filename.stat().st_size
        }

async def download_media(url, mode):
    url = validate_url(url)

    async with _download_slots:
        return await asyncio.to_thread(
            _download_sync, url, mode
        )
