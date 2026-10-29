# «Исправить SBOM» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в sbom-helper раздел «Исправить SBOM», который применяет выбранные формальные правки к CycloneDX JSON и возвращает исправленный документ, статистику по правилам и отчёт об оставшихся несоответствиях.

**Architecture:** Чистый модуль `sbom/fixer.py` с явной Pydantic-моделью опций и упорядоченным конвейером из 21 правила; переупорядочивание — отдельный финальный проход. HTTP-слой `routes/sbom_fix.py` вызывает `fix_sbom`, а `SbomFixOptionsStore` хранит набор опций в JSON-файле. Frontend — Vue 3 SPA: страница `SbomFixer.vue`, API-клиент, типы, маршрут, навигация, плитка и i18n.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, ruff; Vue 3, TypeScript, Vue Router, Pinia, vue-i18n, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-26-sbom-fixer-design.md`

## Global Constraints

- Python запускать только через `.venv`: `.venv/bin/python -m pytest`, `.venv/bin/ruff check src tests`.
- Frontend-команды: `npm test --prefix frontend`, `npm run build --prefix frontend`.
- Новых внешних зависимостей не добавлять; для опций использовать уже имеющийся Pydantic.
- Входной SBOM не мутировать: `copy.deepcopy`; результат не должен зависеть от мутаций входного объекта.
- Поле `group` не изменять нигде.
- Удалять `hashes` только как непосредственный ключ компонента; `externalReferences[].hashes` не трогать.
- Переупорядочивание выполняется последним проходом; после него никакие правила не меняют документ.
- Issues создаются только в `_collect_issues` по итоговому документу; правила issues не порождают.
- Все опции по умолчанию `True`, кроме `metadata_component.remove_purl` и `components.fill_missing_gost_properties`; `spec_version = "1.7"`.
- `stats` содержит все включённые правила в каноническом порядке, включая нулевые; `changed = any(count > 0)`.
- Ошибки API — машиночитаемые коды без `message`; 400/413 возвращать через `JSONResponse` с верхнеуровневым `error`.
- Не требовать PostgreSQL, очередь или фоновые задачи.
- Все пользовательские строки — через `vue-i18n`; структура `en.json` и `ru.json` идентична.
- Максимальный размер файла — `sbom_settings.max_file_size`.
- Работать в текущем worktree на `main`, без отдельных веток и git worktree. Коммиты разрешены; коммитить только файлы текущей задачи.

## Review Focus

- [ ] Некорректные типы внутри компонента (`component` не объект, `properties`/`externalReferences`/`components` не массив, `hashes` любого типа) не должны вызывать исключение и не должны мешать обработке соседних компонентов — тесты в Task 5 и Task 6.
- [ ] Входной документ не мутируется, включая вложенные массивы и `externalReferences[].hashes` — тест в Task 5.
- [ ] Финальный reorder действительно последний: при совместных `add_timestamp`, `rename_supplier`, фильтрах и reorder `timestamp` стоит первым, `manufacturer` — четвёртым, удалённые элементы отсутствуют — тест в Task 4.
- [ ] Повреждённый или частичный файл опций и ошибка `GET /options` не блокируют страницу: используются дефолты, форма остаётся работоспособной — тесты в Task 8 и Task 12.
- [ ] Большой список issues не рендерится в DOM до раскрытия спойлера, при этом API возвращает полный список — тест в Task 13.

---

### Task 1: Модель опций, результат и каркас `fix_sbom`

**Files:**
- Create: `src/purl_resolver/sbom/fixer.py`
- Modify: `src/purl_resolver/sbom/__init__.py`
- Test: `tests/test_sbom_fixer.py`

**Interfaces:**
- Produces:
  - `RootFixOptions`, `MetadataComponentFixOptions`, `MetadataFixOptions`, `ComponentsFixOptions`, `SbomFixOptions` (Pydantic v2, поля и дефолты — как в §9.2 дизайна).
  - `FixStat(rule_id: str, count: int)`, `FixIssue(code: str, path: str, component: str | None = None, details: dict[str, Any] = field(default_factory=dict))`, `SbomFixResult(changed: bool, fixed_sbom: dict, stats: list[FixStat], issues: list[FixIssue])`.
  - `RULE_IDS: tuple[str, ...]` в каноническом порядке §7.
  - `fix_sbom(data: dict, options: SbomFixOptions, now: datetime | None = None) -> SbomFixResult`.
  - `SPEC_VERSION_PATTERN = re.compile(r"^\d+\.\d+$")`, `ALLOWED_SPEC_VERSIONS = {"1.6", "1.7"}`.
- `spec_version` валидируется `@field_validator` независимо от `set_spec_version`; пустая строка и значения вне `^\d+\.\d+$` дают `pydantic.ValidationError`.

- [ ] **Step 1: Написать падающие тесты модели и каркаса**

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from purl_resolver.sbom.fixer import RULE_IDS, SbomFixOptions, fix_sbom


def test_defaults_all_on_except_two_rules():
    o = SbomFixOptions()
    assert o.root.set_spec_version is True
    assert o.root.spec_version == "1.7"
    assert o.metadata.add_timestamp is True
    assert o.metadata.component.remove_purl is False
    assert o.components.fill_missing_gost_properties is False
    assert o.components.filter_properties is True


@pytest.mark.parametrize("value", ["", "1", "1.7.0", "v1.7", "1,7", 1.7])
def test_invalid_spec_version_rejected(value):
    with pytest.raises(ValidationError):
        SbomFixOptions(root={"spec_version": value})


def test_all_enabled_rules_yield_21_stats_in_canonical_order():
    options = SbomFixOptions(
        metadata={"component": {"remove_purl": True}},
        components={"fill_missing_gost_properties": True},
    )
    result = fix_sbom(
        {"bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1}, options
    )
    assert [stat.rule_id for stat in result.stats] == list(RULE_IDS)
    assert len(result.stats) == 21


def test_fix_sbom_copies_input_and_emits_zero_stats_for_enabled_rules():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7"}
    result = fix_sbom(data, SbomFixOptions())
    assert result.fixed_sbom == data
    assert result.fixed_sbom is not data
    assert result.changed is False
    assert len(result.stats) == 19
    assert all(stat.count == 0 for stat in result.stats)
    assert [stat.rule_id for stat in result.stats] == [
        "root.reorder", "root.set_spec_version", "root.remove_dependencies",
        "root.remove_services", "root.increment_version", "metadata.add_timestamp",
        "metadata.reorder", "metadata.remove_properties", "metadata.remove_tools",
        "metadata_component.reorder", "metadata_component.remove_external_references",
        "metadata_component.remove_properties", "metadata_component.remove_scope",
        "metadata_component.rename_supplier", "components.reorder",
        "components.remove_hashes", "components.remove_scope",
        "components.filter_external_references", "components.filter_properties",
    ]
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -v`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` для `purl_resolver.sbom.fixer`.

- [ ] **Step 3: Реализовать модели, dataclass-результаты и каркас**

`fix_sbom` на этом шаге: `fixed = copy.deepcopy(data)`, `stats = [FixStat(rule_id=rid, count=0) for rid in _enabled_rule_ids(options)]`, `issues = []`, `changed = False`. `_enabled_rule_ids(options)` возвращает `RULE_IDS`, отфильтрованные по соответствующему булеву полю.

- [ ] **Step 4: Экспортировать публичный API**

В `src/purl_resolver/sbom/__init__.py` добавить в импорты и `__all__`: `fix_sbom`, `SbomFixOptions`, `SbomFixResult`, `FixStat`, `FixIssue`.

- [ ] **Step 5: Запустить тесты и ruff**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -v && .venv/bin/ruff check src tests`
Expected: PASS, ruff без ошибок.

