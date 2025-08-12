import os
import asyncio
import threading
import logging

from dotenv import load_dotenv
from openai import OpenAI

from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------- ENV ----------
load_dotenv()
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not TG_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN отсутствует")
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY отсутствует")

# OpenAI: передадим ключ через окружение (так надёжнее на Render)
os.environ["OPENAI_API_KEY"] = OPENAI_KEY
client = OpenAI()

# ---------- LOGGING ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fixfur-bot")

# ---------- Telegram handlers ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот FIX FUR by ATARSHCHIKOV. Напишите вопрос о мехе, перешиве или уходе — отвечу по делу."
    )

def ask_openai_sync(text: str) -> str:
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты ассистент бренда «FIX FUR by ATARSHCHIKOV». "
                    "Тон — премиальный, уверенный, краткий и по делу."
                ),
            },
            {"role": "user", "content": text},
        ],
        temperature=0.5,
        max_tokens=700,
    )
    # SDK v1: доступ к контенту так
    return resp.choices[0].message.content.strip()

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text or ""
    reply = await asyncio.to_thread(ask_openai_sync, user_text)
    await update.message.reply_text(reply)

# Асинхронный запуск бота
async def tg_main():
    app = ApplicationBuilder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    await app.run_polling()  # блокирующая корутина

def run_tg_in_thread():
    # Создаём отдельный event loop для потока
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(tg_main())

# ---------- Flask (healthcheck для Render) ----------
flask_app = Flask(__name__)

@flask_app.get("/")
def health():
    return "ok", 200

if __name__ == "__main__":
    # Стартуем Telegram‑бот в отдельном потоке с собственным event loop
    threading.Thread(target=run_tg_in_thread, daemon=True).start()

    # Поднимаем веб‑сервер (Render проверяет, что порт открыт)
    port = int(os.getenv("PORT", "10000"))
    log.info(f"Starting Flask healthcheck on port {port}")
    flask_app.run(host="0.0.0.0", port=port)
