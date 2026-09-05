"""
Слой доступа к данным на чистом sqlite3 (стандартная библиотека Python —
без внешних зависимостей, поэтому сервис разворачивается без шага `pip
install` и без риска конфликтов версий).

Схема простая: одна таблица `companies`. Скор пересчитывается в scoring.py
при каждой вставке/обновлении, поэтому рейтинг всегда согласован.
"""
import json
import os
import sqlite3
import threading

from .buckets import compute_bucket
from .scoring import compute_score
from .vc_scoring import compute_quality_index

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
    "is_ipo", "is_official_rank", "is_major_investor", "is_early_stage",
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
    is_early_stage INTEGER DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS vc_funds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    deals_2024 INTEGER,
    deals_2025 INTEGER,
    deals_total_note TEXT,
    avg_check_note TEXT,
    notable_portfolio TEXT DEFAULT '[]',
    notable_exit_note TEXT,
    stage_focus TEXT,
    confidence TEXT DEFAULT 'medium',
    source_name TEXT,
    source_url TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

VC_FUND_FIELDS = [
    "name", "deals_2024", "deals_2025", "deals_total_note", "avg_check_note",
    "notable_portfolio", "notable_exit_note", "stage_focus", "confidence",
    "source_name", "source_url",
]


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
    _migrate(conn)


def _migrate(conn):
    """Лёгкая миграция для БД, созданных до появления поля is_early_stage —
    ALTER TABLE ... ADD COLUMN безопасен для повторного запуска (оборачиваем
    в try/except, так как sqlite не поддерживает IF NOT EXISTS для колонок)."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(companies)")}
    if "is_early_stage" not in cols:
        conn.execute("ALTER TABLE companies ADD COLUMN is_early_stage INTEGER DEFAULT 0")
        conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["is_ipo"] = bool(d["is_ipo"])
    d["is_official_rank"] = bool(d["is_official_rank"])
    d["is_major_investor"] = bool(d["is_major_investor"])
    d["is_early_stage"] = bool(d.get("is_early_stage", 0))
    d["bucket"] = compute_bucket(d.get("founded"), d["is_early_stage"])
    return d


def _clean(data: dict) -> dict:
    """Оставляет только известные поля, остальное игнорируется."""
    return {k: data[k] for k in FIELDS if k in data}


def list_companies(sector=None, search=None, category="domestic", status="active",
                    bucket=None, limit=100, offset=0, sort_by="score", sort_dir="desc",
                    include_excluded=False):
    """bucket — один из buckets.BUCKETS ("young"/"mature"/"aged"/"early_stage")
    или None (без фильтра по разделу). Фильтрация по bucket и сортировка/
    пагинация делаются в Python поверх результата SQL-запроса — набор данных
    небольшой (сотни записей), а bucket вычисляется динамически от текущего
    года и не хранится в колонке, так что чистого SQL-WHERE для него нет.

    include_excluded=True отключает фильтр по buckets.MAX_AGE_YEARS (компании
    старше 15 лет, bucket=None) — используется только админ-панелью, чтобы
    такие записи оставались находимыми и редактируемыми/удаляемыми, хотя из
    публичного рейтинга они скрыты."""
    allowed_sort = {"score", "rev", "growth", "funding_rub", "founded", "name"}
    if sort_by not in allowed_sort:
        sort_by = "score"
    reverse = sort_dir != "asc"

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

    rows = conn.execute(f"SELECT * FROM companies {where_sql}", params).fetchall()
    items = [_row_to_dict(r) for r in rows]

    # компании старше buckets.MAX_AGE_YEARS (bucket=None) исключены из рейтинга
    # целиком — не только из конкретного раздела, но из любой выдачи вообще
    # (кроме админ-панели, см. include_excluded)
    if not include_excluded:
        items = [it for it in items if it["bucket"] is not None]

    if bucket:
        items = [it for it in items if it["bucket"] == bucket]

    # null-значения всегда в конце независимо от направления сортировки
    non_null = [it for it in items if it.get(sort_by) is not None]
    null_items = [it for it in items if it.get(sort_by) is None]
    non_null.sort(key=lambda it: it[sort_by], reverse=reverse)
    items = non_null + null_items

    total = len(items)
    page = items[offset:offset + limit]
    return page, total


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


def bucket_counts(category="domestic", status="active"):
    """Количество компаний в каждом из 4 разделов (young/mature/aged/early_stage)
    для заданной категории — одним проходом по данным, без отдельного запроса
    на раздел."""
    from .buckets import BUCKETS
    conn = get_conn()
    where = ["category = ?", "status = ?"]
    params = [category, status]
    rows = conn.execute(
        f"SELECT * FROM companies WHERE {' AND '.join(where)}", params
    ).fetchall()
    counts = {b: 0 for b in BUCKETS}
    for r in rows:
        d = _row_to_dict(r)
        if d["bucket"] in counts:
            counts[d["bucket"]] += 1
    return counts


def _active_items(category="domestic", status="active"):
    """Все записи категории/статуса, приведённые в словарь и уже без компаний
    старше buckets.MAX_AGE_YEARS (bucket=None) — общая база для sector_counts()
    и stats(), чтобы они считали ровно то же множество записей, что видно в
    списках/разделах."""
    conn = get_conn()
    where = ["category = ?", "status = ?"]
    params = [category, status]
    rows = conn.execute(
        f"SELECT * FROM companies WHERE {' AND '.join(where)}", params
    ).fetchall()
    items = [_row_to_dict(r) for r in rows]
    return [it for it in items if it["bucket"] is not None]


def sector_counts(category="domestic", status="active"):
    items = _active_items(category, status)
    counts = {}
    for it in items:
        counts[it["sector"]] = counts.get(it["sector"], 0) + 1
    return [[sector, n] for sector, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)]


def _vc_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    try:
        d["notable_portfolio"] = json.loads(d.get("notable_portfolio") or "[]")
    except (TypeError, ValueError):
        d["notable_portfolio"] = []
    d["quality_index"] = compute_quality_index(
        d.get("notable_exit_note"), d["notable_portfolio"], d.get("stage_focus")
    )
    return d


def _clean_vc(data: dict) -> dict:
    out = {k: data[k] for k in VC_FUND_FIELDS if k in data}
    if "notable_portfolio" in out:
        out["notable_portfolio"] = json.dumps(out["notable_portfolio"] or [], ensure_ascii=False)
    return out


def list_vc_funds():
    """Возвращает все фонды, отсортированные так, чтобы сначала шли записи
    с известным числом сделок (по убыванию deals_2024+deals_2025), а затем —
    фонды без точных цифр (по убыванию quality_index). Строк немного
    (десятки), поэтому сортировка в Python, как и для companies."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM vc_funds").fetchall()
    items = [_vc_row_to_dict(r) for r in rows]

    def deal_count(it):
        d24, d25 = it.get("deals_2024"), it.get("deals_2025")
        if d24 is None and d25 is None:
            return None
        return (d24 or 0) + (d25 or 0)

    known = [it for it in items if deal_count(it) is not None]
    unknown = [it for it in items if deal_count(it) is None]
    known.sort(key=deal_count, reverse=True)
    unknown.sort(key=lambda it: it["quality_index"], reverse=True)
    return known + unknown


