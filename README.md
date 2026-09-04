# Characters Service

Минимальный backend-каркас сервиса электронных листов персонажей.

## Состав

- FastAPI;
- PostgreSQL;
- SQLAlchemy с async-сессиями;
- Alembic;
- Docker Compose;
- конфигурация из `.env`;
- liveness и database-readiness endpoints.

## Запуск в Docker

1. Проверьте значения в `.env`.
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

Удаление volume с локальными данными PostgreSQL выполняйте только осознанно:

```shell
docker compose down --volumes
```

## Локальный запуск API

PostgreSQL должен быть доступен по адресу из `DATABASE_URL` в `.env`.

```shell
uv sync
uv run uvicorn app.main:app --reload
```

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
uv run ruff check .
uv run mypy app
uv run pytest
```