- [ ] **Step 6: Чекпойнт**

Убедиться, что рабочее дерево содержит только ожидаемые изменения; закоммитить только файлы задачи.

---

### Task 2: Финальный reorder всех уровней

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py`
- Test: `tests/test_sbom_fixer.py`

**Interfaces:**
- Produces:
  - `_reorder(obj: dict, priority: tuple[str, ...]) -> tuple[dict, bool]` — новый dict, приоритетные ключи впереди, остальные в исходном относительном порядке; флаг `True`, если порядок ключей изменился.
  - `_apply_reorders(data: dict, options: SbomFixOptions, counts: dict[str, int]) -> dict` — финальный проход; переупорядочивает `metadata.component`, `metadata`, каждый компонент pre-order и корень; заполняет `counts` для четырёх reorder-правил.
  - Константы приоритетов: `ROOT_PRIORITY`, `METADATA_PRIORITY`, `METADATA_COMPONENT_PRIORITY`, `COMPONENT_PRIORITY`.

- [ ] **Step 1: Написать падающие тесты reorder**

Проверить:
- корень: `bomFormat`, `specVersion`, `serialNumber`, `version`, `metadata`, `components`, `annotations`, затем прочие; `$schema` уходит в конец; отсутствующие ключи пропускаются;
- `metadata`: `timestamp`, `component`, прочие;
- `metadata.component`: `type`, `name`, `version`, `manufacturer`, прочие;
- компонент: `type`, `name`, `version`, `purl`, `externalReferences`, `properties`, `components`, прочие;
- `components.reorder` считает каждый компонент, у которого порядок изменился, включая вложенные;
- выключенный reorder не меняет порядок и не попадает в `stats`.

Пример ключевого теста:

```python
def test_root_reorder_puts_schema_last():
    data = {
        "$schema": "x", "components": [], "version": 1,
        "serialNumber": "urn:uuid:1", "specVersion": "1.7",
        "bomFormat": "CycloneDX", "annotations": [],
    }
    result = fix_sbom(data, SbomFixOptions())
    assert list(result.fixed_sbom) == [
        "bomFormat", "specVersion", "serialNumber", "version",
        "components", "annotations", "$schema",
    ]
    assert result.stats[0].count == 1
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -k reorder -v`
Expected: FAIL — порядок не меняется, счётчики нулевые.

- [ ] **Step 3: Реализовать reorder**

Вызывать `_apply_reorders` в `fix_sbom` после всех мутаций. Для `metadata.component` и компонентов менять содержимое исходного dict (clear/update) либо переназначать ссылки; важно, чтобы финальный `fixed_sbom` содержал переупорядоченные вложенные объекты. Переупорядочивать только объекты нужного типа; массивы не переупорядочивать.

- [ ] **Step 4: Запустить тесты и ruff**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -v && .venv/bin/ruff check src tests`
Expected: PASS.

---

### Task 3: Правила корневого объекта

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py`
- Test: `tests/test_sbom_fixer.py`

**Interfaces:**
- Produces: `_apply_root_rules(data: dict, options: SbomFixOptions, counts: dict[str, int]) -> None`.
- Счётчики: `root.set_spec_version`, `root.remove_dependencies`, `root.remove_services`, `root.increment_version`.

- [ ] **Step 1: Написать падающие тесты**

Проверить:
- `specVersion` заменяется значением `options.root.spec_version.strip()`; отсутствующий ключ добавляется; одинаковое значение даёт 0;
- `dependencies`/`services` удаляются, включая пустые массивы; отсутствие даёт 0;
- `version` — целое (не `bool`) увеличивается на 1; отсутствие, строка, `bool` не меняются и дают 0;
- при выключенном правиле поле не меняется и правило отсутствует в `stats`;
- при `root.reorder=false` и добавлении `specVersion` ключ оказывается в конце документа;
- любое правило с `count > 0` выставляет `result.changed is True`.

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -k "root or spec_version or version or dependencies or services" -v`
Expected: FAIL.

