# Резервная копия и проверка восстановления

Persistent volume сохраняет данные при перезапуске контейнера, но не защищает
от ошибочного удаления или повреждения. Используйте логический dump PostgreSQL
17 и проверяйте его восстановлением в отдельную пустую БД. Эта инструкция
не задаёт расписание и срок хранения: владелец сервиса должен выбрать их,
место хранения, ограничения доступа и допустимую потерю данных отдельно.

Dump содержит данные пользователей и хеши секретов сессий. Храните его вне Git
и Docker build context в каталоге с ограниченным доступом; внешнюю копию
защищайте шифрованием. `.env` и ключ JWT сохраняются отдельно в защищённом
хранилище. `pg_dump` одной БД не сохраняет роли PostgreSQL и конфигурацию сервера.

## Создание копии

Команды PowerShell запускаются из корня проекта для нужного Compose project.
Убедитесь, что выбран нужный контейнер; если используете `-p`, `-f` или
`--env-file`, передавайте те же параметры каждому вызову Compose.

```powershell
$backupDir = Join-Path $env:LOCALAPPDATA 'CharactersService/backups'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$backupName = 'characters-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.dump'
$backupPath = Join-Path $backupDir $backupName
$dbContainer = docker compose ps -q db
if ($LASTEXITCODE -ne 0 -or -not $dbContainer) { throw 'Database container not found' }
docker compose exec -T db sh -c 'pg_dump --format=custom --no-owner --no-acl --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --file=/tmp/characters-backup.dump'
if ($LASTEXITCODE -ne 0) { throw 'Backup failed' }
docker cp "${dbContainer}:/tmp/characters-backup.dump" $backupPath
if ($LASTEXITCODE -ne 0) { throw 'Copy failed' }
Get-FileHash -Algorithm SHA256 -LiteralPath $backupPath
docker compose exec -T db rm /tmp/characters-backup.dump
```

Бинарный dump записывается сначала внутри контейнера, затем копируется через
`docker cp`: текстовое перенаправление PowerShell не используется. Запишите
в журнал копий время, версию приложения/commit, Alembic revision, SHA256,
результат восстановления. Параллельные backup-задачи с этим именем временного
файла не запускайте. Миграции во время копирования не выполняйте.

## Проверка восстановления

Используйте отдельный PostgreSQL 17 и новую БД, например из инструкции
[тестового окружения](testing.md). Подставьте имя именно тестового контейнера;
имя БД `characters_test_restore` должно ещё не существовать. Не используйте
`--clean` и не восстанавливайте поверх рабочей БД.

```powershell
$restoreContainer = 'characters-test-local'
$restoreUser = 'characters_test'
docker cp $backupPath "${restoreContainer}:/tmp/characters-restore.dump"
if ($LASTEXITCODE -ne 0) { throw 'Copy failed' }
docker exec $restoreContainer createdb --username=$restoreUser --template=template0 characters_test_restore
if ($LASTEXITCODE -ne 0) { throw 'Create isolated database failed' }
docker exec $restoreContainer pg_restore --exit-on-error --single-transaction --no-owner --no-acl --username=$restoreUser --dbname=characters_test_restore /tmp/characters-restore.dump
if ($LASTEXITCODE -ne 0) { throw 'Restore failed' }
docker exec $restoreContainer psql --username=$restoreUser --dbname=characters_test_restore --set=ON_ERROR_STOP=1 --command='SELECT version_num FROM alembic_version; SELECT count(*) FROM users; SELECT count(*) FROM campaigns; SELECT count(*) FROM characters;'
if ($LASTEXITCODE -ne 0) { throw 'Verification failed' }
docker exec $restoreContainer rm /tmp/characters-restore.dump
```

Сравните revision, количества и заранее выбранные контрольные записи с данными
копии. При активных записях в исходную БД более поздние счётчики могут отличаться;
для контрольной проверки остановите запись на время снятия ожидаемых значений
и dump. На восстановленной БД проверьте запуск API, readiness, чтение кампании
и персонажа. Не считайте один успешный `pg_restore` полной проверкой приложения.

При реальном восстановлении сначала ограничьте запись, сохраните повреждённую
БД для расследования, проверьте новую БД и только затем отдельно согласуйте
переключение приложения. После восстановления сессии и секреты требуют
отдельного решения оператора: копия может содержать ранее отозванные сессии.
Не удаляйте исходную БД/volume в рамках проверки резервной копии.

Основание: [PostgreSQL 17 SQL dump и восстановление](https://www.postgresql.org/docs/17/backup-dump.html).
