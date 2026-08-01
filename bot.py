import asyncio
import logging
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

import yt_dlp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, Message
from dotenv import load_dotenv


# =========================================================
# إعدادات المشروع
# =========================================================

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


# =========================================================
# دوال المساعدة
# =========================================================

def is_allowed(message: Message) -> bool:
    return bool(
        message.from_user
        and message.from_user.id in ALLOWED_USERS
    )


def extract_supported_url(text: str) -> str | None:
    match = SUPPORTED_URL_PATTERN.search(text)

    if not match:
        return None

    return match.group(0).rstrip(").,]}>\"'")


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

    safe_platform = {
        "Instagram": "Instagram",
        "TikTok": "TikTok",
        "X": "X",
    }.get(platform, "Video")

    return f"Nekorin_{safe_platform}_{timestamp}.mp4"


def download_video(url: str, job_dir: Path) -> Path:
    output_template = str(job_dir / "%(id)s.%(ext)s")

    ydl_options = {
        "format": (
            "bestvideo[ext=mp4][filesize<45M]+"
            "bestaudio[ext=m4a]/"
            "best[ext=mp4][filesize<45M]/"
            "best[filesize<45M]/"
            "best"
        ),
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "overwrites": True,
    }

    with yt_dlp.YoutubeDL(ydl_options) as ydl:
        info = ydl.extract_info(url, download=True)

        requested_downloads = info.get("requested_downloads") or []

        for item in requested_downloads:
            filepath = item.get("filepath")

            if filepath:
                file_path = Path(filepath)

                if file_path.exists():
                    return file_path

        prepared_filename = Path(ydl.prepare_filename(info))

        if prepared_filename.exists():
            return prepared_filename

    video_files = [
        file
        for file in job_dir.iterdir()
        if file.is_file()
        and file.suffix.lower() in {
            ".mp4",
            ".mov",
            ".mkv",
            ".webm",
        }
    ]

    if not video_files:
        raise FileNotFoundError(
            "لم يتم العثور على الفيديو بعد التنزيل."
        )

    return max(
        video_files,
        key=lambda file: file.stat().st_size,
    )


# =========================================================
# أوامر ورسائل البوت
# =========================================================

@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    if not is_allowed(message):
        await message.answer("🔒 هذا البوت خاص.")
        return

    await message.answer(
        "🌸 <b>هلا بك في Neko Downloader Bot</b> 🐾\n\n"
        "أنا <b>نيكورين</b>، مهمتي أنزّل لك الفيديوهات بسرعة ✨\n\n"
        "🎬 <b>المنصات المدعومة:</b>\n"
        "📸 Instagram\n"
        "🎵 TikTok\n"
        "𝕏 X / Twitter\n\n"
        "📎 فقط طرش رابط الفيديو، والباقي عليّ 😎",
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text)
async def download_handler(
    message: Message,
    bot: Bot,
) -> None:
    if not is_allowed(message):
        await message.answer("🔒 هذا البوت خاص.")
        return

    text = message.text or ""
    url = extract_supported_url(text)

    if not url:
        await message.answer(
            "❌ طرش رابط من:\n"
            "📸 Instagram\n"
            "🎵 TikTok\n"
            "𝕏 X / Twitter"
        )
        return

    platform = get_platform_name(url)

    status_message = await message.answer(
        f"🐾 <b>نيكورين تحمل الفيديو...</b>\n\n"
        f"📥 المصدر: {platform}\n"
        "⏳ باقي شوي بس ✨",
        parse_mode=ParseMode.HTML,
    )

    job_dir = DOWNLOADS_DIR / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        await bot.send_chat_action(
            chat_id=message.chat.id,
            action=ChatAction.UPLOAD_VIDEO,
        )

        video_path = await asyncio.to_thread(
            download_video,
            url,
            job_dir,
        )

        file_size = video_path.stat().st_size

        if file_size > MAX_VIDEO_SIZE_BYTES:
            await status_message.edit_text(
                "❌ الفيديو أكبر من الحد الحالي.\n"
                f"الحد الأقصى: {MAX_VIDEO_SIZE_MB} MB."
            )
            return

        clean_filename = make_clean_filename(platform)

        video_file = FSInputFile(
            video_path,
            filename=clean_filename,
        )

        await message.answer_video(
            video=video_file,
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
        logging.exception(
            "Download error: %s",
            error,
        )

        error_text = str(error).lower()

        if "login" in error_text or "cookies" in error_text:
            response = (
                "❌ الموقع طلب تسجيل دخول لهذا الفيديو.\n"
                "جرّب رابط عام."
            )
        elif "private" in error_text:
            response = "❌ الحساب أو الفيديو خاص."
        elif "unsupported url" in error_text:
            response = "❌ الرابط غير مدعوم."
        else:
            response = (
                "❌ ما قدرت أنزّل الفيديو.\n"
                "تأكد أن الرابط عام وجرب مرة ثانية."
            )

        await status_message.edit_text(response)

    except Exception as error:
        logging.exception(
            "Unexpected error: %s",
            error,
        )

        await status_message.edit_text(
            "❌ صار خطأ أثناء تنزيل الفيديو."
        )

    finally:
        shutil.rmtree(
            job_dir,
            ignore_errors=True,
        )


@router.message()
async def other_messages_handler(
    message: Message,
) -> None:
    if not is_allowed(message):
        await message.answer("🔒 هذا البوت خاص.")
        return

    await message.answer(
        "📎 طرش رابط من Instagram أو TikTok أو X."
    )


# =========================================================
# تشغيل البوت
# =========================================================

async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN غير موجود داخل ملف .env"
        )

    if not ALLOWED_USERS:
        raise RuntimeError(
            "ALLOWED_USERS غير موجود أو غير صحيح داخل ملف .env"
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    bot = Bot(token=BOT_TOKEN)

    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    print("🐾 Neko Downloader Bot is running...")
    print(f"🔒 Allowed users: {ALLOWED_USERS}")
    print("📸 Instagram | 🎵 TikTok | 𝕏 X")

    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())