#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Загружает backend/data/seed.json в базу (создаёт таблицу, если её ещё нет).

Запуск:  cd backend && python3 seed_db.py
Безопасно запускать повторно — работает через upsert по паре (name, sector).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app import db  # noqa: E402

db.init_db()

seed_path = os.path.join(os.path.dirname(__file__), "data", "seed.json")
with open(seed_path, encoding="utf-8") as f:
    items = json.load(f)

created, updated = db.bulk_upsert(items)
print(f"Готово: создано {created}, обновлено {updated}, всего в файле {len(items)}")
