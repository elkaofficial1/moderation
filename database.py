import sqlite3
from datetime import datetime, timezone


class Database:
    def __init__(self, path="data/moderation.db"):
        self.path = path
        self._init()

    def connect(self):
        return sqlite3.connect(self.path)

    def _init(self):
        db = self.connect()
        cur = db.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            message_id INTEGER,
            user_id INTEGER,
            username TEXT,
            full_name TEXT,
            text TEXT,
            category TEXT,
            severity REAL,
            action TEXT,
            reason TEXT,
            created_at TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            message_id INTEGER,
            user_id INTEGER,
            category TEXT,
            severity REAL,
            reason TEXT,
            status TEXT DEFAULT 'new',
            created_at TEXT,
            resolved_at TEXT,
            moderator_id INTEGER
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            ticket_id INTEGER,
            reason TEXT,
            created_at TEXT,
            unbanned_at TEXT,
            unbanned_by INTEGER
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)

        db.commit()
        db.close()

    def save_message(self, message, result):
        db = self.connect()
        db.execute(
            """
            INSERT INTO messages (
                chat_id, message_id, user_id, username,
                full_name, text, category, severity,
                action, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.chat.id,
                message.message_id,
                message.from_user.id,
                message.from_user.username or "",
                message.from_user.full_name,
                message.text or message.caption or "",
                result.category,
                result.severity,
                result.action,
                result.reason,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        db.commit()
        db.close()

    def create_ticket(self, message, result):
        db = self.connect()
        cur = db.cursor()

        cur.execute(
            """
            INSERT INTO tickets (
                chat_id, message_id, user_id,
                category, severity, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.chat.id,
                message.message_id,
                message.from_user.id,
                result.category,
                result.severity,
                result.reason,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        ticket_id = cur.lastrowid
        db.commit()
        db.close()
        return ticket_id

    def resolve_ticket(self, ticket_id, status, moderator_id):
        db = self.connect()
        db.execute(
            """
            UPDATE tickets
            SET status = ?, resolved_at = ?, moderator_id = ?
            WHERE id = ?
            """,
            (
                status,
                datetime.now(timezone.utc).isoformat(),
                moderator_id,
                ticket_id,
            ),
        )
        db.commit()
        db.close()

    def add_ban(self, chat_id, user_id, ticket_id, reason, moderator_id):
        db = self.connect()
        db.execute(
            """
            INSERT INTO bans (
                chat_id, user_id, ticket_id, reason, created_at, unbanned_by
            ) VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (
                chat_id,
                user_id,
                ticket_id,
                reason,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        db.commit()
        db.close()

    def mark_unban(self, chat_id, user_id, moderator_id):
        db = self.connect()
        db.execute(
            """
            UPDATE bans
            SET unbanned_at = ?, unbanned_by = ?
            WHERE chat_id = ? AND user_id = ? AND unbanned_at IS NULL
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                moderator_id,
                chat_id,
                user_id,
            ),
        )
        db.commit()
        db.close()

    def stats(self):
        db = self.connect()
        rows = db.execute(
            """
            SELECT category, COUNT(*)
            FROM messages
            GROUP BY category
            ORDER BY COUNT(*) DESC
            """
        ).fetchall()

        tickets = db.execute(
            "SELECT COUNT(*) FROM tickets WHERE status = 'new'"
        ).fetchone()[0]

        bans = db.execute(
            "SELECT COUNT(*) FROM bans"
        ).fetchone()[0]

        messages = db.execute(
            "SELECT COUNT(*) FROM messages"
        ).fetchone()[0]

        db.close()

        return {
            "messages": messages,
            "tickets": tickets,
            "bans": bans,
            "categories": rows,
        }

    def recent_tickets(self, limit=10):
        db = self.connect()
        rows = db.execute(
            """
            SELECT id, user_id, category, severity, reason, status, created_at
            FROM tickets
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        db.close()
        return rows

    def get_ticket(self, ticket_id):
        db = self.connect()
        row = db.execute(
            "SELECT * FROM tickets WHERE id = ?",
            (ticket_id,),
        ).fetchone()
        db.close()
        return row
