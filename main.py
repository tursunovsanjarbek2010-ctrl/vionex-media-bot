import asyncio
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

from .config import settings
from . import db
from .downloader import download_media

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("vidora")
dp = Dispatcher()
last_request: dict[int, float] = {}
pending_urls: dict[int, str] = {}
URL_RE = re.compile(r"https?://\S+", re.I)

def menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🎬 Video yuklash", callback_data="mode:video")
    kb.button(text="🎵 MP3 yuklash", callback_data="mode:audio")
    kb.adjust(2)
    return kb.as_markup()

@dp.message(CommandStart())
async def start(message: Message):
    await db.touch_user(message.from_user)
    await message.answer(
        "👋 <b>VIDORA DOWNLOADER</b> ga xush kelibsiz!\\n\\n"
        "Ommaviy va ruxsat etilgan havolani yuboring. Men mavjud media sifatini tekshirib, "
        "video yoki MP3 ko‘rinishida tayyorlayman.\\n\\n"
        "⚠️ 1080p manbada mavjud bo‘lsa va fayl hajmi limitga sig‘sa yuboriladi. "
        "Mualliflik huquqi va platforma qoidalariga rioya qiling.",
        reply_markup=menu(),
        parse_mode="HTML"
    )

@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "<b>Foydalanish:</b>\\n"
        "1. Video yoki audio rejimini tanlang.\\n"
        "2. Ommaviy havolani yuboring.\\n"
        "3. Bot mavjud sifatni yuklab, faylni yuboradi.\\n\\n"
        "/stats — administrator statistikasi (adminlar uchun).\\n"
        "Bot DRM, yopiq profil, pullik yoki kirish cheklovlarini chetlab o‘tmaydi.",
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("mode:"))
async def choose_mode(call: CallbackQuery):
    mode = call.data.split(":", 1)[1]
    if mode not in ("video", "audio"):
        await call.answer("Noto‘g‘ri tanlov", show_alert=True)
        return
    await call.answer()
    await call.message.answer(
        "🎬 Video uchun havolani yuboring." if mode == "video"
        else "🎵 Audio uchun havolani yuboring."
    )
    # Store selected mode for the next URL.
    user_modes[call.from_user.id] = mode

user_modes: dict[int, str] = {}

@dp.message(Command("stats"))
async def stats(message: Message):
    if message.from_user.id not in settings.admin_ids:
        await message.answer("Bu buyruq faqat administrator uchun.")
        return
    users, total, success = await db.get_stats()
    await message.answer(
        f"📊 <b>VIDORA statistikasi</b>\\n"
        f"Foydalanuvchilar: <b>{users}</b>\\n"
        f"Jami so‘rovlar: <b>{total}</b>\\n"
        f"Muvaffaqiyatli: <b>{success}</b>",
        parse_mode="HTML"
    )

@dp.message(F.text)
async def handle_text(message: Message):
    user = message.from_user
    await db.touch_user(user)
    text = (message.text or "").strip()
    match = URL_RE.search(text)
    if not match:
        await message.answer("Havola yuboring yoki pastdagi menyudan rejimni tanlang.", reply_markup=menu())
        return

    now = time.monotonic()
    previous = last_request.get(user.id, 0)
    wait = settings.cooldown_seconds - (now - previous)
    if wait > 0:
        await message.answer(f"Iltimos, {int(wait) + 1} soniyadan keyin qayta urinib ko‘ring.")
        return
    last_request[user.id] = now

    url = match.group(0).rstrip(").,!?]}")
    mode = user_modes.get(user.id, "video")
    status = await message.answer("⏳ Havola tekshirilmoqda va media tayyorlanmoqda...")
    host = urlparse(url).hostname or "unknown"
    path = None
    try:
        result = await download_media(url, mode)
        path = Path(result["path"])
        caption = (
            f"✅ <b>Tayyor!</b>\\n"
            f"📌 {escape_html(result['title'][:180])}\\n"
            f"📦 {result['size'] / (1024*1024):.1f} MB"
        )
        if mode == "video" and result.get("height"):
            caption += f"\\n🎞 {result['height']}p"
        file = FSInputFile(path)
        if mode == "audio":
            await message.answer_audio(file, caption=caption, parse_mode="HTML", title=result["title"][:64])
        else:
            await message.answer_video(file, caption=caption, parse_mode="HTML", supports_streaming=True)
        await db.log_download(user.id, host, mode, "success")
        await status.delete()
    except (ValueError, RuntimeError) as exc:
        await db.log_download(user.id, host, mode, "failed")
        await status.edit_text(f"❌ {escape_html(str(exc))}")
    except (TelegramBadRequest, TelegramNetworkError) as exc:
        await db.log_download(user.id, host, mode, "failed")
        log.warning("Telegram upload error: %s", exc)
        await status.edit_text(
            f"❌ Telegram faylni qabul qilmadi. Fayl {settings.max_upload_mb} MB limitidan kichikligini "
            "tekshiring yoki administratorga murojaat qiling."
        )
    except Exception:
        await db.log_download(user.id, host, mode, "failed")
        log.exception("Unhandled download failure")
        await status.edit_text("❌ Yuklashda xatolik yuz berdi. Boshqa havola bilan urinib ko‘ring.")
    finally:
        if path and path.exists():
            try:
                path.unlink()
            except OSError:
                log.warning("Could not delete temporary file: %s", path)

def escape_html(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

async def main():
    os.makedirs(settings.download_dir, exist_ok=True)
    await db.connect()
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(settings.local_api_url)
    ) if settings.local_api_url else AiohttpSession()
    bot = Bot(token=settings.bot_token, session=session)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("VIDORA DOWNLOADER started")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
