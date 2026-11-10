# VIDORA DOWNLOADER

Public Telegram downloader bot starter with a production-oriented Docker setup.

## What it does
- Accepts supported public video URLs and extracts media using `yt-dlp`.
- Offers the best available quality up to 1080p by default (configurable).
- Extracts audio as MP3 when FFmpeg is installed.
- Shows download progress, limits concurrent jobs, enforces per-user cooldowns and file-size limits.
- Stores basic user and download statistics in PostgreSQL.
- Includes admin statistics and broadcast-ready structure (broadcast is intentionally not implemented).
- Supports public links only. It does not bypass DRM, paywalls, private accounts, login walls, or access controls.

## Important platform limits
Telegram's standard Bot API has a bot upload limit that can be lower than large source videos. This project defaults to a conservative 49 MB upload cap. For larger uploads, deploy an official Telegram Local Bot API server and configure `TELEGRAM_LOCAL_API_URL`; do not assume a normal Bot API token can upload multi-gigabyte files.
1080p is not guaranteed: the source must actually provide that rendition, and the selected video must fit Telegram's configured upload limit. Some services may block downloads or change their policies/API.

Only download media you own, have permission to download, or that is otherwise legally available for downloading. Respect platform terms and copyright.

## Deploy (VPS)
1. Install Docker Engine and Docker Compose plugin on your VPS.
2. Copy `.env.example` to `.env`.
3. Set `BOT_TOKEN`, `ADMIN_IDS`, and a strong `POSTGRES_PASSWORD`.
4. Run:
   ```bash
   docker compose up -d --build
   docker compose logs -f bot
   ```
5. Open the bot in Telegram and send `/start`.

## Configuration
- `BOT_TOKEN`: token from @BotFather.
- `ADMIN_IDS`: comma-separated Telegram numeric IDs.
- `MAX_UPLOAD_MB`: max upload size (default 49).
- `MAX_HEIGHT`: maximum video height (default 1080; set 2160 for 4K where available).
- `MAX_CONCURRENT_DOWNLOADS`: global concurrent download limit.
- `USER_COOLDOWN_SECONDS`: per-user cooldown.
- `DOWNLOAD_DIR`: temporary media directory.
- `ALLOWED_DOMAINS`: optional comma-separated host allowlist. Empty means yt-dlp-supported public URLs are accepted.
- `TELEGRAM_LOCAL_API_URL`: optional local Bot API endpoint, e.g. `http://telegram-bot-api:8081`.

## Security / operations
- Keep `.env` private; never commit bot tokens or database passwords.
- Put the bot behind a VPS firewall; expose only services you actually need.
- Add backups for PostgreSQL before production use.
- Monitor disk usage. Temporary files are deleted after upload.
- For public launch, configure a domain allowlist if you want a narrow service scope.
- This code is a solid starter, not a guarantee that every site will work indefinitely. `yt-dlp` site extractors change frequently; rebuild/update the image regularly.
