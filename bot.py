import os
import asyncio
import logging

from dotenv import load_dotenv
from openai import OpenAI

from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# -------- ENV --------
load_dotenv()
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
PORT = int(os.getenv("PORT", "10000"))

if not TG_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN отсутствует")
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY отсутствует")

# OpenAI — берём ключ из env (так стабильнее на Render)
os.environ["OPENAI_API_KEY"] = OPENAI_KEY
client = OpenAI()

# -------- LOGGING --------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fixfur-bot")

# -------- Telegram handlers --------
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
    return resp.choices[0].message.content.strip()

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text or ""
    reply = await asyncio.to_thread(ask_openai_sync, user_text)
    await update.message.reply_text(reply)

async def run_bot():
    application = Application.builder().token(TG_TOKEN).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    # run_polling — корутина, НЕ поток. Запускаем её внутри основного event loop:
    await application.run_polling(close_loop=False)

# -------- Flask (healthcheck для Render) --------
flask_app = Flask(__name__)

@flask_app.get("/")
def health():
    return "ok", 200

# -------- Unified asyncio entrypoint --------
async def main():
    # 1) Запускаем бота фоном в этом же event loop
    asyncio.create_task(run_bot())

    # 2) Поднимаем Flask через Hypercorn (асинхронный WSGI‑сервер)
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    cfg = Config()
    cfg.bind = [f"0.0.0.0:{PORT}"]
    log.info(f"Starting Flask healthcheck on port {PORT}")
    await serve(flask_app, cfg)

if __name__ == "__main__":
    asyncio.run(main())
