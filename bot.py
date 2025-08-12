import os
import asyncio
import logging
import threading
from dotenv import load_dotenv
from openai import OpenAI

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from flask import Flask

# ---------- ENV ----------
load_dotenv()
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not TG_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN отсутствует")
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY отсутствует")

# OpenAI: берём ключ из окружения (так стабильнее на Render)
os.environ["OPENAI_API_KEY"] = OPENAI_KEY
client = OpenAI()

# ---------- LOGGING ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------- TELEGRAM HANDLERS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот FIX FUR by ATARSHCHIKOV. Напишите вопрос — отвечу по делу.")

def _ask_openai_sync(text: str) -> str:
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system",
             "content": "Ты ассистент бренда «FIX FUR by ATARSHCHIKOV». Тон — премиальный, уверенный, без воды."},
            {"role": "user", "content": text}
        ],
        temperature=0.5,
        max_tokens=700
    )
    # для SDK v1: .message.content
    return resp.choices[0].message.content.strip()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text or ""
    reply = await asyncio.to_thread(_ask_openai_sync, user_text)
    await update.message.reply_text(reply)

def run_telegram_bot():
    app_tg = ApplicationBuilder().token(TG_TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app_tg.run_polling()

# ---------- FLASK (healthcheck для Render) ----------
app = Flask(__name__)

@app.get("/")
def health():
    return "ok", 200

if __name__ == "__main__":
    # Стартуем бота в отдельном потоке
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    # Поднимаем веб‑сервер на порту, который даёт Render
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
