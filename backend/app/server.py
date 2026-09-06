"""
HTTP-сервер на стандартной библиотеке Python (http.server) — без FastAPI/
Django и любых внешних зависимостей. Отдаёт JSON API под /api/* и статику
фронтенда (frontend/) под /.

Запуск:  python3 -m app.server            (локально, порт из $PORT или 8000)
"""
import json
import mimetypes
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import db
from . import enrich

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")

METHODOLOGY = {
    "scope": "Компании, работающие преимущественно на российском рынке, по всем отраслям, разбитые на 4 раздела по "
             "возрасту/стадии: «Молодые» (до 3 лет), «Зрелые» (3–10 лет), «Возрастные, но растущие» (10–15 лет, "
             "отобраны по явным признакам продолжающегося роста) и «Ранняя стадия» (pre-seed/seed — выручки нет или "
             "она только начинается, но идея и трекшен выглядят перспективно). Раздел «Ранняя стадия» приоритетный: "
             "если компания туда попадает, она не дублируется в возрастных разделах, независимо от года основания. "
             "Компании старше 15 лет (и не отмеченные как ранняя стадия) в рейтинг не входят вообще — это не стартапы "
             "и не растущие молодые компании, а часть рынка, которую этот рейтинг не охватывает по замыслу.",
    "sources": "ТЕХУСПЕХ (ts.vedomosti.ru), РБК «Топ-50 быстрорастущих компаний», TAdviser500, Smart Ranking (Fintech, "
               "Cybersecurity), карточки ЕГРЮЛ через РБК Компании, Rusbase/RB.RU, vc.ru, Forbes.ru, CNews, ComNews, Sk.ru, "
               "Interfax, Коммерсантъ, Ведомости, Inc. Russia, обзоры акселераторов (Yandex AI Startup Lab, Sber500, ФРИИ, "
               "Сколково). Прямой автоматический сбор с rusprofile.ru недоступен (сервис отдаёт 403 при программном "
               "обращении); для уточнения дат регистрации и реквизитов используется DaData (открытые данные ЕГРЮЛ/ЕГРИП).",
    "score_formula": "Скор = Выручка (0–38 баллов, лог-шкала) + Рост выручки (от −24 до +24, знак сохраняется) + "
                      "Финансирование (0–20 баллов, лог-шкала) + Признание (IPO/pre-IPO +10, официальный отраслевой рейтинг +5, "
                      "крупный инвестор +3) − 6, если ни выручка, ни рост, ни финансирование не раскрыты. Пересчитывается "
                      "автоматически сервером при каждом добавлении/обновлении записи. Для раздела «Ранняя стадия» та же "
                      "формула — компании там обычно ранжируются в основном за счёт финансирования и признания, а не выручки.",
    "limitations": [
        "Это не прямая выгрузка из rusprofile.ru или СПАРК — часть цифр восходит к тем же официальным источникам "
        "(данные ФНС/ЕГРЮЛ), но получена через вторичные агрегаторы и СМИ, отсюда встречаются расхождения между источниками.",
        "Для значительной части компаний (особенно ранней стадии и резидентов «Сколково») в открытом доступе есть только "
        "сумма привлечённого финансирования, но не выручка — это не показатель слабости бизнеса, а следствие непубличности отчётности.",
        "Суммы в долларах пересчитаны в рубли по ориентировочному курсу 85 ₽/$ для сопоставимости.",
        "Компании с пометкой «пограничный год основания» формально основаны в 2017–2018 годах — на 1–2 года раньше строгой "
        "границы, но оставлены в базе как заметные и хорошо задокументированные игроки нужного возрастного сегмента.",
        "Закрытые компании и компании в процедуре банкротства переводятся в статус closed/distress и скрываются из "
        "основного рейтинга независимо от возраста.",
        "Раздел «Возрастные, но растущие» (10–15 лет) — это новый охват (добавлен в сентябре 2026): критерий «растёт» "
        "проверяется вручную на этапе отбора записи (рост выручки, экспансия, крупные раунды/M&A уже будучи зрелой "
        "компанией), а не автоматической формулой — так что попадание в раздел не гарантирует, что рост продолжится.",
        "Жёсткая граница в 15 лет (сентябрь 2026): компании старше исключены из рейтинга целиком, даже если формально "
        "продолжают расти — это ограничение охвата (рейтинг именно стартапов и молодых растущих компаний), а не оценка "
        "их бизнеса. Компания «выпадает» из базы автоматически по мере старения, без ручной модерации.",
        "Раздел «Ранняя стадия» составлен в основном по подборкам акселераторов и медиа (Yandex AI Startup Lab, RB.RU "
        "Choice 100, vc.ru) — это неизбежно value judgement источников о том, что «перспективно», а не объективный "
        "финансовый показатель.",
        "База пополняется на основе открытых источников и может содержать неточности — проверяйте важные решения по первоисточникам.",
    ],
    "excluded_notes": [
        "«Манго Страхование» (2019, insurtech) — прекратила деятельность в августе 2022 г. после остановки финансирования инвестором.",
        "SR Space (ex-Success Rockets, 2020, космос) — находится в процедуре банкротства (2025), под санкциями США (2024).",
        "Ronavi Robotics (2016) и ARS Smart Robotics (по перекрёстной проверке — 2016) — старше целевого возрастного диапазона.",
        "Сравни.ру (2008), CarMoney (2016), «Здоровье.ру» (2016), Medical Visual Systems (2015), РОББО (2007), Smart Engines (2016), "
        "Нейротренд (2015), Гордиз (2008), Broniboy (2017), iFarm (2017), TraceAir/GeoCV/Apis Cor/HomeApp (2014-2018), "
        "Fntastic (2015) — заметные игроки, но основаны заметно раньше ~2019 г.",
    ],
    "usd_rub": 85,
}


