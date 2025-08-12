import os
import asyncio
import logging

from dotenv import load_dotenv
from openai import OpenAI

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.enums import ParseMode

from flask import Flask
from hypercorn.asyncio import serve
from hypercorn.config import Config

# ---------- ENV ----------
load_dotenv()
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
PORT = int(os.getenv("PORT", "10000"))

if not TG_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN отсутствует")
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY отсутствует")

# OpenAI
os.environ["OPENAI_API_KEY"] = OPENAI_KEY
client = OpenAI()

# ---------- LOGGING ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fixfur-bot")

# ---------- Aiogram ----------
bot = Bot(token=TG_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

SYSTEM_PROMPT = (
    "Ты — ассистент бренда «FIX FUR by ATARSHCHIKOV». "
    "Тон — премиальный, уверенный, без воды. Помогай с перешивом, реставрацией и уходом за мехом."
)

@dp.message(F.text)
async def on_text(message: Message):
    user_text = message.text or ""
    try:
        resp = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.5,
                max_tokens=700,
            )
        )
        reply = resp.choices[0].message.content.strip()
    except Exception as e:
        reply = f"Сейчас не получается ответить: {e}"
    await message.answer(reply)

async def run_aiogram():
    await dp.start_polling(bot)

# ---------- Flask (healthcheck для Render) ----------
app = Flask(__name__)

@app.get("/")
def health():
    return "ok", 200

async def run_flask():
    cfg = Config()
    cfg.bind = [f"0.0.0.0:{PORT}"]
    await serve(app, cfg)

# ---------- Unified asyncio entry ----------
async def main():
    # запускаем бота и Flask параллельно в одном event loop
    await asyncio.gather(run_aiogram(), run_flask())

if __name__ == "__main__":
    asyncio.run(main())
