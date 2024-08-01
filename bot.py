import asyncio
import logging
import sys
from os import getenv

import aiohttp
from aiogram import Bot, Dispatcher, html
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.types import Message


TOKEN = getenv('TELEGRAM_API_TOKEN', 'YOUR_API_TOKEN')
URL = getenv('URL', 'YOUR_URL')

# Configure logging
logging.basicConfig(level=logging.INFO)

dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: Message):
    text = (
        f"Assalamu aleikum!\n{html.bold(message.from_user.full_name)}\n"
        "I'm dobrofon_dev_bot!\nPowered by @ibn_petr.\n\n"
        "I can help you with getting the latest health-check info from your server.\n\n"
        "Just type /health and I'll show you the health-check info."
    )
    await message.reply(text)

def format_status(status: dict) -> str:
    formatted = ""
    for service, state in status.items():
        symbol = "✅" if state == "ok" else "❌"
        formatted += f"{service}: {symbol}\n"
    return formatted


@dp.message(Command(commands=["health"]))
async def get_health(message: Message):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(URL) as response:
                if response.status == 200:
                    data = await response.json()
                    services = format_status(data.get('services', {}))
                    containers = format_status(data.get('containers', {}))
                    text = f"<b>Services:</b>\n{services}\n<b>Containers:</b>\n{containers}"
                    await message.reply(text, parse_mode=ParseMode.HTML)
                else:
                    await message.reply(f"Error: {response.status}")
        except Exception as e:
            await message.reply(f"Error: {e}")

async def main() -> None:
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    await dp.start_polling(bot)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
