"""
MCP-related bot handlers (Tasks 7, 10)

Commands:
  /files [path]  — list directory via MCP filesystem server (Task 7)
  /mcp           — show all tools from all connected MCP servers (Task 10)
  /mcp_call <prefixed_tool> [json_args]  — call a specific MCP tool
"""

import json
import logging

from aiogram import Router, types
from aiogram.filters import Command

from services.mcp_client import FilesystemMCPClient
from services.mcp_aggregator import MCPAggregator

router = Router()
log = logging.getLogger("bot.mcp")


# ── /files [path] ─────────────────────────────────────────────────────────────

@router.message(Command("files"))
async def handle_files(message: types.Message):
    """List directory contents via MCP filesystem server."""
    path_arg = (message.text or "").replace("/files", "", 1).strip() or "."

    status_msg = await message.answer("🔌 Подключаюсь к MCP filesystem серверу...")
    try:
        async with FilesystemMCPClient() as client:
            listing = await client.list_directory(path_arg)
            # listing is raw JSON from the filesystem server
            try:
                data = json.loads(listing)
                if isinstance(data, list):
                    lines = "\n".join(
                        f"{'📁' if item.get('type') == 'directory' else '📄'} {item.get('name', item)}"
                        for item in data
                    )
                else:
                    lines = listing
            except (json.JSONDecodeError, TypeError):
                lines = listing

            await status_msg.edit_text(
                f"📂 <b>Каталог: {path_arg}</b>\n\n<pre>{lines[:3000]}</pre>",
                parse_mode="HTML",
            )
    except Exception as e:
        log.error("MCP filesystem error: %s", e)
        await status_msg.edit_text(
            "❌ Не удалось подключиться к MCP filesystem серверу.\n"
            f"<code>{e}</code>",
            parse_mode="HTML",
        )


# ── /mcp — list all tools from aggregator ────────────────────────────────────

@router.message(Command("mcp"))
async def handle_mcp_list(message: types.Message, mcp_aggregator: MCPAggregator | None = None):
    """Show all tools available via the MCP aggregator."""
    if mcp_aggregator is None or not mcp_aggregator.is_ready():
        await message.answer(
            "⚠️ MCP агрегатор не инициализирован.\n"
            "Серверы запускаются при старте бота."
        )
        return

    tools = mcp_aggregator.list_all_tools()
    if not tools:
        await message.answer("❌ Нет доступных MCP инструментов.")
        return

    lines = []
    current_prefix = None
    for t in tools:
        prefix = t["name"].split("__")[0] + "__"
        if prefix != current_prefix:
            current_prefix = prefix
            server_label = {"fs__": "📁 Filesystem", "pg__": "🗄 PostgreSQL", "api__": "🌐 Custom API"}.get(prefix, prefix)
            lines.append(f"\n<b>{server_label}</b>")
        lines.append(f"  • <code>{t['name']}</code> — {t['description'][:60]}")

    await message.answer(
        "🔧 <b>Доступные MCP инструменты:</b>\n" + "\n".join(lines),
        parse_mode="HTML",
    )


# ── /mcp_call <tool> [args_json] ──────────────────────────────────────────────

@router.message(Command("mcp_call"))
async def handle_mcp_call(message: types.Message, mcp_aggregator: MCPAggregator | None = None):
    """Call a specific MCP tool. Usage: /mcp_call pg__query_users {"limit": 5}"""
    if mcp_aggregator is None or not mcp_aggregator.is_ready():
        await message.answer("⚠️ MCP агрегатор не инициализирован.")
        return

    parts = (message.text or "").split(None, 2)
    if len(parts) < 2:
        await message.answer("Использование: <code>/mcp_call &lt;tool_name&gt; {\"arg\": \"val\"}</code>", parse_mode="HTML")
        return

    tool_name = parts[1]
    args = {}
    if len(parts) == 3:
        try:
            args = json.loads(parts[2])
        except json.JSONDecodeError:
            await message.answer("❌ Некорректный JSON для аргументов.")
            return

    status = await message.answer(f"⏳ Вызываю <code>{tool_name}</code>...", parse_mode="HTML")
    try:
        result = await mcp_aggregator.call_tool(tool_name, args)
        await status.edit_text(
            f"✅ <b>{tool_name}</b>\n\n<pre>{result[:3000]}</pre>",
            parse_mode="HTML",
        )
    except Exception as e:
        log.error("mcp_call error: %s", e)
        await status.edit_text(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")
