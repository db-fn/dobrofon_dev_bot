import asyncio
import json
import logging
import sys
import time
from os import getenv
from pathlib import Path

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

PROD_TOKEN = getenv('PROD_TOKEN', '')
MONITORING_TOKEN = getenv('MONITORING_TOKEN', '')
STAGING_TOKEN = getenv('STAGING_TOKEN', '')

ALERT_CHAT_ID = getenv('ALERT_CHAT_ID', '')
SNAPSHOTS_FILE = getenv('SNAPSHOTS_FILE', '/home/dobrofon/alarm-bot/snapshots.jsonl')


def _with_token(url: str, token: str) -> str:
    if not token or not url:
        return url
    sep = '&' if '?' in url else '?'
    return f"{url}{sep}token={token}"


dp = Dispatcher()

last_state: dict[str, dict] = {}

HELP_TEXT = (
    "Available commands:\n\n"
    "/health — all servers overview\n"
    "/prod — production server\n"
    "/services — services server (runners, registry, etc.)\n"
    "/monitoring — monitoring server\n"
    "/staging — staging server\n"
    "/stats — sparkline stats for last 7 days\n"
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


def mb_to_gb(mb_str: str) -> str:
    try:
        mb = int(mb_str.replace("MB", ""))
        return f"{mb / 1024:.1f}GB"
    except Exception:
        return mb_str


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
    return "\n".join(parts)


def pct_indicator(pct_str: str) -> str:
    try:
        pct = int(str(pct_str).replace('%', '').strip())
        if pct >= 90:
            return '🔴'
        if pct >= 80:
            return '⚠️'
        return '✅'
    except Exception:
        return ''


def cpu_indicator(cpu_str: str) -> str:
    try:
        val = int(str(cpu_str).replace('%', '').strip())
        if val >= 90:
            return '🔴'
        if val >= 70:
            return '⚠️'
        return '✅'
    except Exception:
        return ''


def disk_pct(disk_str: str) -> str:
    for part in disk_str.split():
        if part.endswith('%'):
            return part
    return ''


def format_server_block(name: str, data: dict, command: str = "") -> str:
    services = data.get('services', {})
    containers = data.get('containers', {})
    diskspace = data.get('diskspace', '')
    memory = data.get('memory', {})
    load = data.get('cpu', data.get('load', ''))
    registry = data.get('registry', {})
    connections = data.get('connections', None)
    network = data.get('network', {})

    disk_compact = ' '.join(diskspace.split()[1:]) if diskspace else ''

    title = f"🖥 <b>{name}</b>"
    if command:
        title += f" /{command}"
    lines = [title]

    if services:
        lines.append(f"<b>Services:</b>")
        lines.append(format_status_line(services))

    if containers:
        lines.append(f"<b>Containers:</b>")
        lines.append(format_status_line(containers))

    if disk_compact:
        dpct = disk_pct(diskspace)
        disk_icon = pct_indicator(dpct) if dpct else '💾'
        lines.append(f"{disk_icon} Disk: {disk_compact}")

    if memory:
        used = mb_to_gb(memory.get('used', '?'))
        total = mb_to_gb(memory.get('total', '?'))
        pct = memory.get('used_pct', '?')
        ram_icon = pct_indicator(pct)
        lines.append(f"{ram_icon} RAM: {used}/{total} ({pct})")

    if load:
        load_icon = cpu_indicator(load)
        label = 'CPU' if data.get('cpu') else 'Load'
        lines.append(f"{load_icon} {label}: {load}")

    if connections is not None:
        conn_icon = '🔴' if connections > 1000 else ('⚠️' if connections > 500 else '✅')
        lines.append(f"{conn_icon} Connections: {connections}")

    if network:
        rx = network.get('rx', '')
        tx = network.get('tx', '')
        if rx or tx:
            lines.append(f"🌐 Net: ↓{rx} ↑{tx}")

    preview_count = data.get('preview_count', 0)
    if preview_count:
        lines.append(f"🔬 Preview envs: {preview_count} active")

    if registry and registry.get('total_repos', 0) > 0:
        repos = registry.get('repos', {})
        repo_lines = [f"  • {r}: {t} tag{'s' if t != 1 else ''}" for r, t in sorted(repos.items())]
        lines.append(f"📦 Registry: {registry['total_repos']} repos, {registry['total_tags']} tags")
        lines.extend(repo_lines)

    return "\n".join(lines)


async def fetch_server(session, name: str, url: str, command: str = "") -> str:
    if not url:
        return f"⚠️ {name}: not configured"
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                return format_server_block(f"{name} Server", data, command)
            return f"⚠️ {name}: HTTP {resp.status}"
    except Exception as e:
        return f"⚠️ {name}: {e}"


async def fetch_server_data(session, url: str) -> dict | None:
    if not url:
        return None
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            return None
    except Exception:
        return None


def _extract_pct(val: str) -> int | None:
    try:
        return int(str(val).replace('%', '').strip())
    except Exception:
        return None


def save_snapshot(server: str, data: dict) -> None:
    try:
        memory = data.get('memory', {})
        ram_pct = memory.get('used_pct', '') if memory else ''
        diskspace = data.get('diskspace', '')
        dpct = disk_pct(diskspace)
        cpu_val = data.get('cpu', data.get('load', ''))
        services = data.get('services', {})
        containers = data.get('containers', {})
        services_ok = all(v == 'ok' for v in services.values()) if services else True
        containers_ok = all(v == 'ok' for v in containers.values()) if containers else True

        snapshot = {
            "ts": int(time.time()),
            "server": server,
            "cpu": str(cpu_val),
            "ram_pct": str(ram_pct),
            "disk_pct": dpct,
            "services_ok": services_ok,
            "containers_ok": containers_ok,
        }

        path = Path(SNAPSHOTS_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'a') as f:
            f.write(json.dumps(snapshot) + "\n")

        cutoff = int(time.time()) - 31 * 86400
        if path.exists():
            lines = path.read_text().splitlines()
            kept = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get('ts', 0) > cutoff:
                        kept.append(line)
                except Exception:
                    pass
            if len(kept) < len([l for l in lines if l.strip()]):
                path.write_text("\n".join(kept) + "\n")
    except Exception as e:
        logging.warning(f"save_snapshot error: {e}")


def load_snapshots(server: str, days: int = 7) -> list[dict]:
    path = Path(SNAPSHOTS_FILE)
    if not path.exists():
        return []
    cutoff = int(time.time()) - days * 86400
    results = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if entry.get('server') == server and entry.get('ts', 0) > cutoff:
                results.append(entry)
        except Exception:
            pass
    return results


def detect_alerts(server: str, old: dict, new: dict) -> list[str]:
    alerts = []

    old_services = old.get('services', {})
    new_services = new.get('services', {})
    for svc, state in new_services.items():
        if state != 'ok' and old_services.get(svc) == 'ok':
            alerts.append(f"{shorten_name(svc)} ✅→❌")

    old_containers = old.get('containers', {})
    new_containers = new.get('containers', {})
    for ctr, state in new_containers.items():
        if state != 'ok' and old_containers.get(ctr) == 'ok':
            alerts.append(f"{shorten_name(ctr)} ✅→❌")

    old_mem = old.get('memory', {})
    new_mem = new.get('memory', {})
    old_ram = _extract_pct(old_mem.get('used_pct', ''))
    new_ram = _extract_pct(new_mem.get('used_pct', ''))
    if old_ram is not None and new_ram is not None:
        if new_ram >= 90 and old_ram < 90:
            alerts.append(f"RAM: {old_ram}% → {new_ram}% 🔴")
        elif new_ram >= 80 and old_ram < 80:
            alerts.append(f"RAM: {old_ram}% → {new_ram}% ⚠️")

    old_disk_str = old.get('diskspace', '')
    new_disk_str = new.get('diskspace', '')
    old_disk = _extract_pct(disk_pct(old_disk_str))
    new_disk = _extract_pct(disk_pct(new_disk_str))
    if old_disk is not None and new_disk is not None:
        if new_disk >= 90 and old_disk < 90:
            alerts.append(f"Disk: {old_disk}% → {new_disk}% 🔴")
        elif new_disk >= 80 and old_disk < 80:
            alerts.append(f"Disk: {old_disk}% → {new_disk}% ⚠️")

    old_cpu_str = old.get('cpu', old.get('load', ''))
    new_cpu_str = new.get('cpu', new.get('load', ''))
    old_cpu = _extract_pct(old_cpu_str)
    new_cpu = _extract_pct(new_cpu_str)
    if old_cpu is not None and new_cpu is not None:
        if new_cpu >= 90 and old_cpu < 90:
            alerts.append(f"CPU: {old_cpu}% → {new_cpu}% 🔴")
        elif new_cpu >= 70 and old_cpu < 70:
            alerts.append(f"CPU: {old_cpu}% → {new_cpu}% ⚠️")

    return alerts


def make_sparkline(values: list[float]) -> str:
    blocks = "▁▂▃▄▅▆▇█"
    if not values:
        return ""
    mn, mx = min(values), max(values)
    span = mx - mn if mx != mn else 1
    return "".join(blocks[min(7, int((v - mn) / span * 7))] for v in values)


def _stats_for_server(server: str) -> str:
    snapshots = load_snapshots(server, days=7)
    if not snapshots:
        return f"🖥 <b>{server} Server</b>\nNo data yet"

    cpu_vals = []
    ram_vals = []
    disk_vals = []
    for s in snapshots:
        c = _extract_pct(s.get('cpu', ''))
        r = _extract_pct(s.get('ram_pct', ''))
        d = _extract_pct(s.get('disk_pct', ''))
        if c is not None:
            cpu_vals.append(float(c))
        if r is not None:
            ram_vals.append(float(r))
        if d is not None:
            disk_vals.append(float(d))

    lines = [f"🖥 <b>{server} Server</b>"]

    if cpu_vals:
        avg = sum(cpu_vals) / len(cpu_vals)
        spark = make_sparkline(cpu_vals[-24:])
        lines.append(f"CPU:  {spark} avg {avg:.0f}%")

    if ram_vals:
        avg = sum(ram_vals) / len(ram_vals)
        spark = make_sparkline(ram_vals[-24:])
        lines.append(f"RAM:  {spark} avg {avg:.0f}%")

    if disk_vals:
        avg = sum(disk_vals) / len(disk_vals)
        spark = make_sparkline(disk_vals[-24:])
        lines.append(f"Disk: {spark} avg {avg:.0f}%")

    return "\n".join(lines)


async def run_health_check(bot: Bot) -> None:
    all_servers = [
        ("Prod", _with_token(PROD_URL, PROD_TOKEN)),
        ("Services", SERVICES_URL),
        ("Monitoring", _with_token(MONITORING_URL, MONITORING_TOKEN)),
        ("Staging", _with_token(STAGING_URL, STAGING_TOKEN)),
    ]

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        results = await asyncio.gather(*[
            fetch_server_data(session, url)
            for _, url in all_servers
        ])

    alert_lines = []
    for (name, _), data in zip(all_servers, results):
        if data is None:
            continue
        await asyncio.to_thread(save_snapshot, name, data)
        if name in last_state:
            alerts = detect_alerts(name, last_state[name], data)
            if alerts:
                block = f"🚨 ALERT: {name} Server\n" + "\n".join(alerts)
                alert_lines.append(block)
        last_state[name] = data

    if alert_lines and ALERT_CHAT_ID:
        try:
            await bot.send_message(
                chat_id=ALERT_CHAT_ID,
                text="\n\n".join(alert_lines),
            )
        except Exception as e:
            logging.warning(f"Failed to send alert: {e}")


async def monitoring_loop(bot: Bot) -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            await run_health_check(bot)
        except Exception as e:
            logging.error(f"monitoring_loop error: {e}")


@dp.message(Command(commands=["prod"]))
async def cmd_prod(message: Message):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        await message.reply(await fetch_server(session, "Prod", _with_token(PROD_URL, PROD_TOKEN)), parse_mode=ParseMode.HTML)


@dp.message(Command(commands=["services"]))
async def cmd_services(message: Message):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        await message.reply(await fetch_server(session, "Services", SERVICES_URL), parse_mode=ParseMode.HTML)


@dp.message(Command(commands=["monitoring"]))
async def cmd_monitoring(message: Message):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        await message.reply(await fetch_server(session, "Monitoring", _with_token(MONITORING_URL, MONITORING_TOKEN)), parse_mode=ParseMode.HTML)


@dp.message(Command(commands=["staging"]))
async def cmd_staging(message: Message):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        await message.reply(await fetch_server(session, "Staging", _with_token(STAGING_URL, STAGING_TOKEN)), parse_mode=ParseMode.HTML)


@dp.message(Command(commands=["health"]))
async def get_health(message: Message):
    all_servers = [
        ("Prod", _with_token(PROD_URL, PROD_TOKEN), "prod"),
        ("Services", SERVICES_URL, "services"),
        ("Monitoring", _with_token(MONITORING_URL, MONITORING_TOKEN), "monitoring"),
        ("Staging", _with_token(STAGING_URL, STAGING_TOKEN), "staging"),
    ]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        try:
            blocks = await asyncio.gather(*[
                fetch_server(session, name, url, command)
                for name, url, command in all_servers if url
            ])
            await message.reply("\n\n".join(blocks) or "No servers configured.", parse_mode=ParseMode.HTML)
        except Exception as e:
            await message.reply(f"Error: {e}")


@dp.message(Command(commands=["stats"]))
async def cmd_stats(message: Message):
    servers = ["Prod", "Services", "Monitoring", "Staging"]
    blocks = await asyncio.gather(*[
        asyncio.to_thread(_stats_for_server, s) for s in servers
    ])
    text = "📊 <b>Stats (last 7 days)</b>\n\n" + "\n\n".join(blocks)
    await message.reply(text, parse_mode=ParseMode.HTML)


async def main() -> None:
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    _monitor_task = asyncio.create_task(monitoring_loop(bot))
    await run_health_check(bot)
    await dp.start_polling(bot)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
