# High-Level Workflow

→ идея
→ superpowers skills
→ тесты
→ реализация
→ ADR/docs update

---

# Структура проекта

```text
specs/                          — Архитектурные спецификации (INDEX.md — точка входа)
  decisions/                    — Architecture Decision Records

src/                            — Исходный код
```

## Виртуальное окружение

Зависимости управляются через `.venv/` (Python virtual environment). Всегда устанавливай пакеты внутри `.venv`:

```bash
.venv/bin/pip install <package>
```

НЕ используй `pip install --break-system-packages` или установку вне `.venv`.
Инструкции по использованию виртуального окружения также должны передаваться суб-агентам при использовании подхода subagent-driven-development.

---

# Superpowers Skills (MCP Server)

MCP-сервер `superpowers` предоставляет 14 скиллов, доступных как инструменты/промпты:

| Скилл | Назначение |
|-------|------------|
| brainstorming | Творческая работа, исследование дизайна, уточнение требований |
| writing-plans | Небольшие планы реализации с путями файлов и шагами TDD |
| executing-plans | Пакетное выполнение с контрольными точками ревью |
| subagent-driven-development | Один суб-агент на задачу + двухэтапное ревью кода |
| dispatching-parallel-agents | Распределение независимых задач по конкурентным агентам |
| test-driven-development | Цикл RED-GREEN-REFACTOR |
| systematic-debugging | 4-фазный анализ первопричин |
| verification-before-completion | Запуск верификации перед завершением задачи |
| requesting-code-review | Отправка код-ревью с категоризацией замечаний по критичности |
| receiving-code-review | Техническая строгость при обработке фидбэка |
| using-git-worktrees | Изолированные worktree для параллельных фич |
| finishing-a-development-branch | Merge, PR или очистка |
| writing-skills | Создание/тестирование/развёртывание новых скиллов |
| using-superpowers | Обзор системы скиллов и руководство по использованию |

Типичный workflow с superpowers:

```text
идея
→ brainstorming (исследовать дизайн)
→ writing-plans (создать план реализации)
→ test-driven-development или subagent-driven-development
→ verification-before-completion
→ requesting-code-review
→ finishing-a-development-branch
```

Используй `list_skills` для просмотра доступных скиллов, `recommend_skills` для выбора скиллов под задачу, `compose_workflow` для построения упорядоченного workflow из описания цели.

---

# Система индексации кода

К проекту подключена система индексации на основе двух инструментов:

1. **codebase-memory-mcp** — граф знаний кодовой базы (2060 узлов, 4629 связей). Предоставляет поиск по именам функций/классов, трассировку вызовов, анализ архитектуры и потока данных. Рекомендуется для навигации по коду и понимания связей между модулями.

2. **Kilo Codebase Indexing** (`semantic_search`) — эмбеддинг-поиск, понимающий смысл запроса. Модель: `perplexity/pplx-embed-v1-4b` (провайдер OpenRouter). Рекомендуется для поиска по смыслу, когда неизвестны точные имена символов или файлов.

Дополнительно: `specs/` + `vibespec-update` — для работы с intentional architecture, контрактами и ADR.

При необходимости используй `semantic_search` и `search_graph` (из codebase-memory-mcp) для быстрого поиска по коду.

---

# Важные правила

## НУЖНО

- Держи specs небольшими.
- Позволяй архитектуре эволюционировать.
- Проверяй задачи, сгенерированные AI.
- Используй инкрементальные улучшения.
- Фиксируй важные решения.

## НЕ НУЖНО

- Генерировать гигантскую архитектуру заранее.
- Создавать enterprise-сложность для MVP.
- Реализовывать огромные фичи за один шаг.
- Полагаться только на память чата.
- Позволять AI определять объём продукта в одиночку.

---

# Рекомендуемый ежедневный workflow

→ superpowers brainstorming (исследовать дизайн, уточнить требования)
→ superpowers writing-plans (план реализации с путями файлов и шагами TDD)
→ superpowers test-driven-development или subagent-driven-development
→ реализация
→ тесты
→ superpowers verification-before-completion
→ ADR/docs update
→ superpowers requesting-code-review
→ superpowers finishing-a-development-branch (merge, PR или очистка)

Для альтернативных workflow используйте `compose_workflow` из superpowers для генерации подходящей последовательности.

Планирование изменений (включая описание дизайн-плана) по методологии superpowers ведется в директории docs/superpowers/, как это предусмотрено по умолчанию скиллами superpowers. Папка specs/ описывает документацию проекта в целом, в папке .misc/ находятся различные дополнительные материалы, которые я обрабатываю вручную.