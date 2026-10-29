"""Storage layer: where operational tasks are saved.

Two interchangeable stores share the same methods:
- PostgresStore: the real database, used in Docker Compose.
- MemoryStore: a Python dict, used by the automated tests so they need no database.
"""

import psycopg
from psycopg.rows import dict_row


class MemoryStore:
    def __init__(self):
        self.tasks = {}
        self.next_id = 1

    def init_schema(self):
        pass

    def is_ready(self):
        return True

    def create_task(self, title, priority):
        task = {"id": self.next_id, "title": title, "priority": priority, "status": "open"}
        self.tasks[self.next_id] = task
        self.next_id += 1
        return task

    def list_tasks(self):
        return list(self.tasks.values())

    def get_task(self, task_id):
        return self.tasks.get(task_id)


class PostgresStore:
    def __init__(self, dsn):
        self.dsn = dsn

    def _connect(self):
        # connect_timeout stops a request hanging forever if the database is down
        return psycopg.connect(self.dsn, connect_timeout=3, row_factory=dict_row)

    def init_schema(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open'
                )
                """
            )

    def is_ready(self):
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1")
            return True
        except psycopg.Error:
            return False

    def create_task(self, title, priority):
        with self._connect() as conn:
            return conn.execute(
                "INSERT INTO tasks (title, priority) VALUES (%s, %s) "
                "RETURNING id, title, priority, status",
                (title, priority),
            ).fetchone()

    def list_tasks(self):
        with self._connect() as conn:
            return conn.execute(
                "SELECT id, title, priority, status FROM tasks ORDER BY id"
            ).fetchall()

    def get_task(self, task_id):
        with self._connect() as conn:
            return conn.execute(
                "SELECT id, title, priority, status FROM tasks WHERE id = %s", (task_id,)
            ).fetchone()


def build_store(database_url):
    if database_url == "memory://":
        return MemoryStore()
    return PostgresStore(database_url)
