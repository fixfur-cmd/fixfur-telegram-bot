import os
import asyncio
import logging
import base64
import requests
import tempfile

from dotenv import load_dotenv
from openai import OpenAI

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import Message

from flask import Flask
from hypercorn.asyncio import serve
from hypercorn.config import Config

# ---------- ENV ----------
load_dotenv()
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # умеет vision
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
    "Тон — премиальный, уверенный и по делу. Давай рекомендации по перешиву, реставрации и уходу."
)

def chunk(text: str, size: int = 3500):
    for i in range(0, len(text), size):
        yield text[i:i+size]

# ===== helpers =====
def openai_text_reply(prompt: str) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
        max_tokens=700,
    )
    return resp.choices[0].message.content.strip()

def openai_vision_reply(image_bytes: bytes, user_prompt: str) -> str:
    data_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("utf-8")
    resp = client.chat.completions.create(
        model=MODEL,  # gpt-4o-mini поддерживает картинки
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        temperature=0.5,
        max_tokens=700,
    )
    return resp.choices[0].message.content.strip()

# ===== handlers =====
@dp.message(F.text == "/start")
async def on_start(message: Message):
    welcome = (
        "Добро пожаловать в <b>FIX FUR by ATARSHCHIKOVI</b> 🧥\n"
        "Задайте вопрос о реставрации, перешиве, хранении или уходе — подскажу лучший вариант."
    )
    await message.answer(welcome)

@dp.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message):
    user_text = message.text or ""
    try:
        reply = await asyncio.to_thread(openai_text_reply, user_text)
    except Exception as e:
        reply = f"Извините, временная ошибка: {e}"
    for part in chunk(reply):
        await message.answer(part)

# Фото (jpg/png) как photo или как документ-изображение
@dp.message(F.photo | (F.document & F.document.mime_type.startswith("image/")))
async def on_photo(message: Message):
    try:
        caption = message.caption or (
            "Проанализируй изображение как мастер мехового ателье: состояние меха, видимые дефекты, варианты работ и уход."
        )
        # берём самое большое превью или сам документ
        if getattr(message, "photo", None):
            file_id = message.photo[-1].file_id
        else:
            file_id = message.document.file_id

        tg_file = await bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{tg_file.file_path}"
        img_bytes = requests.get(file_url, timeout=60).content

        reply = await asyncio.to_thread(openai_vision_reply, img_bytes, caption)
    except Exception as e:
        reply = f"Не удалось проанализировать фото: {e}"
    await message.answer(reply)

# Голосовые (ogg/oga) → Whisper → ответ
@dp.message(F.voice | (F.document & F.document.mime_type == "audio/ogg"))
async def on_voice(message: Message):
    try:
        file = await bot.get_file(message.voice.file_id if message.voice else message.document.file_id)
        file_url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{file.file_path}"
        r = requests.get(file_url, timeout=60)
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(r.content)
            tmp_path = tmp.name
        with open(tmp_path, "rb") as f:
            tr = client.audio.transcriptions.create(model="whisper-1", file=f)
        user_text = (tr.text if hasattr(tr, "text") else tr["text"]).strip()
        reply = await asyncio.to_thread(openai_text_reply, user_text)
        await message.answer(f"Расшифровка: «{user_text}»\n\n{reply}")
    except Exception as e:
        await message.answer(f"Не удалось обработать голосовое: {e}")

# ---------- Flask (healthcheck для Render) ----------
app = Flask(__name__)

@app.get("/")
def health():
    return "ok", 200

async def run_flask():
    cfg = Config()
    cfg.bind = [f"0.0.0.0:{PORT}"]
    await serve(app, cfg)

async def run_aiogram():
    # фикс конфликтов polling: сбрасываем вебхук и висящие апдейты
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

# ---------- Entry ----------
async def main():
    await asyncio.gather(run_aiogram(), run_flask())

if __name__ == "__main__":
    asyncio.run(main())
