import sqlite3

class Database:
    def __init__(self, db_file):
        self.connection = sqlite3.connect(db_file)
        self.cursor = self.connection.cursor()
        self.create_table()

    def create_table(self):
        with self.connection:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    user_name TEXT,
                    balance REAL DEFAULT 0.0,
                    current_video INTEGER DEFAULT 1
                )
            """)

    def user_exists(self, user_id):
        with self.connection:
            result = self.cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return bool(result)

    def add_user(self, user_id, user_name):
        with self.connection:
            self.cursor.execute("INSERT INTO users (user_id, user_name) VALUES (?, ?)", (user_id, user_name))

    def get_user(self, user_id):
        with self.connection:
            return self.cursor.execute("SELECT balance, current_video FROM users WHERE user_id = ?", (user_id,)).fetchone()

    def update_user(self, user_id, balance, current_video):
        with self.connection:
            self.cursor.execute("UPDATE users SET balance = ?, current_video = ? WHERE user_id = ?", (balance, current_video, user_id))

    def get_stats(self):
        with self.connection:
            total_users = self.cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            total_balance = self.cursor.execute("SELECT SUM(balance) FROM users").fetchone()[0] or 0
            return total_users, total_balance

    def get_all_users(self):
        with self.connection:
            return [row[0] for row in self.cursor.execute("SELECT user_id FROM users").fetchall()]