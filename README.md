# Characters Service

Backend сервиса электронных листов персонажей. Реализованы пользователи,
аутентификация, кампании и приглашения; интерфейс и API листа персонажа ещё
разрабатываются.

## Состав

- FastAPI;
- PostgreSQL;
- SQLAlchemy с async-сессиями;
- Alembic;
- Docker Compose;
- конфигурация из `.env`;
- liveness и database-readiness endpoints.

## Запуск в Docker

1. Если `.env` отсутствует, создайте его из `.env.example` (PowerShell):

   ```powershell
   if (-not (Test-Path .env)) { Copy-Item .env.example .env }
   ```

   Задайте собственные `POSTGRES_PASSWORD` и `JWT_SECRET_KEY`, согласуйте пароль
   с локальным `DATABASE_URL`. Не добавляйте `.env` в Git. `APP_DEBUG=true`
   предназначен только для разработки; для эксплуатации используйте `false`.
2. Запустите сервисы:

   ```shell
   docker compose up --build
   ```

   Перед запуском API контейнер автоматически применит миграции Alembic.

3. Откройте документацию API: <http://localhost:8000/docs>.
4. Проверка приложения: <http://localhost:8000/api/v1/health/live>.
5. Проверка PostgreSQL: <http://localhost:8000/api/v1/health/ready>.

Остановка:

```shell
docker compose down
```

Остановка сохраняет данные PostgreSQL. Перед любым удалением volume сохраните
и проверьте резервную копию: [backup и восстановление](docs/operations/backup-restore.md).
Compose предназначен для разработки: исходники подключены bind mount,
API запускается с `--reload`.

## Локальный запуск API

PostgreSQL должен быть доступен по адресу из `DATABASE_URL` в `.env`.

```shell
uv sync --frozen
uv run --frozen alembic upgrade head
uv run --frozen python -m app.catalog_seed
uv run uvicorn app.main:app --reload
```

Команда загрузки справочников выполняется **после миграций** и добавляет
технический минимальный набор SRD 5.2.1: Human, Fighter и Acolyte. Её можно
повторять: опубликованные версии не перезаписываются, а изменение содержимого
под тем же кодом и версией завершится ошибкой. Это не полный каталог.
В Docker после запуска и миграций выполните
`docker compose exec api uv run --frozen python -m app.catalog_seed` для
нужного Compose project. Перед запуском убедитесь, что `DATABASE_URL` указывает
на предназначенную БД.

Ссылки новых справочников в `Character` пока допускают `NULL`: старые строки
сохраняют прежние текстовые `race` и `character_class`, а их сопоставление с
версиями каталога и выбор предыстории требуют отдельного решения. API создания
нового персонажа проверяет роль Player, активность кампании и доступность
записей набора `dnd-2024`.

## Миграции

Создать миграцию после добавления SQLAlchemy-моделей:

```shell
uv run alembic revision --autogenerate -m "describe change"
```

Применить миграции:

```shell
uv run alembic upgrade head
```

## Проверки

```shell
uv sync --frozen
uv run --frozen ruff check .
uv run --frozen mypy app
uv run --frozen pytest
```

Settings требуют `DATABASE_URL` и `JWT_SECRET_KEY`, в том числе для тестов
с mocks. Интеграционные тесты PostgreSQL запускаются отдельно по инструкции
[тестовое окружение и CI](docs/operations/testing.md). Без тестовой БД они
пропускаются, поэтому успешные unit-тесты не подтверждают работу миграций.

## Аутентификация API

`POST /api/v1/auth/login` принимает JSON с `username` и `password` и возвращает
`access_token`, `refresh_token`, `token_type=bearer`. Access передаётся
в заголовке `Authorization: Bearer <access_token>`.

`POST /api/v1/auth/refresh` принимает JSON `{ "refresh_token": "..." }`
и возвращает новую пару токенов. Каждый refresh заменяет предыдущий; повторное
использование старого токена отзывает всю сессию. Клиент должен выполнять
обновление последовательно и сохранять обе новые строки токенов вместе.

`POST /api/v1/auth/logout` принимает такой же JSON и возвращает 204.
Повторный logout идемпотентен. Access привязан к сессии через `sid` и после
logout также становится недействителен. Для старых access-токенов без сессии
необходим новый вход.

`JWT_ACCESS_TOKEN_EXPIRE_MINUTES` задаёт срок access (по умолчанию 30 минут).
`JWT_REFRESH_TOKEN_EXPIRE_DAYS` задаёт абсолютный срок сессии (по умолчанию
30 дней); ротация этот срок не продлевает. Пароли и токены нельзя записывать
в логи или Git. Выбор хранения токенов в браузере будет согласован с frontend.

## Справочники и черновик персонажа

Авторизованный пользователь читает доступные версии через
`GET /api/v1/catalog/species`, `/classes`, `/backgrounds`; конкретная версия
доступна по `/{version_id}`, даже если она закрыта для нового выбора.

Игрок действующей кампании создаёт черновик через
`POST /api/v1/campaigns/{campaign_id}/characters` с `name`, `species_id`,
`class_catalog_id`, `background_id`. После создания его можно получить через
`GET /api/v1/campaigns/{campaign_id}/characters/{character_id}` и частично
обновить через `PATCH` того же пути. PATCH требует `expected_version` из
предыдущего ответа; конфликт версии возвращает 409, после чего клиенту нужно
повторно прочитать персонажа. Подробные тела ответов, ошибки и матрица прав:
[контракт задания 07](docs/contracts/07-character-draft-api.md).

API черновика пока не распределяет результаты по характеристикам и не переводит
персонажа на проверку мастеру. Старые записи с незаполненными ссылками на
справочники остаются доступны для чтения.

Однократная генерация шести результатов 4D6 доступна владельцу черновика через
`POST /api/v1/campaigns/{campaign_id}/characters/{character_id}/ability-rolls`.
Пустой запрос создаёт набор при первом вызове и возвращает сохранённый при
повторе; кубики и seed от клиента не принимаются. `GET` того же пути читает
набор владельцу или мастеру своей кампании, включая архивные записи. До
генерации GET возвращает 404. Первый POST увеличивает версию персонажа на 1,
повторные запросы её не меняют. Формат ответа и права описаны в
[контракте задания 08](docs/contracts/08-character-ability-rolls-api.md).
