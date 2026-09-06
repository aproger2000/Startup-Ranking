#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Точка входа для продакшена (Render и т.п.).

При первом запуске, если база данных пуста, автоматически подгружает
исходный набор данных (data/seed.json), чтобы сервис не стартовал с
пустым рейтингом. При последующих перезапусках (диск на Render уже
содержит базу) повторного заполнения не происходит — это не затирает
записи, добавленные/изменённые через админ-панель.

Запуск:  python3 boot.py   (из каталога backend/)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import db  # noqa: E402

db.init_db()
conn = db.get_conn()
count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
print(f"[boot] База данных: {db.DB_PATH}")
print(f"[boot] Компаний в базе: {count}")

if count == 0:
    seed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "seed.json")
    if os.path.exists(seed_path):
        print("[boot] База пуста — загружаю data/seed.json...")
        with open(seed_path, encoding="utf-8") as f:
            items = json.load(f)
        created, updated = db.bulk_upsert(items)
        print(f"[boot] Загружено: создано {created}, обновлено {updated}, всего {len(items)}")
    else:
        print("[boot] data/seed.json не найден — стартуем с пустой базой")
else:
    print("[boot] База уже заполнена — пропускаю загрузку seed.json")

vc_count = conn.execute("SELECT COUNT(*) FROM vc_funds").fetchone()[0]
print(f"[boot] Венчурных фондов в базе: {vc_count}")
if vc_count == 0:
    vc_seed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "vc_funds.json")
    if os.path.exists(vc_seed_path):
        print("[boot] Таблица vc_funds пуста — загружаю data/vc_funds.json...")
        with open(vc_seed_path, encoding="utf-8") as f:
            vc_items = json.load(f)
        vc_created, vc_updated = db.bulk_upsert_vc_funds(vc_items)
        print(f"[boot] Загружено фондов: создано {vc_created}, обновлено {vc_updated}, всего {len(vc_items)}")
    else:
        print("[boot] data/vc_funds.json не найден — пропускаю")
else:
    print("[boot] Таблица vc_funds уже заполнена — пропускаю загрузку")

mining_count = conn.execute("SELECT COUNT(*) FROM companies WHERE is_mining_industry = 1").fetchone()[0]
print(f"[boot] Компаний горно-рудной отрасли в базе: {mining_count}")
if mining_count == 0:
    mining_seed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mining_companies.json")
    if os.path.exists(mining_seed_path):
        print("[boot] Отраслевой срез (горно-рудная отрасль) пуст — загружаю data/mining_companies.json...")
        with open(mining_seed_path, encoding="utf-8") as f:
            mining_items = json.load(f)
        mining_created, mining_updated = db.bulk_upsert(mining_items)
        print(f"[boot] Загружено компаний горно-рудной отрасли: создано {mining_created}, обновлено {mining_updated}, всего {len(mining_items)}")
    else:
        print("[boot] data/mining_companies.json не найден — пропускаю")
else:
    print("[boot] Отраслевой срез (горно-рудная отрасль) уже заполнен — пропускаю загрузку")

from app.server import main  # noqa: E402

main()