def find_vc_fund_by_name(name: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM vc_funds WHERE name = ?", (name,)).fetchone()
    return _vc_row_to_dict(row) if row else None


def bulk_upsert_vc_funds(items: list[dict]):
    created, updated = 0, 0
    conn = get_conn()
    for item in items:
        data = _clean_vc(item)
        existing = find_vc_fund_by_name(item["name"])
        if existing:
            set_clause = ", ".join(f"{k} = ?" for k in data.keys())
            conn.execute(
                f"UPDATE vc_funds SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                list(data.values()) + [existing["id"]],
            )
            updated += 1
        else:
            cols = list(data.keys())
            placeholders = ", ".join("?" for _ in cols)
            conn.execute(
                f"INSERT INTO vc_funds ({', '.join(cols)}) VALUES ({placeholders})",
                list(data.values()),
            )
            created += 1
    conn.commit()
    return created, updated


def stats(category="domestic", status="active"):
    items = _active_items(category, status)
    revs = [it["rev"] for it in items if it.get("rev") is not None]
    fundings = [it["funding_rub"] for it in items if it.get("funding_rub") is not None]
    sectors = {it["sector"] for it in items}
    return {
        "total_companies": len(items),
        "total_sectors": len(sectors),
        "total_revenue_mln": round(sum(revs), 1),
        "n_revenue_known": len(revs),
        "total_funding_mln": round(sum(fundings), 1),
        "n_funding_known": len(fundings),
    }