- [ ] **Step 3: Реализовать правила**

Порядок применения внутри группы: `set_spec_version`, `remove_dependencies`, `remove_services`, `increment_version`. Проверка целого: `isinstance(v, int) and not isinstance(v, bool)`.

- [ ] **Step 4: Запустить тесты и ruff**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -v && .venv/bin/ruff check src tests`
Expected: PASS.

---

### Task 4: Правила `metadata` и `metadata.component`

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py`
- Test: `tests/test_sbom_fixer.py`

**Interfaces:**
- Produces:
  - `_apply_metadata_rules(data: dict, options: SbomFixOptions, counts: dict[str, int], now: datetime) -> None`.
  - `_add_timestamp(metadata: dict, now: datetime) -> int`;
  - `_format_timestamp(now: datetime) -> str` — naive трактуется как UTC, aware переводится в UTC, формат `YYYY-MM-DDTHH:MM:SSZ`.
- Счётчики: `metadata.add_timestamp`, `metadata.remove_properties`, `metadata.remove_tools`, `metadata_component.*`.

- [ ] **Step 1: Написать падающие тесты**

Проверить:
- `add_timestamp`: отсутствие/`null`/`""` → `now`; существующая строка (включая неверный формат) не перезаписывается; `int` не перезаписывается; при отсутствии `metadata` ничего не добавляется; naive `now` трактуется как UTC;
- `metadata.remove_properties` и `metadata.remove_tools` удаляют ключи; `tools` удаляется и как массив, и как объект;
- `metadata.component` удаляет `externalReferences`, `properties`, `purl`, `scope`; `remove_purl` по умолчанию не удаляет; `group` не меняется;
- `rename_supplier`: `manufacturer` считается отсутствующим, если ключа нет или значение `None`; в этом случае значение `supplier` переносится. Если `manufacturer` уже есть (в том числе `{}`), он сохраняется, `supplier` удаляется; `supplier: null` удаляется без создания `manufacturer`;
- при отсутствии/`null` `metadata.component` правила пропускаются;
- повторный запуск с тем же `now` не меняет `timestamp` (идемпотентность `add_timestamp`);
- финальный порядок: при дефолтных опциях `metadata` начинается с `timestamp`, затем `component`; `metadata.component` начинается с `type`, `name`, `version`, `manufacturer`.

Ключевой тест финального reorder:

```python
def test_timestamp_and_manufacturer_are_first_and_fourth_after_all_rules():
    data = {
        "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
        "metadata": {
            "supplier": {"name": "Vendor"},
            "component": {"supplier": {"name": "Vendor"}, "version": "1",
                          "name": "root", "type": "application", "group": "g"},
        },
    }
    result = fix_sbom(data, SbomFixOptions(), now=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
    assert list(result.fixed_sbom["metadata"])[:2] == ["timestamp", "component"]
    assert list(result.fixed_sbom["metadata"]["component"])[:4] == ["type", "name", "version", "manufacturer"]
    assert result.fixed_sbom["metadata"]["component"]["group"] == "g"
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -k "metadata or timestamp or supplier" -v`
Expected: FAIL.

- [ ] **Step 3: Реализовать правила**

Правила применяются только если `metadata` — `dict`, а `metadata.component` — `dict`. `add_timestamp` считать добавлением только при фактической установке значения. `rename_supplier` считать сработавшим, если ключ `supplier` был удалён. `metadata.component` может отсутствовать — пропустить без исключения.

- [ ] **Step 4: Запустить тесты и ruff**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -v && .venv/bin/ruff check src tests`
Expected: PASS.

---

### Task 5: Рекурсивные правила `components`

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py`
- Test: `tests/test_sbom_fixer.py`

**Interfaces:**
- Produces:
  - `_walk_components(root: dict, callback: Callable[[dict], None]) -> None` — pre-order по корневому `components` и вложенным `components`; не заходит в `metadata.component.components`; не-объекты пропускает.
  - `_apply_components_rules(data: dict, options: SbomFixOptions, counts: dict[str, int]) -> None`.
  - `_filter_external_references(refs: list) -> tuple[list, int]`, `_filter_properties(props: list) -> tuple[list, int]`, `_fill_gost_properties(component: dict) -> int`.

- [ ] **Step 1: Написать падающие тесты**

Проверить:
- обход на 3+ уровнях; вложенные компоненты обрабатываются;
- `components.remove_hashes` удаляет только непосредственный ключ, в том числе если `hashes` имеет неожиданный тип; `externalReferences[].hashes` сохраняется;
- `components.remove_scope` удаляет `scope` на всех уровнях;
- `filter_external_references` оставляет только объекты с `type` строго `vcs`/`source-distribution`; удаляет прочие, элементы без `type` и не-объекты; пустой массив сохраняется; счётчик — число удалённых элементов;
- `filter_properties` оставляет только `name`, начинающийся ровно с `GOST:` (регистрозависимо); не-строковый `name` и прочие удаляются; пустой массив сохраняется;
- `fill_missing_gost_properties`: отсутствие/`null` → создать `[]`; добавляются только недостающие `GOST:attack_surface` и `GOST:security_function` со значением `"no"`; существующие значения не меняются; не применяется к `metadata.component`;
- при совместном включении сначала выполняется фильтрация, затем добавление;
- неожиданные типы (`properties` не массив, вложенный `components` не массив, элемент массива не объект) не вызывают исключений;
- входной документ не мутируется (сравнить deepcopy до/после), включая сохранённые хэши внешних ссылок.

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -k "components or hashes or external or properties or gost" -v`
Expected: FAIL.

- [ ] **Step 3: Реализовать правила**

Порядок внутри компонента: удалить `hashes`, удалить `scope`, отфильтровать `externalReferences`, отфильтровать `properties`, затем при включённой опции заполнить ГОСТ-свойства. Не-массивы не фильтровать и не заполнять. Для `fill_missing_gost_properties` при отсутствии/`null` создать `[]`; при не-массиве пропустить.

- [ ] **Step 4: Запустить тесты и ruff**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -v && .venv/bin/ruff check src tests`
Expected: PASS.

