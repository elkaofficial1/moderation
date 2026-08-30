import asyncio
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta

import requests
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from ai import moderate_message as ai_moderate_message

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
AI_URL = os.getenv("AI_URL", "http://127.0.0.1:11434/api/chat")
MODEL = os.getenv("AI_MODEL", "qwen2.5:3b")
AUTO_BAN = os.getenv("AUTO_BAN", "true").lower() == "true"
MODE = os.getenv("MODE", "observe")

DB = "moderation.db"
TICKET_DAYS = 30

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


# =========================
# DATABASE
# =========================

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            full_name TEXT,
            text TEXT,
            score REAL,
            reason TEXT,
            status TEXT DEFAULT 'open',
            action TEXT,
            created_at INTEGER NOT NULL,
            resolved_at INTEGER
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            user_id INTEGER,
            admin_id INTEGER,
            action TEXT,
            created_at INTEGER NOT NULL,
            reverted INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            username TEXT,
            full_name TEXT,
            reason TEXT,
            ticket_id INTEGER,
            banned_at INTEGER NOT NULL,
            active INTEGER DEFAULT 1
        )
    """)

    # Migration for bans table
    bans_existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(bans)").fetchall()
    }

    bans_migrations = {
        "active": "INTEGER DEFAULT 1",
        "ticket_id": "INTEGER",
        "reason": "TEXT DEFAULT ''",
        "banned_at": "INTEGER DEFAULT 0"
    }

    for column, definition in bans_migrations.items():
        if column not in bans_existing:
            conn.execute(
                f"ALTER TABLE bans ADD COLUMN {column} {definition}"
            )

    # Fix old ban timestamps if the column was newly added
    conn.execute("""
        UPDATE bans
        SET banned_at = ?
        WHERE banned_at IS NULL OR banned_at = 0
    """, (int(time.time()),))

    # Migration from the previous tickets schema
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(tickets)").fetchall()
    }

    migrations = {
        "message_id": "INTEGER DEFAULT 0",
        "full_name": "TEXT DEFAULT ''",
        "text": "TEXT DEFAULT ''",
        "score": "REAL DEFAULT 0",
        "created_at": "INTEGER DEFAULT 0",
        "resolved_at": "INTEGER"
    }

    for column, definition in migrations.items():
        if column not in existing:
            conn.execute(
                f"ALTER TABLE tickets ADD COLUMN {column} {definition}"
            )

    # Copy data from the old schema into the new fields.
    conn.execute("""
        UPDATE tickets
        SET text = COALESCE(NULLIF(text, ''), message, ''),
            score = COALESCE(score, severity, 0),
            created_at = CASE
                WHEN created_at IS NULL OR created_at = 0
                THEN CAST(strftime('%s', created) AS INTEGER)
                ELSE created_at
            END
        WHERE
            (text IS NULL OR text = '')
            OR score IS NULL
            OR created_at IS NULL
            OR created_at = 0
    """)

    conn.commit()
    conn.close()


def cleanup_old_tickets():
    border = int(time.time()) - TICKET_DAYS * 86400
    conn = db()

    conn.execute(
        "DELETE FROM tickets WHERE created_at < ? AND status != 'open'",
        (border,)
    )

    conn.execute(
        "DELETE FROM actions WHERE created_at < ?",
        (border,)
    )

    conn.commit()
    conn.close()


# =========================
# HELPERS
# =========================

def is_admin(user_id: int):
    return user_id == ADMIN_ID


def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Тикеты", callback_data="tickets:0")],
        [InlineKeyboardButton(text="🚫 Забаненные", callback_data="bans:0")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
    ])


def ticket_buttons(ticket_id: int, status: str):
    buttons = []

    if status == "open":
        buttons.append([
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{ticket_id}"),
            InlineKeyboardButton(text="🚫 Забанить", callback_data=f"ban:{ticket_id}")
        ])

    buttons.append([
        InlineKeyboardButton(text="↩️ Откатить", callback_data=f"rollback:{ticket_id}")
    ])

    buttons.append([
        InlineKeyboardButton(text="⬅️ К тикетам", callback_data="tickets:0")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_ticket(row):
    created = datetime.fromtimestamp(row["created_at"]).strftime("%d.%m.%Y %H:%M")

    status_map = {
        "open": "🟡 Открыт",
        "approved": "🟢 Одобрен",
        "banned": "🔴 Заблокирован",
        "rolled_back": "↩️ Откат"
    }

    username = f"@{row['username']}" if row["username"] else "нет username"

    return (
        f"🎫 <b>Тикет #{row['id']}</b>\n\n"
        f"👤 <b>{row['full_name']}</b>\n"
        f"🔗 {username}\n"
        f"🆔 <code>{row['user_id']}</code>\n\n"
        f"💬 <b>Сообщение:</b>\n"
        f"{row['text'] or '[без текста]'}\n\n"
        f"📊 Оценка: <b>{row['score']:.2f}</b>\n"
        f"⚠️ Причина: {row['reason']}\n"
        f"🕐 {created}\n"
        f"📌 Статус: {status_map.get(row['status'], row['status'])}"
    )


# =========================
# AI MODERATION
# =========================

def moderate(text: str):
    prompt = f"""
