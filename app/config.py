import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _csv_ints(value):
    result = set()
    for item in value.split(","):
        item = item.strip()
        if item:
            try:
                result.add(int(item))
            except ValueError:
                pass
    return result

@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    database_url: str = os.getenv("DATABASE_URL", "")
    admin_ids: set = None
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "49"))
    max_height: int = int(os.getenv("MAX_HEIGHT", "1080"))
    max_concurrent: int = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "2"))
    cooldown_seconds: int = int(os.getenv("USER_COOLDOWN_SECONDS", "15"))
    download_dir: str = os.getenv("DOWNLOAD_DIR", "/tmp/vidora")
    allowed_domains: tuple = tuple(
        x.strip().lower()
        for x in os.getenv("ALLOWED_DOMAINS", "").split(",")
        if x.strip()
    )
    local_api_url: str = os.getenv("TELEGRAM_LOCAL_API_URL", "")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

settings = Settings(admin_ids=_csv_ints(os.getenv("ADMIN_IDS", "")))

if not settings.bot_token:
    raise RuntimeError("BOT_TOKEN is missing.")
if not settings.database_url:
    raise RuntimeError("DATABASE_URL is missing.")
