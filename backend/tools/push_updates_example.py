#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Пример скрипта для пополнения базы рейтинга из внешнего источника через
bulk-эндпоинт админки. Это ШАБЛОН — сам он не ходит в интернет за данными,
а показывает, как отправить уже собранные записи на живой сервис.

Как использовать для регулярного автообновления:
  1. Соберите свежие данные о компаниях (вручную, через агент-исследование,
     через будущий парсер и т.п.) в список словарей в формате ниже.
  2. Подставьте SERVICE_URL и ADMIN_API_KEY вашего развёрнутого на Render
     сервиса (ключ — тот же, что задан в переменной окружения ADMIN_API_KEY).
  3. Запустите скрипт вручную, либо поставьте его в расписание — например,
     через Claude ("создай запланированную задачу, которая раз в неделю
     исследует новости о российских стартапах и добавляет/обновляет записи
     через POST /api/admin/companies/bulk"), либо через Render Cron Job /
     любой другой планировщик на вашей стороне.

Апсерт идёт по паре (name, sector): если такая запись уже есть — она
обновится, если нет — создастся новая. Скор пересчитывается сервером
автоматически по формуле из /api/methodology.

Запуск:  python3 push_updates_example.py
"""
import json
import urllib.request

SERVICE_URL = "https://ВАШ-СЕРВИС.onrender.com"   # замените на реальный адрес после деплоя
ADMIN_API_KEY = "ЗАМЕНИТЕ_НА_КЛЮЧ"                  # тот же, что задан в ADMIN_API_KEY на Render

# Пример новых/обновлённых записей — в реальном сценарии этот список
# формируется на основе свежих публичных данных (пресс-релизы, отраслевые
# рейтинги, карточки компаний и т.п.)
ITEMS = [
    {
        "name": "Пример Стартап",
        "sector": "Fintech и Insurtech",
        "founded": 2022,
        "rev": 150,             # млн ₽
        "rev_year": 2025,
        "growth": 80,           # % год к году
        "funding_rub": 300,     # млн ₽
        "investors": "Пример Фонд",
        "desc": "Короткое описание того, чем занимается компания",
        "source_name": "vc.ru",
        "source_url": "https://vc.ru/example",
        "is_ipo": False,
        "is_official_rank": False,
        "is_major_investor": False,
        "category": "domestic",
        "status": "active",
        "confidence": "medium",
    },
]


def main():
    body = json.dumps(ITEMS).encode("utf-8")
    req = urllib.request.Request(
        f"{SERVICE_URL}/api/admin/companies/bulk",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Api-Key": ADMIN_API_KEY},
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    print(f"Готово: создано {result['created']}, обновлено {result['updated']}, всего {result['total']}")


if __name__ == "__main__":
    main()
