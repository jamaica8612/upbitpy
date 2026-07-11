"""SQLite metadata store: strategies, backtest runs, optimization runs.

Candle data lives in Parquet; this DB only holds strategy definitions and
run records (including the strategy snapshot taken at run time so editing a
strategy never rewrites past results).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS strategies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    definition TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backtests (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    config TEXT NOT NULL,
    strategy_snapshot TEXT NOT NULL,
    progress TEXT,
    result TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS optimizations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    config TEXT NOT NULL,
    progress TEXT,
    result TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class MetaDB:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings.sqlite_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as con:
            con.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ---- strategies ------------------------------------------------------

    def create_strategy(self, name: str, definition: dict[str, Any]) -> dict[str, Any]:
        sid = str(uuid.uuid4())
        now = self._now()
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT INTO strategies (id, name, definition, created_at, updated_at) VALUES (?,?,?,?,?)",
                (sid, name, json.dumps(definition, ensure_ascii=False), now, now),
            )
        return self.get_strategy(sid)  # type: ignore[return-value]

    def update_strategy(self, sid: str, name: str, definition: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock, self._connect() as con:
            cur = con.execute(
                "UPDATE strategies SET name=?, definition=?, updated_at=? WHERE id=?",
                (name, json.dumps(definition, ensure_ascii=False), self._now(), sid),
            )
            if cur.rowcount == 0:
                return None
        return self.get_strategy(sid)

    def get_strategy(self, sid: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM strategies WHERE id=?", (sid,)).fetchone()
        return self._strategy_row(row) if row else None

    def list_strategies(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM strategies ORDER BY updated_at DESC").fetchall()
        return [self._strategy_row(r) for r in rows]

    def delete_strategy(self, sid: str) -> bool:
        with self._lock, self._connect() as con:
            cur = con.execute("DELETE FROM strategies WHERE id=?", (sid,))
            return cur.rowcount > 0

    @staticmethod
    def _strategy_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "definition": json.loads(row["definition"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # ---- runs (backtests & optimizations share shape) ---------------------

    def create_run(self, table: str, config: dict[str, Any], strategy_snapshot: dict[str, Any] | None = None) -> str:
        rid = str(uuid.uuid4())
        with self._lock, self._connect() as con:
            if table == "backtests":
                con.execute(
                    "INSERT INTO backtests (id, created_at, status, config, strategy_snapshot) VALUES (?,?,?,?,?)",
                    (rid, self._now(), "queued", json.dumps(config, ensure_ascii=False),
                     json.dumps(strategy_snapshot or {}, ensure_ascii=False)),
                )
            else:
                con.execute(
                    "INSERT INTO optimizations (id, created_at, status, config) VALUES (?,?,?,?)",
                    (rid, self._now(), "queued", json.dumps(config, ensure_ascii=False)),
                )
        return rid

    def update_run(
        self,
        table: str,
        rid: str,
        status: str | None = None,
        progress: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        sets, vals = [], []
        if status is not None:
            sets.append("status=?")
            vals.append(status)
        if progress is not None:
            sets.append("progress=?")
            vals.append(json.dumps(progress, ensure_ascii=False))
        if result is not None:
            sets.append("result=?")
            vals.append(json.dumps(result, ensure_ascii=False, default=str))
        if error is not None:
            sets.append("error=?")
            vals.append(error)
        if not sets:
            return
        vals.append(rid)
        with self._lock, self._connect() as con:
            con.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id=?", vals)  # noqa: S608 - table is internal

    def get_run(self, table: str, rid: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(f"SELECT * FROM {table} WHERE id=?", (rid,)).fetchone()  # noqa: S608
        if not row:
            return None
        out = {
            "id": row["id"],
            "created_at": row["created_at"],
            "status": row["status"],
            "config": json.loads(row["config"]),
            "progress": json.loads(row["progress"]) if row["progress"] else None,
            "result": json.loads(row["result"]) if row["result"] else None,
            "error": row["error"],
        }
        if table == "backtests":
            out["strategy_snapshot"] = json.loads(row["strategy_snapshot"])
        return out

    def list_runs(self, table: str, limit: int = 50, summary: bool = True) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                f"SELECT * FROM {table} ORDER BY created_at DESC LIMIT ?", (limit,)  # noqa: S608
            ).fetchall()
        out = []
        for row in rows:
            item = self.get_run(table, row["id"])
            if item and summary and item.get("result"):
                # keep the list light: strip heavy arrays
                r = dict(item["result"])
                for heavy in ("equity_curve", "trades", "drawdown_curve", "buy_hold_curve", "candles", "results"):
                    r.pop(heavy, None)
                item["result"] = r
            out.append(item)
        return out

    # ---- settings ----------------------------------------------------------

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._connect() as con:
            row = con.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT INTO app_settings (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )


db = MetaDB()
