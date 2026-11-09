# Скрипты бэкапа и восстановления БД — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить консольные скрипты полного бэкапа и восстановления таблицы `resolved_purls` (CSV.gz + `COPY`), справочные инструкции в «Управлять БД» и README.

**Architecture:** Два хостовых bash-скрипта в `scripts/` работают через `docker compose exec db psql`, поэтому не требуют локального PostgreSQL-клиента и не зависят от образа приложения. Формат — CSV.gz с четырьмя колонками. `db_restore.sh` по умолчанию сливает данные (`ON CONFLICT DO NOTHING`, существующие строки побеждают), а `--mode replace` полностью заменяет таблицу.

**Tech Stack:** bash, Docker Compose, PostgreSQL 16 (`psql`, `COPY`), Python/pytest (интеграционный тест), Vue 3 + vue-i18n + vitest (справка в UI).

**Spec:** `docs/superpowers/specs/2026-11-09-db-backup-restore-scripts-design.md`

## Global Constraints

- Бэкапится только таблица `resolved_purls`; `jobs`, настройки и файлы `data/` не входят.
- Колонки строго: `purl,repository_url,resolver,resolved_at`; UTF-8, запятая, заголовок.
- Экспорт с `PGTZ=UTC`; строки упорядочены по `purl`.
- `merge` — режим по умолчанию; существующие строки целевой БД не изменяются.
- `replace` требует `--yes` или интерактивного подтверждения.
- Скрипты запускаются на хосте, используют `docker compose -f docker-compose.yml exec -T db psql`.
- Логи показывают режим, файл и счётчики `inserted/skipped/total`.
- Ограничение доступа к файлам бэкапа: `umask 077`.
- Ошибки — ненулевой код возврата; staging-таблица удаляется всегда.

## Review Focus

- Повреждённый/не-gzip файл: `db_restore.sh` завершается ненулевым кодом, staging-таблица не остаётся.
- Дубликаты `purl` внутри файла: merge не падает, лишние считаются `skipped`.
- На целевом стенде уже есть строки: merge их не перезаписывает.
- `--mode replace` без `--yes` в неинтерактивном запуске: отказ без изменения данных.
- Сервис `db` не запущен: понятная ошибка; бэкап не оставляет частичный файл (`.tmp` + `mv`).

---

### Task 1: Скрипт полного бэкапа

**Files:**
- Create: `scripts/db_backup.sh`
- Modify: `.gitignore`
- Test: `tests/test_db_backup_scripts.py`

**Interfaces:**
- Consumes: запущенный сервис `db` из `docker-compose.yml`.
- Produces: `scripts/db_backup.sh [-o FILE] [--keep N] [-v]`; переменные окружения `DB_USER` (по умолчанию `sbom`), `DB_NAME` (`sbom`), `BACKUP_DIR` (`backups`). Файл: `backups/sbom_purls_YYYYMMDD-HHMMSS.csv.gz`, CSV с заголовком `purl,repository_url,resolver,resolved_at`.

- [ ] **Step 1: Написать интеграционный тест бэкапа**

Создать `tests/test_db_backup_scripts.py` с помощником, который пропускает тесты, если `docker compose ps --status running --services` не содержит `db`, создаёт отдельную БД `sbom_backup_test_<random>`, применяет `src/purl_resolver/storage/schema.sql` и удаляет её после теста. Тест проверяет: файл создаётся, читается `gzip`+`csv.DictReader`, содержит 4 колонки и все посеянные строки, а в stdout есть путь и количество строк.

