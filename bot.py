import asyncio
import hashlib
import logging
import os
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import uvicorn
import yt_dlp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, Message, Update
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request

BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ALLOWED_USERS = {
    int(user_id.strip())
    for user_id in os.getenv("ALLOWED_USERS", "").split(",")
    if user_id.strip().isdigit()
}
RENDER_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
PORT = int(os.getenv("PORT", "10000"))
WEBHOOK_PATH = "/telegram"
WEBHOOK_SECRET = hashlib.sha256(BOT_TOKEN.encode()).hexdigest()[:32] if BOT_TOKEN else ""

SUPPORTED_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:"
    r"instagram\.com/(?:reel|reels|p|tv)/[A-Za-z0-9_-]+[^\s]*"
    r"|tiktok\.com/[^\s]+"
    r"|vm\.tiktok\.com/[^\s]+"
    r"|vt\.tiktok\.com/[^\s]+"
    r"|x\.com/[^\s]+/status/\d+[^\s]*"
    r"|twitter\.com/[^\s]+/status/\d+[^\s]*"
    r")",
    re.IGNORECASE,
)

MAX_VIDEO_SIZE_MB = 49
MAX_VIDEO_SIZE_BYTES = MAX_VIDEO_SIZE_MB * 1024 * 1024

router = Router()
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dispatcher = Dispatcher()
dispatcher.include_router(router)


def is_allowed(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in ALLOWED_USERS)


def extract_supported_url(text: str) -> str | None:
    match = SUPPORTED_URL_PATTERN.search(text)
    return match.group(0).rstrip(").,]}>\"'") if match else None


def get_platform_name(url: str) -> str:
    url_lower = url.lower()
    if "instagram.com" in url_lower:
        return "Instagram"
    if "tiktok.com" in url_lower:
        return "TikTok"
    if "x.com" in url_lower or "twitter.com" in url_lower:
        return "X"
    return "Media"


def make_clean_filename(platform: str) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_platform = {"Instagram": "Instagram", "TikTok": "TikTok", "X": "X"}.get(platform, "Video")
    return f"Nekorin_{safe_platform}_{timestamp}.mp4"


def download_video(url: str, job_dir: Path) -> Path:
    ydl_options = {
        "format": "bestvideo[ext=mp4][filesize<45M]+bestaudio[ext=m4a]/best[ext=mp4][filesize<45M]/best[filesize<45M]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(job_dir / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "overwrites": True,
    }

    with yt_dlp.YoutubeDL(ydl_options) as ydl:
        info = ydl.extract_info(url, download=True)
        for item in info.get("requested_downloads") or []:
            filepath = item.get("filepath")
            if filepath and Path(filepath).exists():
                return Path(filepath)

        prepared = Path(ydl.prepare_filename(info))
        if prepared.exists():
            return prepared

    video_files = [
        file for file in job_dir.iterdir()
        if file.is_file() and file.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}
    ]
    if not video_files:
        raise FileNotFoundError("لم يتم العثور على الفيديو بعد التنزيل.")
    return max(video_files, key=lambda file: file.stat().st_size)


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    if not is_allowed(message):
        await message.answer("🔒 هذا البوت خاص.")
        return

    await message.answer(
        "🌸 <b>هلا بك في Neko Downloader Bot</b> 🐾\n\n"
        "أنا <b>نيكورين</b>، مهمتي أنزّل لك الفيديوهات بسرعة ✨\n\n"
        "🎬 <b>المنصات المدعومة:</b>\n"
        "📸 Instagram\n🎵 TikTok\n𝕏 X / Twitter\n\n"
        "📎 فقط طرش رابط الفيديو، والباقي عليّ 😎",
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text)
async def download_handler(message: Message, bot: Bot) -> None:
    if not is_allowed(message):
        await message.answer("🔒 هذا البوت خاص.")
        return

    url = extract_supported_url(message.text or "")
    if not url:
        await message.answer("❌ طرش رابط من Instagram أو TikTok أو X / Twitter.")
        return

    platform = get_platform_name(url)
    status_message = await message.answer(
        f"🐾 <b>نيكورين تحمل الفيديو...</b>\n\n📥 المصدر: {platform}\n⏳ باقي شوي بس ✨",
        parse_mode=ParseMode.HTML,
    )

    job_dir = DOWNLOADS_DIR / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
        video_path = await asyncio.to_thread(download_video, url, job_dir)

        if video_path.stat().st_size > MAX_VIDEO_SIZE_BYTES:
            await status_message.edit_text(f"❌ الفيديو أكبر من الحد الأقصى: {MAX_VIDEO_SIZE_MB} MB.")
            return

        clean_filename = make_clean_filename(platform)
        await message.answer_video(
            video=FSInputFile(video_path, filename=clean_filename),
            caption=(
                "✨ <b>تمت المهمة بنجاح</b>\n\n"
                f"📥 المصدر: {platform}\n"
                f"📁 اسم الملف: <code>{clean_filename}</code>\n\n"
                "🐾 تم التنزيل بواسطة نيكورين"
            ),
            supports_streaming=True,
            parse_mode=ParseMode.HTML,
        )
        await status_message.delete()

    except yt_dlp.utils.DownloadError as error:
        logging.exception("Download error: %s", error)
        error_text = str(error).lower()
        if "login" in error_text or "cookies" in error_text:
            response = "❌ الموقع طلب تسجيل دخول لهذا الفيديو. جرّب رابط عام."
        elif "private" in error_text:
            response = "❌ الحساب أو الفيديو خاص."
        elif "unsupported url" in error_text:
            response = "❌ الرابط غير مدعوم."
        else:
            response = "❌ ما قدرت أنزّل الفيديو. تأكد أن الرابط عام وجرب مرة ثانية."
        await status_message.edit_text(response)

    except Exception as error:
        logging.exception("Unexpected error: %s", error)
        await status_message.edit_text("❌ صار خطأ أثناء تنزيل الفيديو.")

    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


@router.message()
async def other_messages_handler(message: Message) -> None:
    if not is_allowed(message):
        await message.answer("🔒 هذا البوت خاص.")
        return
    await message.answer("📎 طرش رابط من Instagram أو TikTok أو X.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not bot:
        raise RuntimeError("BOT_TOKEN غير موجود")
    webhook_url = f"https://{RENDER_HOSTNAME}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url, secret_token=WEBHOOK_SECRET, drop_pending_updates=True)
    logging.info("Webhook enabled: %s", webhook_url)
    yield
    await bot.delete_webhook()
    await bot.session.close()


app = FastAPI(title="Neko Downloader Bot", lifespan=lifespan)


@app.get("/")
async def health() -> dict[str, str]:
    return {"status": "online", "bot": "Neko Downloader Bot"}


@app.post(WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    if not bot:
        raise HTTPException(status_code=500, detail="Bot is not configured")

    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dispatcher.feed_update(bot, update)
    return {"ok": True}


async def run_polling() -> None:
    if not bot:
        raise RuntimeError("BOT_TOKEN غير موجود داخل ملف .env")
    await bot.delete_webhook(drop_pending_updates=True)
    print("🐾 Neko Downloader Bot is running locally...")
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def validate_settings() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN غير موجود")
    if not ALLOWED_USERS:
        raise RuntimeError("ALLOWED_USERS غير موجود أو غير صحيح")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    validate_settings()

    if RENDER_HOSTNAME:
        print("🐾 Starting Neko Downloader Bot on Render...")
        uvicorn.run(app, host="0.0.0.0", port=PORT)
    else:
        asyncio.run(run_polling())
