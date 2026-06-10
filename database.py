import aiosqlite
import datetime


class Database:
    def __init__(self, db_file):
        self.db_file = db_file

    async def create_table(self):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    user_name TEXT,
                    balance REAL DEFAULT 0.0,
                    current_video INTEGER DEFAULT 1
                )
            """)
            # send_weekday: 0=Пн, 1=Вт, 2=Ср, 3=Чт, 4=Пт, 5=Сб, 6=Вс
            await db.execute("""
                CREATE TABLE IF NOT EXISTS push_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    text TEXT,
                    file_id TEXT,
                    send_weekday INTEGER NOT NULL,
                    send_time TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1
                )
            """)
            await db.commit()

    # ───── ПОЛЬЗОВАТЕЛИ ─────

    async def user_exists(self, user_id):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                return bool(await cursor.fetchone())

    async def add_user(self, user_id, user_name):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute(
                "INSERT INTO users (user_id, user_name) VALUES (?, ?)",
                (user_id, user_name)
            )
            await db.commit()

    async def get_user(self, user_id):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute(
                "SELECT balance, current_video FROM users WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                return await cursor.fetchone()

    async def update_user(self, user_id, balance, current_video):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute(
                "UPDATE users SET balance = ?, current_video = ? WHERE user_id = ?",
                (balance, current_video, user_id)
            )
            await db.commit()

    async def get_stats(self):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                total_users = (await cursor.fetchone())[0]
            async with db.execute("SELECT SUM(balance) FROM users") as cursor:
                total_balance = (await cursor.fetchone())[0] or 0
            return total_users, total_balance

    async def get_all_users(self):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute("SELECT user_id FROM users") as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

    # ───── ПУШ-УВЕДОМЛЕНИЯ ─────

    async def add_push(self, title: str, content_type: str,
                       send_weekday: int, send_time: str,
                       text: str = None, file_id: str = None):
        created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute(
                """INSERT INTO push_notifications
                   (title, content_type, text, file_id, send_weekday, send_time, created_at, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                (title, content_type, text, file_id, send_weekday, send_time, created_at)
            )
            await db.commit()

    async def update_push(self, push_id: int, title: str, content_type: str,
                          send_weekday: int, send_time: str,
                          text: str = None, file_id: str = None):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute(
                """UPDATE push_notifications
                   SET title=?, content_type=?, text=?, file_id=?,
                       send_weekday=?, send_time=?, is_active=1
                   WHERE id=?""",
                (title, content_type, text, file_id, send_weekday, send_time, push_id)
            )
            await db.commit()

    async def get_all_pushes(self):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute(
                """SELECT id, title, content_type, send_weekday, send_time, is_active
                   FROM push_notifications ORDER BY id DESC"""
            ) as cursor:
                return await cursor.fetchall()

    async def get_push_by_id(self, push_id: int):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute(
                """SELECT id, title, content_type, text, file_id,
                          send_weekday, send_time, is_active
                   FROM push_notifications WHERE id = ?""",
                (push_id,)
            ) as cursor:
                return await cursor.fetchone()

    async def get_active_pushes_for_schedule(self, weekday: int, send_time: str):
        """Активные пуши на конкретный день недели и время."""
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute(
                """SELECT id, title, content_type, text, file_id
                   FROM push_notifications
                   WHERE is_active = 1 AND send_weekday = ? AND send_time = ?""",
                (weekday, send_time)
            ) as cursor:
                return await cursor.fetchall()

    async def deactivate_push(self, push_id: int):
        """Отключить пуш после отправки (одноразовый)."""
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute(
                "UPDATE push_notifications SET is_active = 0 WHERE id = ?",
                (push_id,)
            )
            await db.commit()

    async def delete_push(self, push_id: int):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute(
                "DELETE FROM push_notifications WHERE id = ?", (push_id,)
            )
            await db.commit()

    async def toggle_push(self, push_id: int):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute(
                "SELECT is_active FROM push_notifications WHERE id = ?", (push_id,)
            ) as cursor:
                row = await cursor.fetchone()
            if row is None:
                return None
            new_status = 0 if row[0] == 1 else 1
            await db.execute(
                "UPDATE push_notifications SET is_active = ? WHERE id = ?",
                (new_status, push_id)
            )
            await db.commit()
            return new_status