```python
def test_backup_creates_csv_gz_with_all_columns(test_db, tmp_path):
    out = tmp_path / "out.csv.gz"
    result = run_script(SCRIPT_BACKUP, "-o", str(out), env={"DB_NAME": test_db})
    assert result.returncode == 0
    assert out.exists()
    with gzip.open(out, "rt", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["purl", "repository_url", "resolver", "resolved_at"]
        rows = list(reader)
    assert {r["purl"] for r in rows} == {"pkg:pypi/alpha", "pkg:pypi/beta"}
    assert "rows: 2" in result.stdout
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `.venv/bin/python -m pytest tests/test_db_backup_scripts.py::test_backup_creates_csv_gz_with_all_columns -v`
Expected: FAIL (скрипт отсутствует или не исполняется).

- [ ] **Step 3: Реализовать `scripts/db_backup.sh`**

Требования: `set -euo pipefail`, переход в корень репозитория по `BASH_SOURCE`, `umask 077`, проверки `docker`/`gzip`/запущенного `db`, `mkdir -p "$BACKUP_DIR"`, запись во временный `<file>.tmp` и `mv` после успеха. Экспорт:

```bash
docker compose -f docker-compose.yml exec -T -e PGTZ=UTC db \
  psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
  -c "COPY (SELECT purl, repository_url, resolver, resolved_at
             FROM resolved_purls ORDER BY purl)
      TO STDOUT WITH (FORMAT csv, HEADER true)" \
  | gzip > "$TMP_FILE"
```

Количество строк получать отдельным `psql -tAc "SELECT count(*) FROM resolved_purls"` и печатать `rows: N`. Поддержать `--keep N` (удаление старых `sbom_purls_*.csv.gz`, оставить N последних), `-v`, `-h/--help`. Добавить `backups/` в `.gitignore`, сделать скрипт исполняемым.

- [ ] **Step 4: Запустить тест и убедиться, что он проходит**

Run: `.venv/bin/python -m pytest tests/test_db_backup_scripts.py::test_backup_creates_csv_gz_with_all_columns -v`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add scripts/db_backup.sh tests/test_db_backup_scripts.py .gitignore
git commit -m "feat: add full database backup script"
```

### Task 2: Скрипт восстановления (merge по умолчанию, replace явно)

**Files:**
- Create: `scripts/db_restore.sh`
- Modify: `tests/test_db_backup_scripts.py`

**Interfaces:**
- Consumes: файл из Task 1 (`purl,repository_url,resolver,resolved_at`, CSV.gz).
- Produces: `scripts/db_restore.sh FILE [--mode merge|replace] [--yes]`; те же `DB_USER`/`DB_NAME`; в stdout строки `mode: merge|replace`, `file: ...`, `inserted: N`, `skipped: N`, `total: N`.

- [ ] **Step 1: Добавить падающие тесты восстановления**

В `tests/test_db_backup_scripts.py` добавить тест полного цикла: после бэкапа изменить существующую строку в целевой БД, добавить строку, которой нет в файле, и удалить одну строку из файла. Затем:
- `db_restore.sh FILE` → в stdout `mode: merge`; изменённая строка осталась целевой (не перезаписана), отсутствующий PURL добавлен, целевая дополнительная строка сохранена;
- `db_restore.sh FILE --mode replace --yes` → в stdout `mode: replace`; таблица содержит ровно строки из файла;
- битый файл (`b"not gzip"`) → ненулевой код возврата;
- `--mode replace` без `--yes` при `stdin=/dev/null` → ненулевой код возврата, данные не изменены.

- [ ] **Step 2: Запустить новые тесты и убедиться, что они падают**

Run: `.venv/bin/python -m pytest tests/test_db_backup_scripts.py -v`
Expected: FAIL (скрипта восстановления нет).

- [ ] **Step 3: Реализовать `scripts/db_restore.sh`**

Общие требования: `set -euo pipefail`, `umask 077`, проверка файла, `docker`/`gzip`, запущенного `db`, лог `[restore <ts>] mode: ...`.

