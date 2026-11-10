import asyncio
import os
import re
import socket
import ipaddress
from urllib.parse import urlparse
from pathlib import Path
import yt_dlp
from .config import settings

# Keep concurrency bounded so a public bot cannot exhaust the VPS.
_download_slots = asyncio.Semaphore(max(1, settings.max_concurrent))

def validate_url(raw_url: str) -> str:
    url = raw_url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Iltimos, http yoki https bilan boshlanadigan to‘g‘ri havola yuboring.")

    host = parsed.hostname.lower().rstrip(".")
    if host in ("localhost",) or host.endswith(".localhost"):
        raise ValueError("Mahalliy manzillarga ruxsat berilmaydi.")

    # Prevent common SSRF targets. yt-dlp may make follow-up requests, so use
    # a network-restricted VPS/container as an additional security boundary.
    try:
        addresses = socket.getaddrinfo(host, None)
        for item in addresses:
            ip = ipaddress.ip_address(item[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError("Ichki yoki mahalliy manzillarga ruxsat berilmaydi.")
    except socket.gaierror:
        raise ValueError("Sayt manzili aniqlanmadi.")

    if settings.allowed_domains:
        allowed = any(host == d or host.endswith("." + d) for d in settings.allowed_domains)
        if not allowed:
            raise ValueError("Bu sayt hozircha ruxsat etilgan platformalar ro‘yxatida yo‘q.")
    return url

def _download_sync(url: str, mode: str) -> dict:
    os.makedirs(settings.download_dir, exist_ok=True)
    outtmpl = str(Path(settings.download_dir) / "%(id)s_%(title).80s.%(ext)s")
    max_bytes = settings.max_upload_mb * 1024 * 1024

    if mode == "audio":
        fmt = "bestaudio/best"
        postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    else:
        # Prefer a single-file rendition when possible; otherwise merge video+audio.
        # Height is capped by MAX_HEIGHT, default 1080p.
        fmt = f"best[height<={settings.max_height}][filesize<={max_bytes}]/best[height<={settings.max_height}]/best"
        postprocessors = []

    opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "windowsfilenames": True,
        "merge_output_format": "mp4",
        "postprocessors": postprocessors,
        "max_filesize": max_bytes,
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 2,
        "overwrites": False,
        "ignoreerrors": False,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if not info:
            raise RuntimeError("Media topilmadi.")
        filename = ydl.prepare_filename(info)
        if mode == "audio":
            filename = str(Path(filename).with_suffix(".mp3"))
        else:
            candidate = Path(filename)
            if not candidate.exists():
                mp4_candidate = candidate.with_suffix(".mp4")
                if mp4_candidate.exists():
                    filename = str(mp4_candidate)
        path = Path(filename)
        if not path.exists():
            # yt-dlp may alter extension after merge; identify newest matching file.
            matches = sorted(Path(settings.download_dir).glob(f"{info.get('id','')}*"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not matches:
                raise RuntimeError("Yuklangan fayl topilmadi.")
            path = matches[0]
        if path.stat().st_size > max_bytes:
            path.unlink(missing_ok=True)
            raise ValueError(f"Fayl {settings.max_upload_mb} MB limitidan katta.")
        return {
            "path": str(path),
            "title": info.get("title") or "Nomsiz media",
            "duration": info.get("duration"),
            "height": info.get("height"),
            "host": urlparse(url).hostname or "unknown",
            "size": path.stat().st_size,
        }

async def download_media(url: str, mode: str) -> dict:
    url = validate_url(url)
    async with _download_slots:
        return await asyncio.to_thread(_download_sync, url, mode)
