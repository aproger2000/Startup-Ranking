#!/usr/bin/env bash
# Массовая загрузка/обновление данных на живом сервере через админ-API —
# обёртка над curl, чтобы не перепечатывать X-Api-Key и URL каждый раз.
#
# Ключ берётся из переменной окружения ADMIN_API_KEY — она должна быть уже
# задана в текущем шелле (см. "Хранение ADMIN_API_KEY локально" в README:
# один раз добавляете export в свой ~/.zshrc или ~/.bashrc, либо создаёте
# .env.local в корне репозитория и делаете `source .env.local` — оба пути
# в .gitignore, ключ никогда не попадёт в git).
#
# Использование:
#   ./backend/tools/bulk_upsert.sh backend/data/mining_companies.json
#   ./backend/tools/bulk_upsert.sh backend/data/vc_funds.json vc-funds
#   ./backend/tools/bulk_upsert.sh backend/data/seed.json companies https://my-staging-url.onrender.com

set -euo pipefail

FILE="${1:?Использование: $0 <путь-к-json> [companies|vc-funds] [base-url]}"
KIND="${2:-companies}"
BASE_URL="${3:-https://startup-ranking-service.onrender.com}"

if [ -z "${ADMIN_API_KEY:-}" ]; then
  echo "Ошибка: переменная окружения ADMIN_API_KEY не задана в этом шелле." >&2
  echo "Разовая настройка (один из вариантов):" >&2
  echo "  echo 'export ADMIN_API_KEY=ваш_ключ' >> ~/.zshrc && source ~/.zshrc" >&2
  echo "  # или создайте .env.local в корне репозитория (уже в .gitignore) и делайте перед запуском: source .env.local" >&2
  exit 1
fi

if [ ! -f "$FILE" ]; then
  echo "Ошибка: файл не найден: $FILE" >&2
  exit 1
fi

case "$KIND" in
  companies) ENDPOINT="/api/admin/companies/bulk" ;;
  vc-funds)  ENDPOINT="/api/admin/vc-funds/bulk" ;;
  *)
    echo "Ошибка: неизвестный тип '$KIND' (ожидается: companies или vc-funds)" >&2
    exit 1
    ;;
esac

echo "POST ${BASE_URL}${ENDPOINT}  <-  ${FILE}" >&2
curl -sS -X POST "${BASE_URL}${ENDPOINT}" \
  -H "X-Api-Key: ${ADMIN_API_KEY}" \
  -H "Content-Type: application/json" \
  --data-binary "@${FILE}"
echo
