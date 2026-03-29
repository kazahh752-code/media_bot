import asyncio
import logging
import os
import re
from pathlib import Path
from threading import Thread

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

from config import BOT_TOKEN, PORT
from downloader import download_instagram, download_youtube_video, download_youtube_audio

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app_flask = Flask(__name__)

TEMP_DIR = Path(__file__).resolve().parent / "temp"
TEMP_DIR.mkdir(exist_ok=True)


@app_flask.route("/")
def index():
    return "Media Bot is running!", 200


# ── Helpers ───────────────────────────────────────────────────────────────────

def detect_platform(url: str) -> str:
    if re.search(r"instagram\.com|instagr\.am", url):
        return "instagram"
    if re.search(r"youtube\.com|youtu\.be", url):
        return "youtube"
    return "unknown"


def clean_temp(filepath: str):
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
    except Exception:
        pass


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я скачиваю медиа из Instagram и YouTube.\n\n"
        "📌 Просто скинь ссылку:\n"
        "• <b>Instagram</b> — скачаю видео/reels/stories\n"
        "• <b>YouTube</b> — выбери: видео 🎬 или аудио 🎵\n\n"
        "Поддерживаются публичные посты. Для Stories нужен публичный аккаунт.",
        parse_mode="HTML"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>Как пользоваться:</b>\n\n"
        "1️⃣ Скопируй ссылку из Instagram или YouTube\n"
        "2️⃣ Вставь её в чат\n"
        "3️⃣ Для YouTube выбери формат: видео или аудио\n\n"
        "⚠️ Ограничения Telegram:\n"
        "• Видео до <b>50 МБ</b> отправляется напрямую\n"
        "• Если файл больше — получишь сообщение\n\n"
        "🔗 Поддерживаемые ссылки:\n"
        "• instagram.com/p/... — пост\n"
        "• instagram.com/reel/... — reels\n"
        "• youtube.com/watch?v=...\n"
        "• youtu.be/...",
        parse_mode="HTML"
    )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # Extract URL from message
    urls = re.findall(r'https?://\S+', text)
    if not urls:
        return

    url = urls[0]
    platform = detect_platform(url)

    if platform == "unknown":
        await update.message.reply_text("❌ Поддерживаются только Instagram и YouTube.")
        return

    if platform == "instagram":
        await handle_instagram(update, context, url)

    elif platform == "youtube":
        # Save URL in context, show format choice
        context.user_data["yt_url"] = url
        keyboard = [
            [
                InlineKeyboardButton("🎬 Видео (mp4)", callback_data="yt_video"),
                InlineKeyboardButton("🎵 Аудио (mp3)", callback_data="yt_audio"),
            ]
        ]
        await update.message.reply_text(
            f"🎞 YouTube ссылка получена.\nВыбери формат:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def handle_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    msg = await update.message.reply_text("⏳ Скачиваю из Instagram...")
    filepath = None
    try:
        filepath = await asyncio.get_event_loop().run_in_executor(
            None, download_instagram, url, str(TEMP_DIR)
        )
        if not filepath or not os.path.exists(filepath):
            await msg.edit_text("❌ Не удалось скачать. Возможно, аккаунт приватный или ссылка устарела.")
            return

        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        if size_mb > 50:
            await msg.edit_text(
                f"⚠️ Файл слишком большой ({size_mb:.1f} МБ).\n"
                "Telegram принимает до 50 МБ. Попробуй короткое видео."
            )
            return

        await msg.edit_text("📤 Отправляю видео...")
        with open(filepath, "rb") as f:
            await update.message.reply_video(
                video=f,
                caption="📥 Instagram видео",
                supports_streaming=True
            )
        await msg.delete()

    except Exception as e:
        logger.error(f"Instagram error: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
    finally:
        clean_temp(filepath)


async def handle_youtube_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    url = context.user_data.get("yt_url")
    if not url:
        await query.edit_message_text("❌ Ссылка не найдена, скинь ещё раз.")
        return

    choice = query.data  # yt_video or yt_audio
    fmt = "видео 🎬" if choice == "yt_video" else "аудио 🎵"
    await query.edit_message_text(f"⏳ Скачиваю {fmt}...\nЭто может занять до 1 минуты.")

    filepath = None
    try:
        if choice == "yt_video":
            filepath = await asyncio.get_event_loop().run_in_executor(
                None, download_youtube_video, url, str(TEMP_DIR)
            )
        else:
            filepath = await asyncio.get_event_loop().run_in_executor(
                None, download_youtube_audio, url, str(TEMP_DIR)
            )

        if not filepath or not os.path.exists(filepath):
            await query.edit_message_text("❌ Не удалось скачать. Проверь ссылку.")
            return

        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        if size_mb > 50:
            await query.edit_message_text(
                f"⚠️ Файл слишком большой ({size_mb:.1f} МБ).\n"
                "YouTube ограничение Telegram — 50 МБ. Попробуй короткое видео."
            )
            return

        await query.edit_message_text("📤 Отправляю...")

        with open(filepath, "rb") as f:
            if choice == "yt_video":
                await query.message.reply_video(
                    video=f,
                    caption="📥 YouTube видео",
                    supports_streaming=True
                )
            else:
                await query.message.reply_audio(
                    audio=f,
                    caption="🎵 YouTube аудио"
                )

        await query.message.delete()

    except Exception as e:
        logger.error(f"YouTube error: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)[:200]}")
    finally:
        clean_temp(filepath)


# ── Run ───────────────────────────────────────────────────────────────────────

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_handler(CallbackQueryHandler(handle_youtube_choice, pattern="^yt_"))

    application.run_polling(stop_signals=None)


if __name__ == "__main__":
    Thread(target=run_bot, daemon=True).start()
    app_flask.run(host="0.0.0.0", port=PORT)