Ты модератор Telegram-чата.

Проанализируй сообщение и верни ТОЛЬКО JSON:

{{
  "score": 0.0,
  "reason": "краткая причина"
}}

Где:
0.0 = полностью безопасное обычное сообщение
1.0 = явное нарушение правил, спам, реклама, мошенничество,
оскорбления, агрессия или другой явно нежелательный контент.

Не наказывай человека за обычное мнение, шутку или нормальное общение.
Не считай одно отдельное грубое слово нарушением без контекста.

Сообщение:
{text}
"""

    try:
        response = requests.post(
            AI_URL,
            json={
                "model": MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "stream": False,
                "format": "json"
            },
            timeout=90
        )

        response.raise_for_status()
        data = response.json()

        content = data["message"]["content"]
        result = json.loads(content)

        score = max(0.0, min(1.0, float(result.get("score", 0))))
        reason = str(result.get("reason", "Не указано"))

        return score, reason

    except Exception as e:
        print("AI ERROR:", e)
        return 0.0, "Ошибка проверки AI"


# =========================
# ADMIN
# =========================

@dp.message(Command("admin"))
async def admin_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    cleanup_old_tickets()

    await message.answer(
        "🛡 <b>Панель модерации</b>\n\n"
        "Здесь можно посмотреть тикеты, баны и статистику.",
        reply_markup=admin_menu()
    )


@dp.callback_query(F.data.startswith("tickets:"))
async def tickets_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    page = int(callback.data.split(":")[1])
    limit = 8
    offset = page * limit

    conn = db()
    rows = conn.execute(
        """
        SELECT *
        FROM tickets
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset)
    ).fetchall()
    conn.close()

    buttons = []

    for row in rows:
        status = {
            "open": "🟡",
            "approved": "🟢",
            "banned": "🔴",
            "rolled_back": "↩️"
        }.get(row["status"], "❔")

        name = row["full_name"][:24]
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} #{row['id']} — {name}",
                callback_data=f"ticket:{row['id']}"
            )
        ])

    nav = []

    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"tickets:{page - 1}"
            )
        )

    if len(rows) == limit:
        nav.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"tickets:{page + 1}"
            )
        )

    if nav:
        buttons.append(nav)

    buttons.append([
        InlineKeyboardButton(text="🏠 Меню", callback_data="menu")
    ])

    await callback.message.edit_text(
        "📋 <b>Тикеты</b>\n\n"
        "Хранение: 30 дней",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("ticket:"))
