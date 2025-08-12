import os, asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.utils.chat_action import ChatActionSender
from openai import OpenAI

load_dotenv()
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not TG_TOKEN: raise RuntimeError("TELEGRAM_BOT_TOKEN отсутствует")
if not OPENAI_KEY: raise RuntimeError("OPENAI_API_KEY отсутствует")

bot = Bot(token=TG_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
client = OpenAI(api_key=OPENAI_KEY)

SYSTEM_PROMPT = (
    "Ты — ассистент бренда «FIX FUR by ATARSHCHIKOV» (люкс меховое ателье). "
    "Отвечай кратко, уверенно, по делу; помогай с перешивом, реставрацией, уходом. "
    "Если нужен офлайн-визит — предложи записаться. Без воды."
)

def ask_openai_sync(text: str) -> str:
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            temperature=0.5,
            max_tokens=700
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return "Сейчас не получается ответить из-за тех. ошибки. Попробуйте позже."

@dp.message(F.text)
async def on_text(message: Message):
    async with ChatActionSender.typing(chat_id=message.chat.id, bot=bot):
        reply = await asyncio.to_thread(ask_openai_sync, message.text)
    await message.answer(reply)

@dp.message()
async def on_other(message: Message):
    await message.answer("Пришлите, пожалуйста, текстовый вопрос 🙂")

async def main():
    print("Bot started.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
