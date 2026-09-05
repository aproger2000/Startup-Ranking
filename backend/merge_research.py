#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Объединяет исходный data/seed.json (137 записей из первой версии рейтинга)
с новыми исследованиями (data/research/aged_growing.json — раздел "Возрастные,
но растущие" и data/research/early_stage.json — раздел "Ранняя стадия") в
единый seed.json с полной схемой (включая новое поле is_early_stage).

Запуск (один раз, для пересборки seed.json):  python3 merge_research.py
"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
SEED_PATH = os.path.join(BASE, "data", "seed.json")
AGED_PATH = os.path.join(BASE, "data", "research", "aged_growing.json")
EARLY_PATH = os.path.join(BASE, "data", "research", "early_stage.json")

with open(SEED_PATH, encoding="utf-8") as f:
    seed = json.load(f)

with open(AGED_PATH, encoding="utf-8") as f:
    aged = json.load(f)

with open(EARLY_PATH, encoding="utf-8") as f:
    early = json.load(f)


def normalize(item, is_early_stage):
    return {
        "name": item["name"],
        "sector": item["sector"],
        "founded": item.get("founded"),
        "rev": item.get("rev"),
        "rev_year": item.get("rev_year"),
        "growth": item.get("growth"),
        "growth_note": item.get("growth_note"),
        "funding_rub": item.get("funding_rub"),
        "funding_note": item.get("funding_note"),
        "investors": item.get("investors"),
        "desc": item.get("desc"),
        "note": item.get("note"),
        "source_name": item.get("source_name"),
        "source_url": item.get("source_url"),
        "is_ipo": bool(item.get("is_ipo", False)),
        "is_official_rank": bool(item.get("is_official_rank", False)),
        "is_major_investor": bool(item.get("is_major_investor", False)),
        "is_early_stage": is_early_stage,
        "category": "domestic",
        "status": "active",
        "confidence": item.get("confidence", "medium"),
    }


# существующие 137 записей: явно проставляем is_early_stage=False (в исходном
# seed.json этого поля ещё нет)
for item in seed:
    item.setdefault("is_early_stage", False)

existing_keys = {(it["name"], it["sector"]) for it in seed}

merged = list(seed)
skipped = []

for item in aged:
    key = (item["name"], item["sector"])
    if key in existing_keys:
        skipped.append(("aged_growing", key))
        continue
    merged.append(normalize(item, is_early_stage=False))
    existing_keys.add(key)

for item in early:
    key = (item["name"], item["sector"])
    if key in existing_keys:
        skipped.append(("early_stage", key))
        continue
    merged.append(normalize(item, is_early_stage=True))
    existing_keys.add(key)

with open(SEED_PATH, "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)

print(f"Итого записей в seed.json: {len(merged)} (было {len(seed)}, добавлено aged={len(aged)}, early={len(early)})")
if skipped:
    print("Пропущено как дубликаты (name, sector):")
    for src, key in skipped:
        print(f"  [{src}] {key}")
