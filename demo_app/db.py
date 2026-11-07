import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, Optional

DEFAULT_DB_PATH = os.getenv("SWITCHGUARD_DB_PATH", "./data/switchguard.db")
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "blueprint" / "schema.sql"


def get_db_path(custom_path: Optional[str] = None) -> str:
    return custom_path or os.getenv("SWITCHGUARD_DB_PATH", DEFAULT_DB_PATH)


@contextmanager
def get_db(custom_path: Optional[str] = None):
    db_file = Path(get_db_path(custom_path))
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file), timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(custom_path: Optional[str] = None) -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_db(custom_path) as conn:
        conn.executescript(schema_sql)
        conn.execute("PRAGMA foreign_keys = ON;")


def get_service_state(custom_path: Optional[str] = None) -> Dict[str, Any]:
    with get_db(custom_path) as conn:
        row = conn.execute(
            "SELECT service_name, active_version, fault_mode_enabled FROM runtime_config WHERE config_id = 1"
        ).fetchone()
        if not row:
            return {
                "service": "cart-service",
                "active_version": "v2.14.0",
                "fault_mode_enabled": True,
                "status": "degraded",
            }
        fault = bool(row["fault_mode_enabled"]) and row["active_version"] == "v2.14.0"
        return {
            "service": row["service_name"],
            "active_version": row["active_version"],
            "fault_mode_enabled": fault,
            "status": "degraded" if fault else "healthy",
        }


def update_service_version(target_version: str, fault_enabled: bool, custom_path: Optional[str] = None) -> Dict[str, Any]:
    with get_db(custom_path) as conn:
        conn.execute(
            """
            UPDATE runtime_config
            SET active_version = ?, fault_mode_enabled = ?, updated_at = CURRENT_TIMESTAMP
            WHERE config_id = 1
            """,
            (target_version, 1 if fault_enabled else 0),
        )
    return get_service_state(custom_path)
