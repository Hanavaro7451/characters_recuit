# Задание 04 — финальная приёмка исправлений 02

Дата: 2026-10-05. Статус: done. Исходный и итоговый HEAD:
`742378793f9ed5905f267da5d9bd4f32eb81aa46`.

## Результат

- Незакоммиченный diff задания 02 сохранён; прочитаны изменения auth, прав доступа,
  моделей, миграций, CI и документации. Новых замечаний по приложению нет.
- QA исправил два URL с завершающим `/` в новом интеграционном сценарии
  `tests/integration/test_campaign_api.py`; это устранило 307 вместо ожидаемого 201.
- Текущее поведение проверено с реальной PostgreSQL 17: миграции
  upgrade/downgrade/upgrade, ORM и ограничения UNIQUE, изоляция кампаний,
  invite-доступ, readiness, JWT rotation/replay/logout, конкурентный refresh,
  сроки сессий и откат транзакции.
- DevOps проверил Docker build/up, HTTP live/docs/ready, сохранность тестовой записи
  после рестарта, custom dump и восстановление в отдельную PostgreSQL 17. На
  восстановленной БД подтверждены Alembic head `d85fb6214e09`, запись и readiness.
  Временный проект и ресурсы DevOps удалены; QA и основной Compose не затронуты.

## Фактические проверки

- `uv sync --frozen` — exit 0; `uv run --frozen ruff check .` — exit 0;
  `uv run --frozen mypy app` — exit 0, 38 файлов.
- `uv run --frozen pytest tests --ignore=tests/integration -q` вне sandbox —
  119 passed, exit 0. В sandbox было 108 passed и 11 setup errors из-за загрузки
  Argon2 DLL; вне sandbox те же тесты прошли.
- `uv run --frozen pytest -q` вне sandbox — 119 passed, 24 skipped, exit 0:
  интеграция без `TEST_DATABASE_URL` штатно пропускается.
- QA: `uv run --frozen pytest tests/integration` на `characters_test_audit` —
  24 passed, exit 0; `tests/test_audit_regressions.py` — 33 passed, exit 0.
- DevOps: Docker `up --build --wait` и HTTP smoke — exit 0/200; PostgreSQL
  persistence, `pg_dump`/`pg_restore` и restored API readiness — успешно;
  `actionlint` — exit 0; `uv lock --check --offline` — exit 0.
- `git diff --check` — exit 0; есть только предупреждения Git о LF/CRLF.

## Ограничения и следующий шаг

QA-интеграция запускалась на отдельной тестовой БД, не на рабочей. Восстановленная
БД содержала контрольную запись, но не заполненные кампании/персонажей; чтение
этих ресурсов после восстановления не проверялось. В текущей версии API листа
персонажа ещё нет. Блокеров для приёмки задания 02 нет. Следующий шаг —
просмотреть и оформить сохранённый незакоммиченный diff в Git; деплой и миграции
рабочей БД в это задание не входили.