async def ticket_view(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    ticket_id = int(callback.data.split(":")[1])

    conn = db()
    row = conn.execute(
        "SELECT * FROM tickets WHERE id = ?",
        (ticket_id,)
    ).fetchone()

    if not row:
        conn.close()
        await callback.answer("Тикет не найден", show_alert=True)
        return

    # Контекст
    context = conn.execute(
        """
        SELECT text, username, created_at
        FROM tickets
        WHERE chat_id = ?
        AND created_at BETWEEN ? AND ?
        ORDER BY created_at DESC
        LIMIT 5
        """,
        (
            row["chat_id"],
            row["created_at"] - 600,
            row["created_at"] + 600
        )
    ).fetchall()

    conn.close()

    text = format_ticket(row)

    if context:
        text += "\n\n<b>💬 Контекст:</b>\n"
        for item in reversed(context):
            username = f"@{item['username']}" if item["username"] else "user"
            text += f"• {username}: {item['text'] or '[без текста]'}\n"

    await callback.message.edit_text(
        text,
        reply_markup=ticket_buttons(ticket_id, row["status"])
    )

    await callback.answer()


# =========================
# APPROVE
# =========================

@dp.callback_query(F.data.startswith("approve:"))
async def approve_ticket(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    ticket_id = int(callback.data.split(":")[1])

    conn = db()
    row = conn.execute(
        "SELECT * FROM tickets WHERE id = ?",
        (ticket_id,)
    ).fetchone()

    if not row:
        conn.close()
        await callback.answer("Тикет не найден", show_alert=True)
        return

    conn.execute(
        "UPDATE tickets SET status='approved', action='approved', resolved_at=? WHERE id=?",
        (int(time.time()), ticket_id)
    )

    conn.execute(
        """
        INSERT INTO actions
        (ticket_id, user_id, admin_id, action, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            ticket_id,
            row["user_id"],
            callback.from_user.id,
            "approve",
            int(time.time())
        )
    )

    conn.commit()
    conn.close()

    await callback.answer("Сообщение одобрено")
    await ticket_view(callback)


# =========================
# BAN
# =========================

async def ban_user(ticket_id: int, admin_id: int):
    conn = db()

    row = conn.execute(
        "SELECT * FROM tickets WHERE id=?",
        (ticket_id,)
    ).fetchone()

    if not row:
        conn.close()
        return False

    try:
        await bot.ban_chat_member(
            row["chat_id"],
            row["user_id"]
        )
    except Exception as e:
        print("BAN ERROR:", e)

    conn.execute(
        """
        INSERT OR REPLACE INTO bans
        (user_id, chat_id, username, full_name, reason, ticket_id, banned_at, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            row["user_id"],
            row["chat_id"],
            row["username"],
            row["full_name"],
            row["reason"],
            ticket_id,
            int(time.time())
        )
    )

    conn.execute(
        """
        UPDATE tickets
        SET status='banned', action='ban', resolved_at=?
        WHERE id=?
        """,
        (int(time.time()), ticket_id)
    )

    conn.execute(
        """
        INSERT INTO actions
        (ticket_id, user_id, admin_id, action, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            ticket_id,
            row["user_id"],
            admin_id,
            "ban",
            int(time.time())
        )
    )

    conn.commit()
    conn.close()

    return True


@dp.callback_query(F.data.startswith("ban:"))
async def ban_ticket(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    ticket_id = int(callback.data.split(":")[1])

    await ban_user(ticket_id, callback.from_user.id)

    await callback.answer("Пользователь заблокирован")
    await ticket_view(callback)


# =========================
# ROLLBACK
# =========================

@dp.callback_query(F.data.startswith("rollback:"))
async def rollback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    ticket_id = int(callback.data.split(":")[1])

    conn = db()

    ticket = conn.execute(
        "SELECT * FROM tickets WHERE id=?",
        (ticket_id,)
    ).fetchone()

    if not ticket:
        conn.close()
        await callback.answer("Тикет не найден", show_alert=True)
        return

    if ticket["action"] == "ban":
        try:
            await bot.unban_chat_member(
                ticket["chat_id"],
                ticket["user_id"],
                only_if_banned=True
            )
        except Exception as e:
            print("UNBAN ERROR:", e)

        conn.execute(
            "UPDATE bans SET active=0 WHERE user_id=? AND chat_id=?",
            (ticket["user_id"], ticket["chat_id"])
        )

    conn.execute(
        """
        UPDATE tickets
        SET status='rolled_back',
            action='rollback',
            resolved_at=?
        WHERE id=?
        """,
        (int(time.time()), ticket_id)
    )

    conn.execute(
        """
        UPDATE actions
        SET reverted=1
        WHERE ticket_id=?
        """,
        (ticket_id,)
    )

    conn.commit()
    conn.close()

    await callback.answer("Действие отменено")
    await ticket_view(callback)


# =========================
# BANS
# =========================

@dp.callback_query(F.data.startswith("bans:"))
async def bans_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    page = int(callback.data.split(":")[1])
    limit = 8
    offset = page * limit

    conn = db()
    rows = conn.execute(
        """
        SELECT *
        FROM bans
        WHERE active=1
        ORDER BY banned_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset)
    ).fetchall()
    conn.close()

    buttons = []

    for row in rows:
        name = row["full_name"][:24]
        buttons.append([
            InlineKeyboardButton(
                text=f"🚫 {name}",
                callback_data=f"banuser:{row['user_id']}:{row['chat_id']}"
            )
        ])

    nav = []

    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"bans:{page - 1}"
            )
        )

    if len(rows) == limit:
        nav.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"bans:{page + 1}"
            )
        )

    if nav:
        buttons.append(nav)

    buttons.append([
        InlineKeyboardButton(text="🏠 Меню", callback_data="menu")
    ])

    await callback.message.edit_text(
        "🚫 <b>Забаненные пользователи</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("banuser:"))
async def ban_user_view(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    _, user_id, chat_id = callback.data.split(":")
    user_id = int(user_id)
    chat_id = int(chat_id)

    conn = db()
    row = conn.execute(
        """
        SELECT *
        FROM bans
        WHERE user_id=? AND chat_id=? AND active=1
        """,
        (user_id, chat_id)
    ).fetchone()
    conn.close()

    if not row:
        await callback.answer("Пользователь уже разбанен", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔓 Разбанить",
                callback_data=f"unban:{user_id}:{chat_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🎫 Открыть тикет",
                callback_data=f"ticket:{row['ticket_id']}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="bans:0"
            )
        ]
    ])

    await callback.message.edit_text(
        f"👤 <b>{row['full_name']}</b>\n\n"
        f"🆔 <code>{row['user_id']}</code>\n"
        f"🚫 Забанен\n\n"
        f"⚠️ Причина: {row['reason']}\n"
        f"🎫 Тикет: #{row['ticket_id']}\n"
        f"🕐 {datetime.fromtimestamp(row['banned_at']).strftime('%d.%m.%Y %H:%M')}",
        reply_markup=keyboard
    )

    await callback.answer()


