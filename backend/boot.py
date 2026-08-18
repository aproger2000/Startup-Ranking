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

from app.server import main  # noqa: E402

main()
