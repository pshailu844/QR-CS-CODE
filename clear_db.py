import os
import sqlite3

DB_PATH = os.environ.get("APP_DB_PATH", os.path.join(os.getcwd(), "app.db"))

def main() -> None:
	conn = sqlite3.connect(DB_PATH)
	try:
		cur = conn.cursor()
		cur.execute("DELETE FROM submissions")
		cur.execute("DELETE FROM requests")
		cur.execute("DELETE FROM settings")
		conn.commit()
		print("Database cleared: submissions, requests, settings")
	except Exception as exc:
		print(f"Error: {exc}")
	finally:
		conn.close()

if __name__ == "__main__":
	main()