`merge`:
1. `CREATE TABLE IF NOT EXISTS resolved_purls_import (LIKE resolved_purls INCLUDING DEFAULTS); TRUNCATE resolved_purls_import;`
2. `gunzip -c "$FILE" | docker compose ... psql ... -c "\\copy resolved_purls_import (purl, repository_url, resolver, resolved_at) FROM STDIN WITH (FORMAT csv, HEADER true)"`
3. одним SQL-запросом вставить и посчитать:
```sql
WITH ins AS (
  INSERT INTO resolved_purls (purl, repository_url, resolver, resolved_at)
  SELECT purl, repository_url, resolver, resolved_at FROM resolved_purls_import
  ON CONFLICT (purl) DO NOTHING
  RETURNING 1
)
SELECT (SELECT count(*) FROM resolved_purls_import),
       (SELECT count(*) FROM ins);
```
4. `DROP TABLE IF EXISTS resolved_purls_import` (и в `trap ... EXIT` для ошибок).

`replace`: подтверждение (TTY `read` или `--yes`), проверка заголовка, загрузка в staging, отказ при нулевом числе строк, затем в одной транзакции `TRUNCATE resolved_purls` и `INSERT ... SELECT DISTINCT ON (purl) ... ORDER BY purl, resolved_at DESC`; вывод `inserted/total`.

- [ ] **Step 4: Запустить тесты и убедиться, что они проходят**

Run: `.venv/bin/python -m pytest tests/test_db_backup_scripts.py -v`
Expected: PASS (или SKIP, если Docker/`db` недоступны).

### Task 3: Справка в «Управлять БД»

**Files:**
- Create: `frontend/src/components/db/DbBackupHelp.vue`
- Modify: `frontend/src/views/DatabaseAdmin.vue`
- Modify: `frontend/src/i18n/locales/ru.json`
- Modify: `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/views/DatabaseAdmin.test.ts`

**Interfaces:**
- Produces: элемент `[data-role="db-backup-help"]` со ссылками на `scripts/db_backup.sh` и `scripts/db_restore.sh`; ключи `dbAdmin.backupHelp.*` в обоих языках.

- [ ] **Step 1: Написать падающий тест**

В `DatabaseAdmin.test.ts` добавить тест, монтирующий страницу и проверяющий наличие `[data-role="db-backup-help"]` и текста `scripts/db_backup.sh` / `scripts/db_restore.sh`.

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `npm --prefix frontend run test -- DatabaseAdmin.test.ts`
Expected: FAIL (элемента нет).

- [ ] **Step 3: Реализовать компонент и тексты**

`DbBackupHelp.vue` — `<details class="backup-help" data-role="db-backup-help">` с `<summary>{{ t('dbAdmin.backupHelp.title') }}</summary>`, кратким вступлением, командами в `<pre>` и примечанием про `--mode replace`. Подключить в `DatabaseAdmin.vue` после `DbImportModal`. Добавить ключи `backupHelp.title/intro/backup/restore/replace/note` в `ru.json` и `en.json`.

- [ ] **Step 4: Запустить тест и сборку**

Run: `npm --prefix frontend run test -- DatabaseAdmin.test.ts`
Expected: PASS.

Run: `npm --prefix frontend run build`
Expected: success.

### Task 4: README и спецификации

**Files:**
- Modify: `README.md`
- Modify: `specs/domains/web-ui.md`
- Modify: `specs/INDEX.md`

- [ ] **Step 1: Добавить раздел в README**

Рядом с «Updating» добавить «Database backup and restore» с командами `db_backup.sh`, `db_restore.sh` (merge по умолчанию) и `--mode replace --yes` с предупреждением об удалении отсутствующих в файле строк.

- [ ] **Step 2: Обновить спецификации**

В `specs/domains/web-ui.md` описать справочный блок в разделе `/db-admin` и новый компонент; в `specs/INDEX.md` добавить строку task mapping для бэкапа/восстановления БД.

- [ ] **Step 3: Полная проверка**

Run: `bash -n scripts/db_backup.sh scripts/db_restore.sh`
Expected: без ошибок.

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (e2e при необходимости с `SKIP_E2E=1`).

Run: `npm --prefix frontend run test`
Expected: PASS.

Run: `npm --prefix frontend run build`
Expected: success.
