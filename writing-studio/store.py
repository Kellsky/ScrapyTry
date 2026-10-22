"""Small durable store for the single-user prototype."""
import json
import os
import sqlite3
import threading
from pathlib import Path


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory = directory
        self.path = directory / 'studio.sqlite3'
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        os.chmod(self.path, 0o600)
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        self.connection.execute('CREATE TABLE IF NOT EXISTS config (name TEXT PRIMARY KEY, data TEXT NOT NULL)')
        self.connection.commit()

    def get_config(self, name, default=None):
        with self.lock:
            row = self.connection.execute('SELECT data FROM config WHERE name=?', (name,)).fetchone()
            return json.loads(row[0]) if row else default

    def set_config(self, name, data):
        with self.lock:
            self.connection.execute('INSERT OR REPLACE INTO config VALUES (?, ?)', (name, json.dumps(data, ensure_ascii=False)))
            self.connection.commit()

    def save(self, task):
        with self.lock:
            self.connection.execute('INSERT OR REPLACE INTO tasks VALUES (?, ?)', (task['id'], json.dumps(task, ensure_ascii=False)))
            self.connection.commit()

    def get(self, task_id):
        with self.lock:
            row = self.connection.execute('SELECT data FROM tasks WHERE id=?', (task_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def all(self):
        with self.lock:
            rows = self.connection.execute('SELECT data FROM tasks ORDER BY rowid DESC').fetchall()
            return [json.loads(row[0]) for row in rows]

    def delete(self, task_id):
        with self.lock:
            self.connection.execute('DELETE FROM tasks WHERE id=?', (task_id,))
            self.connection.commit()

    def close(self):
        self.connection.close()
