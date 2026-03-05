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
PROD_URL = getenv('PROD_URL', 'YOUR_URL')
SERVICES_URL = getenv('SERVICES_URL', 'YOUR_SERVICES_URL')
MONITORING_URL = getenv('MONITORING_URL', '')
STAGING_URL = getenv('STAGING_URL', '')

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
    command_args = message.text.split()[1:]
    target = command_args[0] if len(command_args) > 0 else None

    async with aiohttp.ClientSession() as session:
        try:
            if target is None:
                # Request general info
                async with session.get(PROD_URL) as prod_response, session.get(SERVICES_URL) as services_response:
                    if prod_response.status == 200 and services_response.status == 200:
                        prod_data = await prod_response.json()
                        services_data = await services_response.json()

                        prod_services = format_status(prod_data.get('services', {}))
                        prod_containers = format_status(prod_data.get('containers', {}))
                        prod_diskspace = prod_data.get('diskspace', {})

                        services_services = format_status(services_data.get('services', {}))
                        services_containers = format_status(services_data.get('containers', {}))
                        services_diskspace = services_data.get('diskspace', {})

                        text = (
                            f"<b>Prod Server</b>\n<b>Services:</b>\n{prod_services}\n"
                            f"<b>Containers:</b>\n{prod_containers}\n"
                            f"<b>Diskspace:</b>\n{prod_diskspace}\n\n"
                            f"<b>Services Server</b>\n<b>Services:</b>\n{services_services}\n"
                            f"<b>Containers:</b>\n{services_containers}\n"
                            f"<b>Diskspace:</b>\n{services_diskspace}"
                        )
                        await message.reply(text, parse_mode=ParseMode.HTML)
                    else:
                        await message.reply("Error: Unable to fetch health check information from one or both URLs.")

            else:
                # Request specific info
                url_map = {
                    "prod": PROD_URL,
                    "services": SERVICES_URL,
                    "monitoring": MONITORING_URL,
                    "staging": STAGING_URL,
                }
                url = url_map.get(target)

                if url is None:
                    await message.reply("Invalid target. Use /health, /health prod, /health services, /health monitoring or /health staging.")
                    return

                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        services = format_status(data.get('services', {}))
                        containers = format_status(data.get('containers', {}))
                        diskspace = data.get('diskspace', '')
                        memory = data.get('memory', {})
                        load = data.get('load', '')

                        text = f"<b>{target.capitalize()} Server</b>\n"
                        text += f"<b>Services:</b>\n{services}\n"
                        if containers.strip():
                            text += f"<b>Containers:</b>\n{containers}\n"
                        text += f"<b>Diskspace:</b>\n{diskspace}\n"
                        if memory:
                            text += f"\n<b>Memory:</b>\n"
                            text += f"Used: {memory.get('used', '?')} / {memory.get('total', '?')} ({memory.get('used_pct', '?')})\n"
                            text += f"Available: {memory.get('available', '?')}\n"
                        if load:
                            text += f"\n<b>Load avg (1m 5m 15m):</b>\n{load}"

                        await message.reply(text.strip(), parse_mode=ParseMode.HTML)
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
