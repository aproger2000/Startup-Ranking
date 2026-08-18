#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Строит backend/data/seed.json из более ранней таблицы данных (133 отобранные
компании + 4 diaspora-кейса), пересобранной в первой части проекта
(/home/claude/startups_ranking/build_data.py). Формат приведён к схеме API
нового сервиса (is_ipo / is_official_rank / is_major_investor вместо текстовых
пометок в note).
"""
import importlib.util
import json
import os

SRC = "/home/claude/startups_ranking/build_data.py"
spec = importlib.util.spec_from_file_location("build_data", SRC)
build_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_data)  # выполняет модуль (в т.ч. печатает свою сводку — это нормально)

seed = []
for d in build_data.DATA:
    seed.append({
        "name": d["name"],
        "sector": d["sector"],
        "founded": d["founded"],
        "rev": d["rev"],
        "rev_year": d["rev_year"],
        "growth": d["growth"],
        "growth_note": d["growth_note"] or None,
        "funding_rub": d["funding_rub"],
        "funding_note": d["funding_note"] or None,
        "investors": d["investors"] if d["investors"] and d["investors"] != "—" else None,
        "desc": d["desc"],
        "note": d["note"] or None,
        "source_name": d["source_name"],
        "source_url": d["source_url"],
        "is_ipo": bool(d["ipo"]),
        "is_official_rank": bool(d["official_rank"]),
        "is_major_investor": bool(d["major_investor"]),
        "category": "domestic",
        "status": d["status"],
        "confidence": d["confidence"],
    })

for d in build_data.DIASPORA:
    seed.append({
        "name": d["name"],
        "sector": d["sector"],
        "founded": d["founded"],
        "rev": None,
        "rev_year": None,
        "growth": None,
        "growth_note": None,
        "funding_rub": None,
        "funding_note": d.get("funding_note"),
        "investors": None,
        "desc": d["note"],
        "note": "Работает преимущественно на зарубежном рынке — российские сооснователи",
        "source_name": None,
        "source_url": d["source_url"],
        "is_ipo": False,
        "is_official_rank": False,
        "is_major_investor": False,
        "category": "diaspora",
        "status": "active",
        "confidence": "medium",
    })

os.makedirs(os.path.join(os.path.dirname(__file__), "data"), exist_ok=True)
out_path = os.path.join(os.path.dirname(__file__), "data", "seed.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(seed, f, ensure_ascii=False, indent=2)

print(f"\nСохранено {len(seed)} записей в {out_path}")
