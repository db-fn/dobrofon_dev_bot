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

HELP_TEXT = (
    "Available commands:\n\n"
    "/health — all servers overview\n"
    "/health prod — production server\n"
    "/health services — services server (runners, registry, etc.)\n"
    "/health monitoring — monitoring server\n"
    "/health staging — staging server\n"
    "/help — show this message"
)


@dp.message(CommandStart())
async def command_start_handler(message: Message):
    text = (
        f"Assalamu aleikum! {html.bold(message.from_user.full_name)}\n"
        "I'm dobrofon_dev_bot!\n\n"
        + HELP_TEXT
    )
    await message.reply(text)


@dp.message(Command(commands=["help"]))
async def command_help_handler(message: Message):
    await message.reply(HELP_TEXT)

def format_status(status: dict) -> str:
    formatted = ""
    for service, state in status.items():
        symbol = "✅" if state == "ok" else "❌"
        formatted += f"{service}: {symbol}\n"
    return formatted


def format_server_block(name: str, data: dict) -> str:
    services = format_status(data.get('services', {}))
    containers = format_status(data.get('containers', {}))
    diskspace = data.get('diskspace', '')
    memory = data.get('memory', {})
    load = data.get('load', '')
    registry = data.get('registry', {})

    text = f"<b>{name}</b>\n"
    text += f"<b>Services:</b>\n{services}\n"
    if containers.strip():
        text += f"<b>Containers:</b>\n{containers}\n"
    text += f"<b>Diskspace:</b>\n{diskspace}\n"
    if memory:
        text += f"\n<b>Memory:</b>\n"
        text += f"Used: {memory.get('used', '?')} / {memory.get('total', '?')} ({memory.get('used_pct', '?')})\n"
        text += f"Available: {memory.get('available', '?')}\n"
    if load:
        text += f"\n<b>Load avg (1m 5m 15m):</b>\n{load}\n"
    if registry and registry.get('total_repos', 0) > 0:
        text += f"\n<b>Registry:</b>\n"
        text += f"Repos: {registry.get('total_repos', 0)}, Tags: {registry.get('total_tags', 0)}\n"
        for repo, tag_count in sorted(registry.get('repos', {}).items()):
            text += f"  {repo}: {tag_count} tags\n"
    return text.strip()


@dp.message(Command(commands=["health"]))
async def get_health(message: Message):
    command_args = message.text.split()[1:]
    target = command_args[0] if len(command_args) > 0 else None

    async with aiohttp.ClientSession() as session:
        try:
            if target is None:
                all_servers = [
                    ("Prod", PROD_URL),
                    ("Services", SERVICES_URL),
                    ("Monitoring", MONITORING_URL),
                    ("Staging", STAGING_URL),
                ]
                blocks = []
                errors = []
                for name, url in all_servers:
                    if not url:
                        continue
                    try:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                blocks.append(format_server_block(f"{name} Server", data))
                            else:
                                errors.append(f"{name}: HTTP {resp.status}")
                    except Exception as e:
                        errors.append(f"{name}: {e}")

                text = "\n\n".join(blocks)
                if errors:
                    text += "\n\n⚠️ Errors:\n" + "\n".join(errors)
                await message.reply(text or "No servers configured.", parse_mode=ParseMode.HTML)

            else:
                # Request specific info
                url_map = {
                    "prod": PROD_URL,
                    "services": SERVICES_URL,
                    "monitoring": MONITORING_URL,
                    "staging": STAGING_URL,
                }
                url = url_map.get(target)

                if not url:
                    await message.reply("Invalid target. Use /health, /health prod, /health services, /health monitoring or /health staging.")
                    return

                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        text = format_server_block(f"{target.capitalize()} Server", data)
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