---

### Task 6: Issues компонентов

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py`
- Test: `tests/test_sbom_fixer.py`

**Interfaces:**
- Produces: `_collect_component_issues(components: list, base_path: str, issues: list[FixIssue]) -> None` — рекурсивно, pre-order, с путями `$.components[i]` и `$.components[i].components[j]`. Функция приватная; она вызывается из `_collect_issues` в Task 7.
- `component` — `name`, если это непустая строка, иначе `None`; `details` — `{}` кроме `component.missing_gost_properties`.

- [ ] **Step 1: Написать падающие тесты**

Импортировать `FixIssue`, `_collect_component_issues` и вызывать helper напрямую:

```python
def test_collect_component_issues_reports_missing_fields():
    issues: list[FixIssue] = []
    _collect_component_issues([{"type": "library"}], "$.components", issues)
    assert [(i.code, i.path, i.component) for i in issues] == [
        ("component.missing_name", "$.components[0]", None),
        ("component.missing_version", "$.components[0]", None),
        ("component.missing_purl", "$.components[0]", None),
        ("component.missing_gost_properties", "$.components[0]", None),
        ("component.missing_source_reference", "$.components[0]", None),
    ]
```

Проверить коды §8.4:
- `component.invalid_entry` для не-объекта; остальные элементы обрабатываются;
- `component.missing_type/name/version/purl`;
- `component.invalid_properties` для не-массива; при этом `missing_gost_properties` не дублируется;
- `component.missing_gost_properties` для отсутствия/`null`/массива без одного или обоих свойств; `details.missing` в порядке `["GOST:attack_surface", "GOST:security_function"]`;
- `component.invalid_external_references` для не-массива; при этом `missing_source_reference` не дублируется;
- `component.missing_source_reference` для отсутствия/`null`/массива без `vcs`/`source-distribution`;
- исключения: непустой массив `components`; `GOST:provided_by` с непустым строковым `value`; `licenses` с `{"license": {"name": "Proprietary"}}`;
- `component.invalid_subcomponents` для не-массива; вложенный обход не выполняется;
- порядок кодов внутри компонента и pre-order вложенных;
- один дефект не попадает в отчёт несколько раз;
- неожиданные типы не вызывают исключений.

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -k "component_issues or gost or source_reference or subcomponents" -v`
Expected: FAIL — `_collect_component_issues` отсутствует.

- [ ] **Step 3: Реализовать проверки**

Проверять только элементы переданного массива и их вложенные `components`; `metadata.component` сюда не передаётся. Для `missing_source_reference` сначала проверить исключения, затем выдавать issue. Для `invalid_external_references`/`invalid_properties` не выполнять соответствующую проверку содержимого. `invalid_subcomponents` выдавать и не рекурсировать в не-массив.

- [ ] **Step 4: Запустить тесты и ruff**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -v && .venv/bin/ruff check src tests`
Expected: PASS.

---

### Task 7: Issues корня и `metadata`, интеграция отчёта

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py`
- Test: `tests/test_sbom_fixer.py`

**Interfaces:**
- Produces:
  - `_collect_issues(data: dict) -> list[FixIssue]` — единственный источник issues; вызывается в `fix_sbom` по итоговому документу.
  - `_collect_root_issues(data: dict, issues: list[FixIssue]) -> None`, `_collect_metadata_issues(data: dict, issues: list[FixIssue]) -> None` (приватные).
- Пути: `$`, `$.metadata`, `$.metadata.component`; порядок: корень → `metadata` → `metadata.component` → компоненты pre-order.

- [ ] **Step 1: Написать падающие тесты**

Проверить все коды §8.1–8.3 через `fix_sbom` с полностью выключенными правками или с документом, где дефекты остаются:
- `root.missing_spec_version`, `root.invalid_spec_version`, `root.spec_version_not_allowed` взаимоисключающие; пустая строка → `missing`, `null` → `missing`, не-строка → `invalid`, `"1.5"` → `not_allowed`;
- `root.missing_version` для отсутствия/`null`; `root.invalid_version` для строки, `bool` и float;
- `root.missing_metadata` / `root.invalid_metadata`; при них проверки `metadata.*` не выполняются;
- `root.invalid_components` для не-массива; отсутствие/`null`/пустой массив — не ошибка;
- `metadata.missing_timestamp` для отсутствия/`null`/пустой строки/не-строки; существующая неверная строка не даёт issue;
- `metadata.missing_component` / `metadata.invalid_component`; при них вложенные проверки не выполняются;
- `metadata_component.missing_type/name/version/manufacturer` для отсутствия, пустой строки и неверного типа; `manufacturer: null`, `{}`, `{"name": ""}` считаются отсутствием;
- интеграция: `fix_sbom` возвращает компонентные issues из Task 6 в общем порядке после root/metadata/metadata.component;
- `details` для `missing_gost_properties` сохраняется;
- один дефект не дублируется;
- в тестах дефектов, которые исправляются правилами (`specVersion`, `timestamp`), соответствующее правило явно выключается, иначе issue исчезает по итоговому документу.

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -k "issue or missing or invalid or not_allowed" -v`
Expected: FAIL — `issues` пуст.

- [ ] **Step 3: Реализовать проверки и интеграцию**

`fix_sbom` заменяет `issues = []` на `_collect_issues(fixed)`. `_collect_issues` проверяет корень, затем `metadata`, затем при наличии объекта `metadata.component`, затем вызывает `_collect_component_issues` для `data.get("components")`, если это массив. Не создавать issue для `bomFormat` и `serialNumber`. Для `metadata.timestamp` не проверять формат. Для `metadata.component` не проверять `purl`, `externalReferences`, `properties`, `scope`.

- [ ] **Step 4: Запустить тесты и ruff**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -v && .venv/bin/ruff check src tests`
Expected: PASS.

