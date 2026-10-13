# Проверки с PostgreSQL

Unit-тесты используют mocks и не требуют рабочей БД. Для Settings всё равно
нужны `DATABASE_URL` и `JWT_SECRET_KEY`. Интеграционные тесты требуют отдельную
PostgreSQL 17: не направляйте их на БД разработки или пользователей.

Пример одноразовой БД (PowerShell; имя контейнера должно быть свободно):

```powershell
docker run --detach --name characters-test-local -e POSTGRES_USER=characters_test -e POSTGRES_PASSWORD=local-test-only -e POSTGRES_DB=characters_test_local -p 127.0.0.1::5432 postgres:17-alpine
docker exec characters-test-local pg_isready -U characters_test -d characters_test_local
docker port characters-test-local 5432
```

Дождитесь `accepting connections`; используйте показанный порт вместо `<port>`:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+asyncpg://characters_test:local-test-only@127.0.0.1:<port>/characters_test_local'
$env:ALLOW_TEST_DATABASE_RESET = '1'
$env:DATABASE_URL = $env:TEST_DATABASE_URL
$env:JWT_SECRET_KEY = 'local-test-only-not-a-production-secret'
$env:APP_ENV = 'testing'
$env:APP_DEBUG = 'false'
uv sync --frozen
uv run --frozen pytest tests/integration
```

Имя тестовой БД должно начинаться с `characters_test`. Тесты создают отдельные
схемы с уникальными именами и удаляют только их. Не запускайте тесты параллельно
с изменением миграций. При заданном тестовом URL ошибка подключения является
ошибкой теста; отсутствие URL означает пропуск локальных интеграционных тестов.

После работы остановите и удалите только созданный выше одноразовый контейнер
и его временный volume:

```powershell
docker stop characters-test-local
docker rm --volumes characters-test-local
```

CI в `.github/workflows/ci.yml` устанавливает Python 3.12 и uv 0.9.27,
синхронизирует lockfile через `--frozen`, запускает Ruff, mypy, unit-тесты
и обязательный отдельный этап интеграционных тестов с PostgreSQL 17.
Тестовые параметры передаются явно и не требуют `.env` или GitHub Secrets.
CI не выполняет деплой и не обращается к рабочей БД.

Ссылки: [uv в GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/),
[PostgreSQL service containers](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers).