@dp.callback_query(F.data.startswith("unban:"))
async def unban_user(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    _, user_id, chat_id = callback.data.split(":")
    user_id = int(user_id)
    chat_id = int(chat_id)

    try:
        await bot.unban_chat_member(
            chat_id,
            user_id,
            only_if_banned=True
        )
    except Exception as e:
        print("UNBAN ERROR:", e)

    conn = db()

    conn.execute(
        """
        UPDATE bans
        SET active=0
        WHERE user_id=? AND chat_id=?
        """,
        (user_id, chat_id)
    )

    conn.execute(
        """
        UPDATE tickets
        SET status='rolled_back',
            action='unban',
            resolved_at=?
        WHERE id = (
            SELECT ticket_id FROM bans
            WHERE user_id=? AND chat_id=?
            LIMIT 1
        )
        """,
        (int(time.time()), user_id, chat_id)
    )

    conn.commit()
    conn.close()

    await callback.answer("Пользователь разбанен")
    await bans_list(callback)


# =========================
# STATS
# =========================

@dp.callback_query(F.data == "stats")
async def stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    conn = db()

    total = conn.execute(
        "SELECT COUNT(*) FROM tickets"
    ).fetchone()[0]

    open_count = conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE status='open'"
    ).fetchone()[0]

    banned = conn.execute(
        "SELECT COUNT(*) FROM bans WHERE active=1"
    ).fetchone()[0]

    approved = conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE status='approved'"
    ).fetchone()[0]

    conn.close()

    await callback.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"🎫 Всего тикетов: {total}\n"
        f"🟡 Открытых: {open_count}\n"
        f"🟢 Одобрено: {approved}\n"
        f"🚫 Сейчас забанено: {banned}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")]
        ])
    )

    await callback.answer()