---

### Task 8: `SbomFixOptionsStore`

**Files:**
- Create: `src/purl_resolver/sbom_fix_options_store.py`
- Test: `tests/test_sbom_fix_options_store.py`

**Interfaces:**
- Produces: `SbomFixOptionsStore(path: str | Path | None = None)`; default `./data/sbom_fix_options.json`.
  - `load() -> SbomFixOptions`
  - `save(options: SbomFixOptions) -> None`
- `load`: файла нет → `SbomFixOptions()`; битый JSON/`OSError`/`ValidationError` → warning в лог и `SbomFixOptions()`; частичный JSON → Pydantic заполняет отсутствующие поля дефолтами.
- `save`: создать родительский каталог; `model_dump()` с `indent=2`, `ensure_ascii=False`, завершающий `\n`.

- [ ] **Step 1: Написать падающие тесты**

```python
def test_load_missing_file_returns_defaults(tmp_path):
    store = SbomFixOptionsStore(tmp_path / "missing.json")
    assert store.load() == SbomFixOptions()


def test_save_load_roundtrip_including_spec_version(tmp_path):
    store = SbomFixOptionsStore(tmp_path / "options.json")
    options = SbomFixOptions(root={"spec_version": "1.6"})
    store.save(options)
    assert store.load() == options


def test_corrupt_json_returns_defaults(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    assert SbomFixOptionsStore(path).load() == SbomFixOptions()


def test_partial_json_fills_defaults(tmp_path):
    path = tmp_path / "partial.json"
    path.write_text('{"root": {"reorder": false}}', encoding="utf-8")
    loaded = SbomFixOptionsStore(path).load()
    assert loaded.root.reorder is False
    assert loaded.root.set_spec_version is True
    assert loaded.metadata.add_timestamp is True
```

Дополнительно: невалидный `spec_version` → дефолты; переданный путь используется вместо пути по умолчанию; `save()` пишет JSON с отступом 2, `ensure_ascii=False` и завершающим `\n` (проверить содержимое файла с не-ASCII значением).

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `.venv/bin/python -m pytest tests/test_sbom_fix_options_store.py -v`
Expected: FAIL — модуль отсутствует.

- [ ] **Step 3: Реализовать store по образцу `IgnorePatternsStore`**

Логировать warning через `logging.getLogger(__name__)`; не пробрасывать ошибки чтения наружу. Ошибки записи не глотать — их обработает API.

- [ ] **Step 4: Запустить тесты и ruff**

Run: `.venv/bin/python -m pytest tests/test_sbom_fix_options_store.py -v && .venv/bin/ruff check src tests`
Expected: PASS.

---

### Task 9: API `POST /api/v1/sbom/fix` и `/api/v1/sbom/fix/options`

**Files:**
- Create: `src/purl_resolver/routes/sbom_fix.py`
- Modify: `src/purl_resolver/router.py`
- Modify: `src/purl_resolver/main.py`
- Test: `tests/test_sbom_fix_api.py`

**Interfaces:**
- Produces: `router` в `routes/sbom_fix.py` с тремя endpoint'ами.
- `POST /api/v1/sbom/fix`: `multipart/form-data`, `file: UploadFile`, `options: str | None = Form(None)`.
  - 200: `{"changed": bool, "fixed_sbom": dict, "stats": [{"rule_id","count"}], "issues": [{"code","path","component","details"}]}`.
  - 400 `invalid_json`, 400 `invalid_sbom` (с `detail`), 400 `invalid_options` (с `detail`), 413 `file_too_large` (с `max_size_mb`), 422 без файла.
- `GET /api/v1/sbom/fix/options`: 200 `{"options": {...}}`, всегда.
- `POST /api/v1/sbom/fix/options`: тело `{"options": {...}}`; 200 `{"status": "saved"}`; 400 `invalid_options`; 500 `options_save_failed`.
- `main.py` создаёт `app.state.sbom_fix_options_store = SbomFixOptionsStore()`; `router.py` подключает `sbom_fix_router`.

- [ ] **Step 1: Написать падающие API-тесты**

Тестовое приложение:

```python
@pytest.fixture
def client(tmp_path):
    test_app = FastAPI()
    test_app.state.sbom_fix_options_store = SbomFixOptionsStore(tmp_path / "options.json")
    test_app.include_router(router)
    with TestClient(test_app) as c:
        yield c
```

Проверить:
- 200 с корректным файлом и опциями; форма `changed`/`fixed_sbom`/`stats`/`issues`;
- не-ASCII `name` компонента возвращается без `\u`-экранирования;
- `options` не передан → встроенные дефолты (19 stats, изменения применяются), а не режим проверки;
- 400 `invalid_json`; 400 `invalid_sbom`; 400 `invalid_options` для невалидного JSON опций и для невалидного `spec_version`;
- 413 `file_too_large` через `monkeypatch.setattr("purl_resolver.routes.sbom_fix.sbom_settings.max_file_size", 10)`;
- 422 без `file`;
- GET options возвращает сохранённые или дефолтные;
- POST options сохраняет; последующий GET возвращает тот же набор;
- POST options с невалидными опциями → 400 `invalid_options`;
- POST options с телом не-JSON или телом без ключа `options` → 400 `invalid_options`;
- ошибка записи (`monkeypatch.setattr(SbomFixOptionsStore, "save", raise_oserror)`) → 500 `options_save_failed`.

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `.venv/bin/python -m pytest tests/test_sbom_fix_api.py -v`
Expected: FAIL — маршруты отсутствуют.

