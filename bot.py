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
    "/prod — production server\n"
    "/services — services server (runners, registry, etc.)\n"
    "/monitoring — monitoring server\n"
    "/staging — staging server\n"
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

def shorten_name(name: str) -> str:
    name = name.removesuffix(".service")
    replacements = {
        "github-actions-runner": "gh-runner",
        "celery-production": "celery",
        "celerybeat-production": "celerybeat",
        "dobrofon-production": "dobrofon",
        "admin-frontend-production-app": "admin-frontend",
        "redis-production": "redis",
    }
    return replacements.get(name, name)


def format_status_line(status: dict) -> str:
    parts = []
    for name, state in status.items():
        symbol = "✅" if state == "ok" else "❌"
        parts.append(f"{shorten_name(name)} {symbol}")
    return " │ ".join(parts)


def format_server_block(name: str, data: dict) -> str:
    services = data.get('services', {})
    containers = data.get('containers', {})
    diskspace = data.get('diskspace', '')
    memory = data.get('memory', {})
    load = data.get('load', '')
    registry = data.get('registry', {})

    disk_compact = ' '.join(diskspace.split()[1:]) if diskspace else ''

    lines = [f"🖥 <b>{name}</b>"]

    if services:
        lines.append(f"<b>Services:</b> {format_status_line(services)}")

    if containers:
        lines.append(f"<b>Containers:</b> {format_status_line(containers)}")

    if disk_compact:
        lines.append(f"💾 {disk_compact}")

    if memory and load:
        used = memory.get('used', '?')
        total = memory.get('total', '?')
        pct = memory.get('used_pct', '?')
        lines.append(f"🧠 RAM: {used}/{total} ({pct}) │ Load: {load}")
    elif memory:
        lines.append(f"🧠 RAM: {memory.get('used','?')}/{memory.get('total','?')} ({memory.get('used_pct','?')})")
    elif load:
        lines.append(f"📊 Load: {load}")

    if registry and registry.get('total_repos', 0) > 0:
        repos = registry.get('repos', {})
        repo_lines = [f"  • {r}: {t} tag{'s' if t != 1 else ''}" for r, t in sorted(repos.items())]
        lines.append(f"📦 Registry: {registry['total_repos']} repos, {registry['total_tags']} tags")
        lines.extend(repo_lines)

    return "\n".join(lines)


async def fetch_server(session, name: str, url: str) -> str:
    if not url:
        return f"⚠️ {name}: not configured"
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                return format_server_block(f"{name} Server", data)
            return f"⚠️ {name}: HTTP {resp.status}"
    except Exception as e:
        return f"⚠️ {name}: {e}"


@dp.message(Command(commands=["prod"]))
async def cmd_prod(message: Message):
    async with aiohttp.ClientSession() as session:
        await message.reply(await fetch_server(session, "Prod", PROD_URL), parse_mode=ParseMode.HTML)


@dp.message(Command(commands=["services"]))
async def cmd_services(message: Message):
    async with aiohttp.ClientSession() as session:
        await message.reply(await fetch_server(session, "Services", SERVICES_URL), parse_mode=ParseMode.HTML)


@dp.message(Command(commands=["monitoring"]))
async def cmd_monitoring(message: Message):
    async with aiohttp.ClientSession() as session:
        await message.reply(await fetch_server(session, "Monitoring", MONITORING_URL), parse_mode=ParseMode.HTML)


@dp.message(Command(commands=["staging"]))
async def cmd_staging(message: Message):
    async with aiohttp.ClientSession() as session:
        await message.reply(await fetch_server(session, "Staging", STAGING_URL), parse_mode=ParseMode.HTML)


@dp.message(Command(commands=["health"]))
async def get_health(message: Message):
    command_args = message.text.split()[1:]
    target = command_args[0] if len(command_args) > 0 else None

    all_servers = [
        ("Prod", PROD_URL),
        ("Services", SERVICES_URL),
        ("Monitoring", MONITORING_URL),
        ("Staging", STAGING_URL),
    ]
    async with aiohttp.ClientSession() as session:
        try:
            blocks = await asyncio.gather(*[
                fetch_server(session, name, url)
                for name, url in all_servers if url
            ])
            await message.reply("\n\n".join(blocks) or "No servers configured.", parse_mode=ParseMode.HTML)
        except Exception as e:
            await message.reply(f"Error: {e}")

async def main() -> None:
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    await dp.start_polling(bot)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
