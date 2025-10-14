import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

DB_PATH = os.environ.get("APP_DB_PATH", os.path.join(os.getcwd(), "app.db"))


def _dict_factory(cursor: sqlite3.Cursor, row: Tuple[Any, ...]) -> Dict[str, Any]:
	return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def _connect() -> sqlite3.Connection:
	conn = sqlite3.connect(DB_PATH, check_same_thread=False)
	conn.row_factory = _dict_factory
	return conn


@contextmanager
def get_conn() -> Iterable[sqlite3.Connection]:
	conn = _connect()
	try:
		yield conn
	finally:
		conn.commit()
		conn.close()


def init_db() -> None:
	with get_conn() as conn:
		cur = conn.cursor()
		# settings
		cur.execute(
			"""
			CREATE TABLE IF NOT EXISTS settings (
				key TEXT PRIMARY KEY,
				value TEXT
			)
			"""
		)
		# requests
		cur.execute(
			"""
			CREATE TABLE IF NOT EXISTS requests (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				title TEXT NOT NULL,
				description TEXT,
				status TEXT NOT NULL DEFAULT 'open',
				token TEXT UNIQUE NOT NULL,
				created_at TEXT NOT NULL,
				one_time_use INTEGER DEFAULT 0,
				used_count INTEGER DEFAULT 0
			)
			"""
		)
		# submissions
		cur.execute(
			"""
			CREATE TABLE IF NOT EXISTS submissions (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				request_id INTEGER NOT NULL,
				name TEXT NOT NULL,
				phone TEXT NOT NULL,
				email TEXT,
				created_at TEXT NOT NULL,
				FOREIGN KEY(request_id) REFERENCES requests(id)
			)
			"""
		)
		
		# Add new columns to existing requests table if they don't exist
		try:
			cur.execute("ALTER TABLE requests ADD COLUMN one_time_use INTEGER DEFAULT 0")
		except:
			pass  # Column already exists
		
		try:
			cur.execute("ALTER TABLE requests ADD COLUMN used_count INTEGER DEFAULT 0")
		except:
			pass  # Column already exists
		
		# Fix email column to allow NULL
		try:
			cur.execute("ALTER TABLE submissions ALTER COLUMN email DROP NOT NULL")
		except:
			pass  # Column already allows NULL
		
		conn.commit()


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
	with get_conn() as conn:
		cur = conn.cursor()
		cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
		row = cur.fetchone()
		return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
	with get_conn() as conn:
		cur = conn.cursor()
		cur.execute(
			"INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
			(key, value),
		)


def create_request(title: str, description: str, token: str) -> Dict[str, Any]:
	now = datetime.utcnow().isoformat()
	with get_conn() as conn:
		cur = conn.cursor()
		cur.execute(
			"INSERT INTO requests(title, description, status, token, created_at) VALUES(?, ?, 'open', ?, ?)",
			(title, description, token, now),
		)
		rid = cur.lastrowid
		cur.execute("SELECT * FROM requests WHERE id = ?", (rid,))
		return cur.fetchone()


def list_requests(status: Optional[str] = None) -> List[Dict[str, Any]]:
	with get_conn() as conn:
		cur = conn.cursor()
		if status:
			cur.execute("SELECT * FROM requests WHERE status = ? ORDER BY created_at DESC", (status,))
		else:
			cur.execute("SELECT * FROM requests ORDER BY created_at DESC")
		return cur.fetchall()


def get_request_by_token(token: str) -> Optional[Dict[str, Any]]:
	with get_conn() as conn:
		cur = conn.cursor()
		cur.execute("SELECT * FROM requests WHERE token = ?", (token,))
		return cur.fetchone()


def update_request_status(request_id: int, status: str) -> None:
	with get_conn() as conn:
		cur = conn.cursor()
		cur.execute("UPDATE requests SET status = ? WHERE id = ?", (status, request_id))


def delete_request(request_id: int) -> None:
	with get_conn() as conn:
		cur = conn.cursor()
		cur.execute("DELETE FROM submissions WHERE request_id = ?", (request_id,))
		cur.execute("DELETE FROM requests WHERE id = ?", (request_id,))


def add_submission(request_id: int, name: str, phone: str, email: str) -> Dict[str, Any]:
	now = datetime.utcnow().isoformat()
	with get_conn() as conn:
		cur = conn.cursor()
		
		# Check for duplicate phone number in the same request
		cur.execute("SELECT id FROM submissions WHERE request_id = ? AND phone = ?", (request_id, phone))
		existing = cur.fetchone()
		if existing:
			raise ValueError("A submission with this phone number already exists for this request")
		
		cur.execute(
			"INSERT INTO submissions(request_id, name, phone, email, created_at) VALUES(?, ?, ?, ?, ?)",
			(request_id, name, phone, email, now),
		)
		sid = cur.lastrowid
		cur.execute("SELECT * FROM submissions WHERE id = ?", (sid,))
		return cur.fetchone()


def list_submissions(request_id: int) -> List[Dict[str, Any]]:
	with get_conn() as conn:
		cur = conn.cursor()
		cur.execute("SELECT * FROM submissions WHERE request_id = ? ORDER BY created_at DESC", (request_id,))
		return cur.fetchall()


def is_token_used(token: str) -> bool:
	"""Check if token has been used (for one-time use)"""
	with get_conn() as conn:
		cur = conn.cursor()
		cur.execute("SELECT one_time_use, used_count FROM requests WHERE token = ?", (token,))
		row = cur.fetchone()
		if row and row["one_time_use"] == 1 and row["used_count"] > 0:
			return True
		return False


def mark_token_used(token: str) -> None:
	"""Mark token as used (increment used_count)"""
	with get_conn() as conn:
		cur = conn.cursor()
		cur.execute("UPDATE requests SET used_count = used_count + 1 WHERE token = ?", (token,))


def set_one_time_use(request_id: int, one_time: bool) -> None:
	"""Set whether a request is one-time use"""
	with get_conn() as conn:
		cur = conn.cursor()
		cur.execute("UPDATE requests SET one_time_use = ? WHERE id = ?", (1 if one_time else 0, request_id))


def wipe_database() -> None:
    """Delete all data from settings, submissions, and requests tables."""
    with get_conn() as conn:
        cur = conn.cursor()
        # Order matters due to FK from submissions -> requests
        cur.execute("DELETE FROM submissions")
        cur.execute("DELETE FROM requests")
        cur.execute("DELETE FROM settings")