- [ ] **Step 3: Реализовать route**

Порядок в fix-endpoint: чтение файла → проверка размера → `json.loads` → `CycloneDXParser.parse` → разбор `options` (если `None`, `SbomFixOptions()`) → `fix_sbom(data, options)` → `JSONResponse`. Разбор `options`: `json.loads`, затем `SbomFixOptions.model_validate`; ловить `json.JSONDecodeError`, `ValidationError` и возвращать 400 `invalid_options` с текстом ошибки в `detail`.

Для POST options вручную читать `await request.json()`, проверить, что тело — объект с ключом `options`, затем `SbomFixOptions.model_validate`. `store.save` обернуть в `try/except OSError` → 500 `options_save_failed`.

- [ ] **Step 4: Подключить store и router**

`main.py`: импорт `SbomFixOptionsStore`; в lifespan рядом с `ignore_patterns_store` создать `app.state.sbom_fix_options_store`. `router.py`: импорт и `router.include_router(sbom_fix_router)`.

- [ ] **Step 5: Запустить тесты, ruff и проверить существующие API-тесты**

Run: `.venv/bin/python -m pytest tests/test_sbom_fix_api.py tests/test_api.py tests/test_images_list_converter.py -v && .venv/bin/ruff check src tests`
Expected: PASS.

---

### Task 10: Frontend-типы и API-клиент

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/sbom.ts`

**Interfaces:**
- Types: `RootFixOptions`, `MetadataComponentFixOptions`, `MetadataFixOptions`, `ComponentsFixOptions`, `SbomFixOptions`, `SbomFixStat`, `SbomFixIssue`, `SbomFixResponse`, `SbomFixOptionsResponse`.
- Functions:
  - `fixSbom(file: File, options: SbomFixOptions): Promise<SbomFixResponse>`
  - `getFixOptions(): Promise<SbomFixOptionsResponse>`
  - `saveFixOptions(options: SbomFixOptions): Promise<{ status: string }>`

- [ ] **Step 1: Добавить типы**

Типы повторяют §9.2 и §9.4: `spec_version` — строка; `details` — `Record<string, unknown>`; `fixed_sbom` — `unknown`; `component` — `string | null`.

- [ ] **Step 2: Добавить API-функции**

`fixSbom` создаёт `FormData`, добавляет `file` и `options` (`JSON.stringify(options)`), вызывает `apiFetch` с `method: 'POST'` и без ручного `Content-Type`. `getFixOptions` — GET; `saveFixOptions` — POST JSON `{ options }`.

- [ ] **Step 3: Проверить типы сборкой**

Run: `npm run build --prefix frontend`
Expected: сборка и `vue-tsc` без ошибок.

- [ ] **Step 4: Чекпойнт**

Убедиться, что существующие вызовы `../api/sbom` не сломаны.

---

### Task 11: Маршрут, навигация, плитка и базовые i18n-ключи

**Files:**
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/components/AppNav.vue`
- Modify: `frontend/src/views/HomePage.vue`
- Modify: `frontend/src/views/HomePage.test.ts`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/ru.json`

**Interfaces:**
- Маршрут `/fix-sbom`, name `fix-sbom`, view `../views/SbomFixer.vue`.
- `nav.sbomFixer`; плитка namespace `sbomFixer` с `title` и `subtitle`.
- Порядок: PURL Resolver → Enrich SBOM → Fix SBOM → Generate Images List → Manage Database → Settings.

- [ ] **Step 1: Обновить тест домашней страницы (падающий)**

Изменить ожидания на 6 плиток и маршруты:

```python
expectedRoutes = [
    '/purl-resolver', '/sbom-updater', '/fix-sbom',
    '/images-list-converter', '/db-admin', '/settings',
]
```

Заголовки: `Resolve PURL`, `Enrich SBOM`, `Fix SBOM`, `Generate Images List`, `Manage Database`, `Settings`.

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `npm test --prefix frontend -- HomePage.test.ts`
Expected: FAIL — 5 плиток.

- [ ] **Step 3: Реализовать маршрут, навигацию, плитку и ключи**

`router/index.ts`: добавить маршрут `/fix-sbom` до catch-all. `AppNav.vue`: добавить `{ path: '/fix-sbom', nameKey: 'nav.sbomFixer' }` между `sbom-updater` и `images-list-converter`. `HomePage.vue`: добавить `{ route: '/fix-sbom', ns: 'sbomFixer' }` на ту же позицию. В `en.json`/`ru.json` добавить `nav.sbomFixer` и `sbomFixer.title`/`sbomFixer.subtitle`; английский title — `Fix SBOM`, subtitle — смысл «upload CycloneDX and apply selected fixes»; русский — «Исправить SBOM» и аналогичный смысл.

- [ ] **Step 4: Запустить тест**

Run: `npm test --prefix frontend -- HomePage.test.ts`
Expected: PASS.

---

### Task 12: Страница `SbomFixer.vue` — опции, сохранение, запуск, статус

**Files:**
- Create: `frontend/src/views/SbomFixer.vue`
- Create: `frontend/src/views/SbomFixer.test.ts`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/ru.json`

