"""Privacy-conscious import of daily step totals exported by health devices."""
from contextlib import closing
from datetime import date

from fitlog_store import DB_FILE, _connect, init_db

SUPPORTED_SOURCES = {
    "fitbit", "garmin", "apple_health", "google_health_connect", "other"
}


def init_device_db(db_file=DB_FILE):
    """Create additive device tables without changing existing workout records."""
    init_db(db_file)
    with closing(_connect(db_file)) as conn, conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS device_daily_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source TEXT NOT NULL CHECK(source IN ('fitbit','garmin','apple_health','google_health_connect','other')),
            activity_date TEXT NOT NULL,
            steps INTEGER NOT NULL CHECK(steps >= 0),
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, source, activity_date))""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_device_steps_user_date ON device_daily_steps(user_id,activity_date)")


def import_daily_steps(user_id, source, records, db_file=DB_FILE):
    """Import actual exported readings, upserting one daily total per source."""
    init_device_db(db_file)
    source = str(source or "").strip().lower()
    if source not in SUPPORTED_SOURCES:
        raise ValueError("Choose a supported device data source.")
    if not isinstance(records, (list, tuple)) or not records:
        raise ValueError("The CSV has no step records to import.")

    clean = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        try:
            activity_date = date.fromisoformat(str(record["date"]).strip()).isoformat()
            raw_steps = float(record["steps"])
            steps = int(raw_steps)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if raw_steps != steps or steps < 0:
            continue
        clean[activity_date] = steps
    if not clean:
        raise ValueError("No valid rows found. Dates must use YYYY-MM-DD and steps must be a non-negative whole number.")

    added = updated = 0
    with closing(_connect(db_file)) as conn, conn:
        for activity_date, steps in clean.items():
            existing = conn.execute(
                "SELECT id FROM device_daily_steps WHERE user_id=? AND source=? AND activity_date=?",
                (user_id, source, activity_date),
            ).fetchone()
            conn.execute("""INSERT INTO device_daily_steps(user_id,source,activity_date,steps)
                VALUES(?,?,?,?) ON CONFLICT(user_id,source,activity_date) DO UPDATE SET
                steps=excluded.steps,imported_at=CURRENT_TIMESTAMP""",
                (user_id, source, activity_date, steps))
            if existing: updated += 1
            else: added += 1
    return {"added": added, "updated": updated, "total": len(clean)}


def list_daily_steps(user_id, start_date=None, end_date=None, db_file=DB_FILE):
    init_device_db(db_file)
    query = "SELECT id,source,activity_date,steps,imported_at FROM device_daily_steps WHERE user_id=?"
    params = [user_id]
    if start_date:
        query += " AND activity_date>=?"; params.append(date.fromisoformat(str(start_date)).isoformat())
    if end_date:
        query += " AND activity_date<=?"; params.append(date.fromisoformat(str(end_date)).isoformat())
    query += " ORDER BY activity_date DESC,source"
    with closing(_connect(db_file)) as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]
