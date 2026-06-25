Общее описание назначения и структуры проекта sbom-helper доступно в specs/INDEX.md (и в файлах, на которые есть ссылки в INDEX.md). specs/META.md определяет формат и правила обновления спецификаций. Для исследования архитектуры проекта используй MCP-сервер codebase-memory-mcp (название проекта: "home-administrator-Desktop-projects-sbom-helper").

Общие правила работы описаны в .misc/WORKFLOW.md.

Термины, используемые в текущем проекте, описаны в файле CONTEXT.md

Разработка ведется в ОС Ubuntu с использованием IDE VS Code и расширения Kilo Code.

Для планирования, внедрения и тестирования изменений используй скиллы из набора "superpowers". Для начала работы со скиллами используй скилл "superpowers:superpowers_using-superpowers". Для подключения нужных скиллов используй MCP-сервер superpowers-mcp.

### Расположение helper-скриптов superpowers

Helper-скрипты скиллов (не сами скиллы, а утилиты вроде `task-brief`, `review-package`) лежат в `~/.superpowers-mcp/skills/skills/<skill-name>/scripts/`:

- `~/.superpowers-mcp/skills/skills/subagent-driven-development/scripts/` — `task-brief PLAN N [OUTFILE]` (извлекает текст задачи в файл), `review-package BASE HEAD` (готовит diff для ревьюера), `sdd-workspace`
- `~/.superpowers-mcp/skills/skills/brainstorming/scripts/` — `start-server.sh`, `stop-server.sh` (для visual companion)
- `~/.superpowers-mcp/skills/skills/systematic-debugging/find-polluter.sh`

Перед использованием скилла `subagent-driven-development` сначала запускай `task-brief` для генерации брифа задачи и `review-package BASE HEAD` для генерации diff-файла перед ревью.

Перед структурными изменениями сначала читай соответствующий spec из specs/.

Для запуска кода на python используй виртуальное окружение .venv. Также передавай эту инструкцию по использованию виртуального окружения суб-агентам при необходимости, чтобы они не пытались запускать код напрямую. При необходимости установки новых python-модулей, также вызывай pip внутри виртуального окружения.

Для получения актуальной документации библиотек и фреймворков проекта (FastAPI, Pydantic, asyncpg, httpx, pytest, vue.js и др.) используй MCP-сервер context7. Доступны инструменты: context7_resolve-library-id и context7_query-docs.

 Для исследования проекта рекомендуется использовать документацию в папке specs, механизм индексирования Kilo Code и MCP-сервер codebase-memory-mcp.