**Interfaces:**
- Consumes: `fixSbom`, `getFixOptions`, `saveFixOptions`, `useSettingsStore`, `FileUploadZone`, `downloadJson`.
- Produces DOM-контракт для тестов:
  - `.warning-banner`, `.options-warning`, `.options-panel`, `.save-settings`, `.save-status`, `.reset-defaults`, `.spec-version-input`, `.fix-button`, `.loading`, `.error-msg`, `.status-card.status-changed`, `.status-card.status-unchanged`;
  - карточки `.group-card[data-group="root|metadata|components"]`, подблок `[data-group="metadata-component"]`;
  - мастер-чекбокс `.master-checkbox`, чекбокс правила `[data-rule="<rule_id>"]`, кнопки `.select-all`, `.clear-all`.
- State: `reactive<SbomFixOptions>`; `selectedFile`, `loading`, `error`, `result`, `optionsWarning`, `saveStatus: 'idle'|'saving'|'saved'|'error'`.
- Helpers: `defaultFixOptions(): SbomFixOptions`; `applyOptions(next: SbomFixOptions): void`; `plainOptions(): SbomFixOptions` (JSON round-trip).

- [ ] **Step 1: Написать падающие тесты**

Mock `../api/sbom`, `../api/settings`, `../composables/useDownload`. В `beforeEach`: `setActivePinia(createPinia())`, `getFixOptions` → дефолты, `getSettings` → полный `SettingsResponse` с `json_indent: 2`, `fixSbom` → успешный ответ, `saveFixOptions` → `{ status: 'saved' }`.

Проверить:
- рендерится `.warning-banner` о том, что почти все правки включены по умолчанию;
- на монтировании вызывается `getFixOptions`, форма заполняется значениями; `getSettings` вызывается;
- если `getFixOptions` отклонён — `.options-warning` есть, форма содержит дефолты, страница работает;
- мастер `root`/`metadata`/`components` включает/выключает всех детей; мастер `metadata` включает и `metadata.component.*`; мастер `metadata-component` не меняет `metadata.reorder`/`remove_*`/`add_timestamp`;
- промежуточное состояние мастера выражено `indeterminate`;
- `.select-all`/`.clear-all` работают в своей группе; `.reset-defaults` восстанавливает дефолты (`remove_purl === false`, `fill_missing_gost_properties === false`, остальные `true`, `spec_version === "1.7"`) и не вызывает `saveFixOptions`;
- `.save-settings` вызывает `saveFixOptions(plainOptions())` и показывает `Saved`; при ошибке — статус ошибки;
- `.spec-version-input` disabled при выключенном `root.set_spec_version`;
- `.fix-button` disabled без файла; после выбора файла активен;
- во время запроса отображается `.loading`; успешный `fixSbom` получает файл и текущие опции; рендерится `.status-changed` при `changed=true` и `.status-unchanged` при `false`;
- ошибки запуска (`invalid_options`, `invalid_sbom`) и сетевая ошибка показываются в `.error-msg`;
- ошибка сохранения (`options_save_failed` или сетевая) показывается в `.save-status` с ошибочным состоянием, а не в `.error-msg`;
- новый выбор файла сбрасывает результат и ошибку, но не опции.

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `npm test --prefix frontend -- SbomFixer.test.ts`
Expected: FAIL — компонент отсутствует.

- [ ] **Step 3: Реализовать страницу**

Страница содержит заголовок/подзаголовок, `.warning-banner` и `<FileUploadZone accept=".json" :max-size="200" />`.

`onMounted`: `Promise.allSettled([getFixOptions(), settingsStore.load()])`; при отклонении `getFixOptions` — `optionsWarning = true`, остаются дефолты; при отклонении `load()` страница не блокируется (`jsonIndent` остаётся 4).

Мастер-чекбоксы: computed get/set по булевым полям; для `metadata` включать и вложенные `component.*`; для `metadata-component` — только его поля. `specVersion` показывать всегда, disabled без `set_spec_version`.

`handleFix`: `fixSbom(selectedFile, plainOptions())`; `result = res`; `error = null`; ошибки как в `ImagesListConverter.vue` (`ApiError` → `t('errors.' + e.error, e.data)`, `Error` → `errors.network_error`, иначе `errors.unexpected_error`).

Добавить в i18n: `sbomFixer.title`, `subtitle`, `warning`, `saveSettings`, `saved`, `saveFailed`, `loadFailed`, `resetDefaults`, `fix`, `processing`, `groups.{root,metadata,components,metadataComponent}`, `selectAll`, `clearAll`, `specVersion`, `changed`, `unchanged`, `rules.<rule_id>` для всех 21 правила, `errors.invalid_options`, `errors.options_save_failed`. Английские значения, на которые опираются тесты: `Fix SBOM`, `Save settings`, `Saved`, `Restore defaults`, `Fix`, `Changes applied`, `No changes needed`.

- [ ] **Step 4: Запустить тесты**

Run: `npm test --prefix frontend -- SbomFixer.test.ts`
Expected: PASS для тестов этой задачи.

---

### Task 13: Страница `SbomFixer.vue` — статистика, issues, скачивание

