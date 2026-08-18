"""
Слой доступа к данным на чистом sqlite3 (стандартная библиотека Python —
без внешних зависимостей, поэтому сервис разворачивается без шага `pip
install` и без риска конфликтов версий).

Схема простая: одна таблица `companies`. Скор пересчитывается в scoring.py
при каждой вставке/обновлении, поэтому рейтинг всегда согласован.
"""
import os
import sqlite3
import threading

from .scoring import compute_score

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "startups.db"),
)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

_local = threading.local()

FIELDS = [
    "name", "sector", "founded", "rev", "rev_year", "growth", "growth_note",
    "funding_rub", "funding_note", "investors", "desc", "note",
    "source_name", "source_url",
    "is_ipo", "is_official_rank", "is_major_investor",
    "category", "status", "confidence",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sector TEXT NOT NULL,
    founded INTEGER,
    rev REAL,
    rev_year INTEGER,
    growth REAL,
    growth_note TEXT,
    funding_rub REAL,
    funding_note TEXT,
    investors TEXT,
    desc TEXT,
    note TEXT,
    source_name TEXT,
    source_url TEXT,
    is_ipo INTEGER DEFAULT 0,
    is_official_rank INTEGER DEFAULT 0,
    is_major_investor INTEGER DEFAULT 0,
    category TEXT DEFAULT 'domestic',
    status TEXT DEFAULT 'active',
    confidence TEXT DEFAULT 'medium',
    score REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_companies_sector ON companies(sector);
CREATE INDEX IF NOT EXISTS idx_companies_score ON companies(score);
CREATE INDEX IF NOT EXISTS idx_companies_category_status ON companies(category, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_name_sector ON companies(name, sector);
"""


def get_conn():
    """Одно соединение на поток (sqlite3-объекты не потокобезопасны между потоками)."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # WAL позволяет читать во время записи и снижает риск "database is locked"
        # при параллельных запросах от нескольких потоков ThreadingHTTPServer.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 10000")
        _local.conn = conn
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["is_ipo"] = bool(d["is_ipo"])
    d["is_official_rank"] = bool(d["is_official_rank"])
    d["is_major_investor"] = bool(d["is_major_investor"])
    return d


def _clean(data: dict) -> dict:
    """Оставляет только известные поля, остальное игнорируется."""
    return {k: data[k] for k in FIELDS if k in data}


def list_companies(sector=None, search=None, category="domestic", status="active",
                    limit=100, offset=0, sort_by="score", sort_dir="desc"):
    allowed_sort = {"score", "rev", "growth", "funding_rub", "founded", "name"}
    if sort_by not in allowed_sort:
        sort_by = "score"
    sort_dir = "DESC" if sort_dir != "asc" else "ASC"

    where = []
    params = []
    if sector:
        where.append("sector = ?")
        params.append(sector)
    if category:
        where.append("category = ?")
        params.append(category)
    if status:
        where.append("status = ?")
        params.append(status)
    if search:
        where.append("(name LIKE ? OR desc LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    conn = get_conn()

    total = conn.execute(f"SELECT COUNT(*) FROM companies {where_sql}", params).fetchone()[0]

    # NULLS LAST не во всех сборках sqlite доступен единым синтаксисом — эмулируем через CASE.
    rows = conn.execute(
        f"""SELECT * FROM companies {where_sql}
            ORDER BY ({sort_by} IS NULL), {sort_by} {sort_dir}
            LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()
    return [_row_to_dict(r) for r in rows], total


def get_company(company_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    return _row_to_dict(row) if row else None


def find_by_name_sector(name: str, sector: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM companies WHERE name = ? AND sector = ?", (name, sector)
    ).fetchone()
    return _row_to_dict(row) if row else None


def _score_for(data: dict) -> float:
    return compute_score(
        data.get("rev"), data.get("growth"), data.get("funding_rub"),
        data.get("is_ipo", False), data.get("is_official_rank", False), data.get("is_major_investor", False),
    )


def create_company(data: dict) -> dict:
    data = _clean(data)
    data.setdefault("category", "domestic")
    data.setdefault("status", "active")
    data.setdefault("confidence", "medium")
    score = _score_for(data)

    cols = list(data.keys()) + ["score"]
    placeholders = ", ".join("?" for _ in cols)
    values = [data[c] for c in data.keys()] + [score]

    conn = get_conn()
    cur = conn.execute(
        f"INSERT INTO companies ({', '.join(cols)}) VALUES ({placeholders})", values
    )
    conn.commit()
    return get_company(cur.lastrowid)


def update_company(company_id: int, data: dict) -> dict | None:
    existing = get_company(company_id)
    if not existing:
        return None
    data = _clean(data)
    merged = {**existing, **data}
    score = _score_for(merged)

    set_clause = ", ".join(f"{k} = ?" for k in data.keys())
    values = list(data.values()) + [score, company_id]
    conn = get_conn()
    conn.execute(
        f"UPDATE companies SET {set_clause}, score = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        values,
    )
    conn.commit()
    return get_company(company_id)


def delete_company(company_id: int) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM companies WHERE id = ?", (company_id,))
    conn.commit()
    return cur.rowcount > 0


def bulk_upsert(items: list[dict]):
    created, updated = 0, 0
    for item in items:
        existing = find_by_name_sector(item["name"], item["sector"])
        if existing:
            update_company(existing["id"], item)
            updated += 1
        else:
            create_company(item)
            created += 1
    return created, updated


def sector_counts(category="domestic", status="active"):
    conn = get_conn()
    rows = conn.execute(
        "SELECT sector, COUNT(*) as n FROM companies WHERE category = ? AND status = ? GROUP BY sector ORDER BY n DESC",
        (category, status),
    ).fetchall()
    return [[r["sector"], r["n"]] for r in rows]


def stats(category="domestic", status="active"):
    conn = get_conn()
    row = conn.execute(
        """SELECT COUNT(*) as total,
                  COUNT(rev) as n_rev, COALESCE(SUM(rev), 0) as sum_rev,
                  COUNT(funding_rub) as n_funding, COALESCE(SUM(funding_rub), 0) as sum_funding
           FROM companies WHERE category = ? AND status = ?""",
        (category, status),
    ).fetchone()
    n_sectors = conn.execute(
        "SELECT COUNT(DISTINCT sector) FROM companies WHERE category = ? AND status = ?",
        (category, status),
    ).fetchone()[0]
    return {
        "total_companies": row["total"],
        "total_sectors": n_sectors,
        "total_revenue_mln": round(row["sum_rev"], 1),
        "n_revenue_known": row["n_rev"],
        "total_funding_mln": round(row["sum_funding"], 1),
        "n_funding_known": row["n_funding"],
    }
