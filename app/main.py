import asyncio
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .config import settings
from . import db
from .downloader import download_media

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("vionex")

dp = Dispatcher()
last_request = {}
user_modes = {}

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
        "👑 <b>VIONEX MEDIA</b>\n\n"
        "Video yoki musiqa havolasini yuboring.",
        reply_markup=menu(),
        parse_mode="HTML"
    )

@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "Havolani yuboring va video yoki audio rejimini tanlang."
    )

@dp.callback_query(F.data.startswith("mode:"))
async def choose_mode(call: CallbackQuery):
    mode = call.data.split(":")[1]
    if mode not in ("video", "audio"):
        await call.answer("Noto‘g‘ri tanlov")
        return

    user_modes[call.from_user.id] = mode
    await call.answer("Tanlandi")
    await call.message.answer("Endi media havolasini yuboring.")

@dp.message(Command("stats"))
async def stats(message: Message):
    if message.from_user.id not in settings.admin_ids:
        return

    users, total, success = await db.get_stats()
    await message.answer(
        f"Foydalanuvchilar: {users}\n"
        f"Jami yuklashlar: {total}\n"
        f"Muvaffaqiyatli: {success}"
    )

@dp.message(F.text)
async def handle_text(message: Message):
    await db.touch_user(message.from_user)

    match = re.search(r"https?://\S+", message.text or "")
    if not match:
        await message.answer("Iltimos, havola yuboring.", reply_markup=menu())
        return

    uid = message.from_user.id
    now = time.monotonic()
    wait = settings.cooldown_seconds - (now - last_request.get(uid, 0))

    if wait > 0:
        await message.answer(f"{int(wait)+1} soniya kuting.")
        return

    last_request[uid] = now
    url = match.group(0).rstrip(").,!?]}")
    mode = user_modes.get(uid, "video")
    host = urlparse(url).hostname or "unknown"

    status = await message.answer("⏳ Media tayyorlanmoqda...")
    path = None

    try:
        result = await download_media(url, mode)
        path = Path(result["path"])

        caption = (
            f"✅ <b>{escape(result['title'][:150])}</b>\n"
            f"📦 {result['size'] / 1048576:.1f} MB"
        )

        if mode == "audio":
            await message.answer_audio(
                FSInputFile(path),
                caption=caption,
                parse_mode="HTML"
            )
        else:
            await message.answer_video(
                FSInputFile(path),
                caption=caption,
                parse_mode="HTML",
                supports_streaming=True
            )

        await db.log_download(uid, host, mode, "success")
        await status.delete()

    except Exception as exc:
        log.exception("Download error")
        await db.log_download(uid, host, mode, "failed")
        await status.edit_text(f"❌ Xatolik: {escape(str(exc))[:300]}")

    finally:
        if path and path.exists():
            path.unlink(missing_ok=True)

async def main():
    os.makedirs(settings.download_dir, exist_ok=True)
    await db.connect()

    bot = Bot(token=settings.bot_token)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