**Files:**
- Modify: `frontend/src/views/SbomFixer.vue`
- Modify: `frontend/src/views/SbomFixer.test.ts`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/ru.json`

**Interfaces:**
- Adds DOM: `.stats-spoiler`, `.stats-table`, `.issues-spoiler`, `.issues-table`, `.no-issues-card`, `.download-button`.
- `statsOpen = ref(true)`, `issuesOpen = ref(false)`; спойлеры — `<details>` с `@toggle`; таблица issues обёрнута в `v-if="issuesOpen"`.
- Скачивание: `downloadJson(result.fixed_sbom, selectedFile.name.replace(/\.json$/, '') + '_fixed.json', settingsStore.jsonIndent)`.

- [ ] **Step 1: Написать падающие тесты**

Проверить:
- статистика рендерится в `.stats-spoiler`, открытом по умолчанию; строки соответствуют `result.stats`, включая нулевые; подпись правила через `t('sbomFixer.rules.' + rule_id)`;
- при непустых issues есть `.issues-spoiler`, закрытый по умолчанию; подпись содержит количество (`Show non-conformities (N)`); `.issues-table` отсутствует в DOM до раскрытия; после установки `element.open = true` и `trigger('toggle')` таблица появляется; строки содержат code/path/component/details; `details.missing` форматируется через запятую;
- пустой `issues` — `.no-issues-card`, `.issues-spoiler` отсутствует;
- `.download-button` вызывает `downloadJson` с `fixed_sbom`, именем `sbom_fixed.json` и `jsonIndent` из store;
- если `getSettings` отклонён, скачивание использует `jsonIndent = 4`;
- спойлер статистики можно свернуть и снова открыть.

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `npm test --prefix frontend -- SbomFixer.test.ts`
Expected: FAIL — нет спойлеров/кнопки скачивания.

- [ ] **Step 3: Реализовать результаты**

Таблица статистики: колонки «Правило»/«Изменений», значения через i18n. Issues: колонки code/path/component/details; details `missing` → `join(', ')`, прочее → `JSON.stringify`; длинные значения обрезать CSS с `title`. `issuesOpen` сбрасывать в `false` при новом результате; `statsOpen` — в `true`.

Добавить i18n-ключи: `statistics`, `rule`, `changes`, `noIssues`, `issuesToggle` (англ. `Show non-conformities ({count})`), `issuesCode`, `issuesPath`, `issuesComponent`, `issuesDetails`, `download` (англ. `Download fixed SBOM`), `issues.<code>` для всех 25 кодов §8.

- [ ] **Step 4: Запустить тесты**

Run: `npm test --prefix frontend -- SbomFixer.test.ts`
Expected: PASS.

---

### Task 14: Обновление project specs

**Files:**
- Create: `specs/domains/sbom-fixing.md`
- Modify: `specs/META.md`
- Modify: `specs/INDEX.md`
- Modify: `specs/domains/web-ui.md`
- Modify: `specs/contracts/api-contract.md`
- Modify: `specs/architecture/layers.md`

**Interfaces:**
- `specs/domains/sbom-fixing.md` — назначение, ключевые файлы, модели, порядок правил, дефолты, хранение опций, статистика, коды issues, API-поведение, инварианты, конфигурация.

- [ ] **Step 1: Создать доменную спеку**

Зафиксировать: 21 правило и их дефолты; `spec_version = "1.7"`; `SbomFixOptionsStore` и файл `./data/sbom_fix_options.json`; issues только по итоговому документу; `changed`; правила сохранения `group` и `externalReferences[].hashes`; отсутствие БД и очереди.

- [ ] **Step 2: Обновить `META.md`**

Добавить `domains/sbom-fixing.md` в File Organization.

- [ ] **Step 3: Обновить `INDEX.md`**

Добавить task-to-spec строку «Fix SBOM normalization defects» → `domains/sbom-fixing.md`, `contracts/api-contract.md`, `domains/web-ui.md`, `architecture/layers.md`; добавить файл в Directory Listing; обновить описание web-ui как шести tool-страниц.

- [ ] **Step 4: Обновить `web-ui.md`**

`five` → `six` tool pages; key files: `SbomFixer.vue`, `SbomFixer.test.ts`, функции fix в `api/sbom.ts`, типы; маршрут `/fix-sbom` и 7 page routes + catch-all; навигация и 6 плиток; flow «Fix SBOM»; инварианты страницы (загрузка/сохранение опций, мастер-чекбоксы, спойлеры, скачивание с `jsonIndent`, ошибки); тесты.

- [ ] **Step 5: Обновить `api-contract.md`**

Добавить SPA-маршрут `/fix-sbom`; `POST /api/v1/sbom/fix` с request/response/ошибками; `GET/POST /api/v1/sbom/fix/options`; строки ошибок `invalid_options`, `options_save_failed`; обновить список SPA-маршрутов.

- [ ] **Step 6: Обновить `layers.md`**

Добавить `sbom/fixer.py` и `sbom_fix_options_store.py` в SBOM/Store-блоки; `routes/sbom_fix.py` в API Layer; import rules (API Layer использует store через `app.state`, `fixer.py` не импортирует Storage/Resolver/API-схемы); responsibilities; Web UI views/routes/stores.

- [ ] **Step 7: Проверить cross-references**

Run: `grep -rn "sbom-fixing\|fix-sbom\|sbom/fixer\|sbom_fix_options_store" specs`
Expected: все новые ссылки присутствуют; пути к файлам существуют.

---

### Task 15: Финальная проверка

**Files:**
- Все изменённые файлы.

- [ ] **Step 1: Backend-тесты**

Run: `.venv/bin/python -m pytest`
Expected: все тесты PASS.

- [ ] **Step 2: Ruff**

Run: `.venv/bin/ruff check src tests`
Expected: без ошибок.

- [ ] **Step 3: Frontend-тесты**

Run: `npm test --prefix frontend`
Expected: все тесты PASS.

- [ ] **Step 4: Frontend-сборка**

Run: `npm run build --prefix frontend`
Expected: `vue-tsc` и Vite build PASS.

- [ ] **Step 5: Финальная сверка с дизайном**

Проверить по чек-листу:
- 21 правило и канонический порядок stats;
- дефолты: всё `True`, кроме двух;
- финальный reorder и отсутствие мутаций входа;
- `group` и `externalReferences[].hashes` не тронуты;
- API-коды ошибок и `JSONResponse` с верхнеуровневым `error`;
- store: дефолты при отсутствии/повреждении/частичном файле;
- UI: предупреждение, мастер-чекбоксы, сохранение/сброс, спойлеры, скачивание, i18n en/ru;
- specs обновлены.

- [ ] **Step 6: Чекпойнт**

Сообщить результат проверки и перечислить изменённые файлы.
