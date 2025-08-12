import os
import asyncio
import logging

from dotenv import load_dotenv
from openai import OpenAI

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import Message

from flask import Flask
from hypercorn.asyncio import serve
from hypercorn.config import Config
import requests  # для скачивания голосовых

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
    "Ты — ассистент премиального мехового ателье «FIX FUR by ATARSHCHIKOV». "
    "Отвечай кратко, уверенно и по делу. Предлагай решения по перешиву, реставрации, уходу."
)

def chunk(text: str, size: int = 3500):
    for i in range(0, len(text), size):
        yield text[i:i+size]

@dp.message(F.text == "/start")
async def on_start(message: Message):
    welcome = (
        "Добро пожаловать в <b>FIX FUR by ATARSHCHIKOV</b> 🧥\n"
        "Задайте вопрос о реставрации, перешиве, хранении или уходе — подскажу лучший вариант."
    )
    await message.answer(welcome)

@dp.message(F.text & ~F.text.startswith("/"))
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
        reply = f"Извините, временная ошибка: {e}"
    for part in chunk(reply):
        await message.answer(part)

@dp.message(F.photo | F.video | (F.document & ~F.document.file_name.endswith(".oga")))
async def on_media(message: Message):
    caption = message.caption or "Прокомментируй это изображение/видео с точки зрения мехового ателье."
    try:
        resp = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": caption},
                ],
                temperature=0.5,
                max_tokens=600,
            )
        )
        reply = resp.choices[0].message.content.strip()
    except Exception as e:
        reply = f"Получил файл. Пока не удалось обработать: {e}"
    await message.answer(reply)

@dp.message(F.voice | (F.document & F.document.mime_type == "audio/ogg"))
async def on_voice(message: Message):
    try:
        file = await bot.get_file(message.voice.file_id if message.voice else message.document.file_id)
        file_url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{file.file_path}"
        # скачиваем файл
        r = requests.get(file_url, timeout=60)
        r.raise_for_status()
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(r.content)
            tmp_path = tmp.name
        # Whisper
        with open(tmp_path, "rb") as f:
            tr = client.audio.transcriptions.create(model="whisper-1", file=f)
        user_text = (tr.text if hasattr(tr, "text") else tr["text"]).strip()
        # ответ
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
        await message.answer(f"Расшифровка: «{user_text}»\n\n{reply}")
    except Exception as e:
        await message.answer(f"Не удалось обработать голосовое: {e}")

async def run_aiogram():
    # важный фикс конфликта: сбрасываем вебхук и очищаем висящие апдейты
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

# ---------- Flask (healthcheck) ----------
app = Flask(__name__)

@app.get("/")
def health():
    return "ok", 200

async def run_flask():
    cfg = Config()
    cfg.bind = [f"0.0.0.0:{PORT}"]
    await serve(app, cfg)

# ---------- Entry ----------
async def main():
    await asyncio.gather(run_aiogram(), run_flask())

if __name__ == "__main__":
    asyncio.run(main())
