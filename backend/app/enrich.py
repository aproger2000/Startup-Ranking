"""
Обогащение данных через DaData ("Подсказки по организациям") — используется
из админ-панели, чтобы уточнить точный год регистрации компании (и её
ИНН/ОГРН) по открытым данным ЕГРЮЛ/ЕГРИП, вместо ручного поиска в интернете.

Работает только если задана переменная окружения DADATA_API_KEY (бесплатный
ключ — после регистрации на https://dadata.ru/api/, тариф "Бесплатный":
10 000 запросов в день). Без ключа эндпоинт /api/admin/enrich возвращает 503,
остальной сервис при этом продолжает работать как обычно — это опциональное
дополнение, а не обязательная зависимость.

Реализовано на chistом urllib (без внешних библиотек вроде requests), чтобы
не добавлять зависимостей проекту.
"""
import json
import os
import urllib.error
import urllib.request

DADATA_API_KEY = os.environ.get("DADATA_API_KEY")
SUGGEST_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"


def _ts_to_year(ts):
    """DaData отдаёт даты как Unix-время в миллисекундах; на всякий случай
    поддерживаем и секунды."""
    if ts is None:
        return None
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return None
    seconds = ts / 1000 if ts > 10**12 else ts
    try:
        import datetime
        return datetime.datetime.utcfromtimestamp(seconds).year
    except (OverflowError, OSError, ValueError):
        return None


def suggest_company(query: str, count: int = 5):
    """Возвращает список кандидатов вида:
    [{"name": ..., "inn": ..., "ogrn": ..., "founded": <год или null>,
      "status": ..., "address": ...}, ...]
    Бросает RuntimeError с человекочитаемым сообщением при ошибке запроса —
    вызывающий код (server.py) превращает это в JSON-ошибку с кодом 502."""
    if not DADATA_API_KEY:
        raise RuntimeError("DADATA_API_KEY не настроен на сервере")

    body = json.dumps({"query": query, "count": count}).encode("utf-8")
    req = urllib.request.Request(
        SUGGEST_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {DADATA_API_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DaData вернула ошибку {e.code}: {detail[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Не удалось обратиться к DaData: {e.reason}")

    out = []
    for s in payload.get("suggestions", []):
        d = s.get("data", {}) or {}
        state = d.get("state", {}) or {}
        name = d.get("name", {}) or {}
        addr = d.get("address", {}) or {}
        out.append({
            "name": name.get("short_with_opf") or name.get("full_with_opf") or s.get("value"),
            "inn": d.get("inn"),
            "ogrn": d.get("ogrn"),
            "founded": _ts_to_year(state.get("registration_date")),
            "status": state.get("status"),
            "address": (addr.get("value") if isinstance(addr, dict) else None),
        })
    return out