@dp.callback_query(F.data == "menu")
async def menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "🛡 <b>Панель модерации</b>",
        reply_markup=admin_menu()
    )

    await callback.answer()


# =========================
# MESSAGE MODERATION
# =========================

@dp.message()
async def moderate_message(message: Message):
    print(
        f"INCOMING MESSAGE: chat_id={message.chat.id} "
        f"user_id={message.from_user.id if message.from_user else None} "
        f"text={message.text!r}",
        flush=True
    )

    if not message.text:
        return

    if message.from_user and is_admin(message.from_user.id):
        return

    try:
        result = await asyncio.to_thread(
            ai_moderate_message,
            message.text
        )

        score = float(result.severity)
        reason = result.reason or "Без объяснения"
        category = result.category
        action = result.action

        print(
            f"[MODERATION] user={message.from_user.id if message.from_user else 0} "
            f"category={category} score={score:.2f} "
            f"action={action} text={message.text[:100]}",
            flush=True
        )

    except Exception as exc:
        print(
            f"[MODERATION ERROR] {type(exc).__name__}: {exc}",
            flush=True
        )
        return

    # Обычные сообщения не создают тикет
    if score < 0.4:
        return

    conn = db()

    conn.execute(
        """
        INSERT INTO tickets
        (chat_id, message_id, user_id, username, full_name,
         text, score, reason, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
        """,
        (
            message.chat.id,
            message.message_id,
            message.from_user.id if message.from_user else 0,
            message.from_user.username if message.from_user else "",
            message.from_user.full_name if message.from_user else "",
            message.text,
            score,
            reason,
            int(time.time())
        )
    )

    ticket_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    # В режиме observe ничего не удаляем и не баним,
    # но тикет и уведомление админу создаём.
    if MODE == "observe":
        action = "review"

    # Автобан
    if AUTO_BAN and MODE != "observe" and score >= 0.7:
        try:
            await bot.ban_chat_member(
                chat_id=message.chat.id,
                user_id=message.from_user.id
            )
            action = "ban"
        except Exception as exc:
            print(
                f"[BAN ERROR] {type(exc).__name__}: {exc}",
                flush=True
            )

    # Уведомление админу
    username = (
        f"@{message.from_user.username}"
        if message.from_user and message.from_user.username
        else message.from_user.full_name
        if message.from_user
        else "Unknown"
    )

    text = (
        f"<b>🚨 Новый тикет</b>\n\n"
        f"<b>Пользователь:</b> {username}\n"
        f"<b>ID:</b> <code>{message.from_user.id if message.from_user else 0}</code>\n"
        f"<b>Категория:</b> {category}\n"
        f"<b>Оценка:</b> {score:.2f}\n"
        f"<b>Действие:</b> {action}\n"
        f"<b>Причина:</b> {reason}\n\n"
        f"<b>Сообщение:</b>\n"
        f"{message.text}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить",
                    callback_data=f"ticket_approve:{message.message_id}"
                ),
                InlineKeyboardButton(
                    text="🚫 Забанить",
                    callback_data=f"ticket_ban:{message.message_id}"
                )
            ]
        ]
    )

    try:
        await bot.send_message(
            ADMIN_ID,
            text,
            reply_markup=keyboard
        )
        print(
            f"[TICKET] sent to admin: message_id={message.message_id}",
            flush=True
        )
    except Exception as exc:
        print(
            f"[TICKET ERROR] {type(exc).__name__}: {exc}",
            flush=True
        )



async def cleanup_loop():
    while True:
        try:
            cleanup_old_tickets()
        except Exception as e:
            print(f"[CLEANUP] error: {e}", flush=True)
        await asyncio.sleep(86400)


async def main():
    init_db()
    cleanup_old_tickets()

    print("================================")
    print("Moderation bot started")
    print(f"Model: {MODEL}")
    print(f"AI URL: {AI_URL}")
    print(f"Mode: {MODE}")
    print(f"Auto ban: {AUTO_BAN}")
    print("Tickets retention: 30 days")
    print("================================")

    asyncio.create_task(cleanup_loop())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