def json_default(o):
    raise TypeError(f"Не сериализуется в JSON: {type(o)}")


class Handler(BaseHTTPRequestHandler):
    server_version = "StartupRankingAPI/1.0"

    def log_message(self, fmt, *args):
        # компактный лог вместо стандартного многословного формата http.server
        print(f"{self.address_string()} {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")

    # ---------- helpers ----------
    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False, default=json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Api-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status, message):
        self._send_json({"error": message}, status=status)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Некорректный JSON в теле запроса: {e}")

    def _require_admin(self) -> bool:
        if not ADMIN_API_KEY:
            self._send_error_json(503, "ADMIN_API_KEY не настроен на сервере — админ-функции отключены")
            return False
        key = self.headers.get("X-Api-Key")
        if not key or key != ADMIN_API_KEY:
            self._send_error_json(401, "Неверный или отсутствующий заголовок X-Api-Key")
            return False
        return True

    def _serve_static(self, path: str):
        if path == "/":
            path = "/index.html"
        # защита от выхода за пределы каталога фронтенда
        safe_path = os.path.normpath(path).lstrip("/")
        full_path = os.path.join(FRONTEND_DIR, safe_path)
        if not os.path.abspath(full_path).startswith(os.path.abspath(FRONTEND_DIR)):
            self._send_error_json(403, "Forbidden")
            return
        if not os.path.isfile(full_path):
            # SPA-фоллбэк на index.html для путей без расширения (например, /admin)
            if "." not in os.path.basename(safe_path):
                full_path = os.path.join(FRONTEND_DIR, safe_path.rstrip("/") + ".html")
        if not os.path.isfile(full_path):
            self._send_error_json(404, "Не найдено")
            return
        ctype, _ = mimetypes.guess_type(full_path)
        with open(full_path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---------- routing ----------
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Api-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        try:
            if path == "/api/health":
                return self._send_json({"status": "ok"})

            if path == "/api/companies":
                items, total = db.list_companies(
                    sector=qs.get("sector"),
                    search=qs.get("search"),
                    category=qs.get("category", "domestic"),
                    status=qs.get("status", "active"),
                    bucket=qs.get("bucket") or None,
                    limit=min(int(qs.get("limit", 100)), 500),
                    offset=int(qs.get("offset", 0)),
                    sort_by=qs.get("sort_by", "score"),
                    sort_dir=qs.get("sort_dir", "desc"),
                    include_excluded=qs.get("include_all_ages") == "1",
                )
                return self._send_json({"total": total, "items": items})

            if path == "/api/buckets":
                return self._send_json(db.bucket_counts(
                    category=qs.get("category", "domestic"), status=qs.get("status", "active")
                ))

            m = re.match(r"^/api/companies/(\d+)$", path)
            if m:
                obj = db.get_company(int(m.group(1)))
                if not obj:
                    return self._send_error_json(404, "Компания не найдена")
                return self._send_json(obj)

            if path == "/api/sectors":
                return self._send_json(db.sector_counts(
                    category=qs.get("category", "domestic"), status=qs.get("status", "active")
                ))

            if path == "/api/stats":
                return self._send_json(db.stats(
                    category=qs.get("category", "domestic"), status=qs.get("status", "active")
                ))

            if path == "/api/vc-funds":
                return self._send_json({"items": db.list_vc_funds()})

            if path == "/api/industries/mining":
                items, total = db.list_mining_industry_companies(
                    limit=min(int(qs.get("limit", 100)), 500),
                    offset=int(qs.get("offset", 0)),
                )
                return self._send_json({"total": total, "items": items})

            if path == "/api/methodology":
                return self._send_json(METHODOLOGY)

            if path == "/api/admin/enrich":
                if not self._require_admin():
                    return
                if not enrich.DADATA_API_KEY:
                    return self._send_error_json(503, "DADATA_API_KEY не настроен на сервере — обогащение через DaData отключено")
                query = qs.get("query", "").strip()
                if not query:
                    return self._send_error_json(422, "Параметр query обязателен")
                try:
                    candidates = enrich.suggest_company(query)
                except RuntimeError as e:
                    return self._send_error_json(502, str(e))
                return self._send_json({"query": query, "candidates": candidates})

            if path.startswith("/api/"):
                return self._send_error_json(404, "Неизвестный маршрут API")

            return self._serve_static(path)
        except Exception as e:  # noqa: BLE001
            self._send_error_json(500, f"Внутренняя ошибка: {e}")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/admin/companies":
                if not self._require_admin():
                    return
                data = self._read_json_body()
                if not data.get("name") or not data.get("sector"):
                    return self._send_error_json(422, "Обязательные поля: name, sector")
                if db.find_by_name_sector(data["name"], data["sector"]):
                    return self._send_error_json(409, "Компания с таким названием и отраслью уже существует — используйте PUT")
                obj = db.create_company(data)
                return self._send_json(obj, status=201)

            if path == "/api/admin/companies/bulk":
                if not self._require_admin():
                    return
                data = self._read_json_body()
                items = data if isinstance(data, list) else data.get("items", [])
                for it in items:
                    if not it.get("name") or not it.get("sector"):
                        return self._send_error_json(422, "У каждой записи обязательны поля name и sector")
                created, updated = db.bulk_upsert(items)
                return self._send_json({"created": created, "updated": updated, "total": created + updated})

            if path == "/api/admin/vc-funds/bulk":
                if not self._require_admin():
                    return
                data = self._read_json_body()
                items = data if isinstance(data, list) else data.get("items", [])
                for it in items:
                    if not it.get("name"):
                        return self._send_error_json(422, "У каждой записи обязательно поле name")
                created, updated = db.bulk_upsert_vc_funds(items)
                return self._send_json({"created": created, "updated": updated, "total": created + updated})

            return self._send_error_json(404, "Неизвестный маршрут")
        except ValueError as e:
            self._send_error_json(400, str(e))
        except Exception as e:  # noqa: BLE001
            self._send_error_json(500, f"Внутренняя ошибка: {e}")

    def do_PUT(self):
        parsed = urlparse(self.path)
        m = re.match(r"^/api/admin/companies/(\d+)$", parsed.path)
        try:
            if m:
                if not self._require_admin():
                    return
                data = self._read_json_body()
                obj = db.update_company(int(m.group(1)), data)
                if not obj:
                    return self._send_error_json(404, "Компания не найдена")
                return self._send_json(obj)
            return self._send_error_json(404, "Неизвестный маршрут")
        except ValueError as e:
            self._send_error_json(400, str(e))
        except Exception as e:  # noqa: BLE001
            self._send_error_json(500, f"Внутренняя ошибка: {e}")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        m = re.match(r"^/api/admin/companies/(\d+)$", parsed.path)
        try:
            if m:
                if not self._require_admin():
                    return
                ok = db.delete_company(int(m.group(1)))
                if not ok:
                    return self._send_error_json(404, "Компания не найдена")
                return self._send_json({"deleted": int(m.group(1))})
            return self._send_error_json(404, "Неизвестный маршрут")
        except Exception as e:  # noqa: BLE001
            self._send_error_json(500, f"Внутренняя ошибка: {e}")


def main():
    db.init_db()
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Сервер запущен на http://{host}:{port}  (ADMIN_API_KEY {'задан' if ADMIN_API_KEY else 'НЕ задан — админка отключена'})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
