import aiosqlite

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
            await db.commit()

    async def user_exists(self, user_id):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)) as cursor:
                result = await cursor.fetchone()
                return bool(result)

    async def add_user(self, user_id, user_name):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("INSERT INTO users (user_id, user_name) VALUES (?, ?)", (user_id, user_name))
            await db.commit()

    async def get_user(self, user_id):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute("SELECT balance, current_video FROM users WHERE user_id = ?", (user_id,)) as cursor:
                return await cursor.fetchone()

    async def update_user(self, user_id, balance, current_video):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("UPDATE users SET balance = ?, current_video = ? WHERE user_id = ?", (balance, current_video, user_id))
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