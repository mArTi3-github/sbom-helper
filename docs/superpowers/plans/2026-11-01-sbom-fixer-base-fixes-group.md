# «Базовые правки» и полное отображение несоответствий — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Объединить четыре правила упорядочивания в одно, привести модель опций и интерфейс к трём подразделам («Базовые правки», «Правки массива components[]», «Удаление необязательных полей по „белому списку“») и показывать таблицу несоответствий без обрезания строк.

**Architecture:** Плоские «базовые» поля в `SbomFixOptions`, одно правило `reorder` с единой строкой статистики; вложенными остаются только `components` и `optional_fields`. Frontend повторяет эту форму: один каталог `BASE_RULES`, карточка «Базовые правки» с мастер-чекбоксом, карточка компонентов без `reorder` и неизменная карточка белого списка.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest; Vue 3 `<script setup>`, TypeScript, vue-i18n, Vitest, vue-tsc.

**Spec:** `docs/superpowers/specs/2026-11-01-sbom-fixer-base-fixes-group-design.md`

## Global Constraints

- Обратная совместимость не нужна: старые rule id, вложенные `root`/`metadata`/`metadata.component` и старый файл настроек не поддерживаются, миграции нет.
- `RULE_IDS` — ровно 8 правил в порядке: `reorder`, `set_spec_version`, `increment_version`, `add_timestamp`, `add_manufacturer`, `components.filter_external_references`, `components.filter_properties`, `components.fill_missing_gost_properties`.
- Правило `reorder` остаётся последней мутацией документа; входной документ не мутируется (`copy.deepcopy`).
- `reorder` считается как число объектов с изменённым порядком ключей: корень + `metadata` + `metadata.component` + каждый компонент дерева `components[]`, по 1 за объект.
- Названия базовых пунктов фиксированы дизайном (раздел 5.1): путь в названии обязателен, кроме объединённого `reorder` («Упорядочить поля», полный перечень объектов — в справке); у компонентных правил путь не дублируется.
- Все пользовательские строки — через i18n (`ru.json`, `en.json`); других языков нет.
- Python запускается только через `.venv`; frontend-команды — через `npm --prefix frontend`.
- Раздел должен по-прежнему работать с файлами 100+ МБ: никаких повторных обходов документа или лишних копий сверх существующих.

## Review Focus

- Старый `data/sbom_fix_options.json` с ключами `root`/`metadata`/`metadata.component`: страница обязана открыться на встроенных значениях без ошибки — тесты `test_load_ignores_legacy_nested_options` (Task 1) и `GET /options` с legacy-файлом (Task 1).
- Частичный payload опций (например, только `{"optional_fields": ...}` или только `{"spec_version": ...}`): недостающие плоские поля обязаны взять defaults, а не упасть — `test_save_and_load_options_trim...` и roundtrip (Task 1).
- Выключенный `reorder`: порядок ключей всех четырёх объектов не меняется, строки `reorder` нет в статистике — `test_reorder_disabled_changes_nothing_and_is_absent_from_stats` (Task 1).
- Смешанный случай: изменился только компонент, а корень и metadata уже каноничны — счётчик равен числу изменившихся объектов, а не 4 — `test_merged_reorder_counts_only_changed_objects` (Task 1).
- Очень длинные неразрывные значения в таблице несоответствий (длинный `component`, длинный `path`, длинный JSON в `details`): текст виден целиком, `title` больше не используется — тест на полный текст и отсутствие `title` (Task 3); CSS-перенос проверяется ревью, jsdom его не вычисляет.

---

### Task 1: Backend — плоские опции, единое правило `reorder`, статистика

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py:58-176`, `src/purl_resolver/sbom/fixer.py:210-275`, `src/purl_resolver/sbom/fixer.py:592-654`
- Test: `tests/test_sbom_fixer.py`
- Test: `tests/test_sbom_fix_options_store.py`
- Test: `tests/test_sbom_fix_api.py`

**Interfaces:**
- Consumes: `DEFAULT_KEEP_FIELDS`, `normalize_keep`, `remove_optional_fields` из `optional_fields.py` (не меняются).
- Produces:
  - `SbomFixOptions(reorder: bool = True, set_spec_version: bool = True, spec_version: str = "1.7", increment_version: bool = True, add_timestamp: bool = True, add_manufacturer: bool = True, manufacturer: str = "Positive Technologies", components: ComponentsFixOptions, optional_fields: OptionalFieldsFixOptions)`
  - `ComponentsFixOptions(filter_external_references: bool = True, filter_properties: bool = True, fill_missing_gost_properties: bool = False)`
  - `RULE_IDS` из 8 элементов (см. Global Constraints)
  - `fix_sbom(data, options, now=None, remove_fields=())` — сигнатура без изменений; в `stats` одна строка `reorder`

- [ ] **Step 1: Переписать контрактные ожидания в `tests/test_sbom_fixer.py`**

Заменить `NEW_RULE_IDS` на:

```python
NEW_RULE_IDS = (
    "reorder",
    "set_spec_version",
    "increment_version",
    "add_timestamp",
    "add_manufacturer",
    "components.filter_external_references",
    "components.filter_properties",
    "components.fill_missing_gost_properties",
)
```

Заменить `test_defaults_expose_new_options_and_keep_list` на `test_defaults_expose_flat_base_options`:

```python
def test_defaults_expose_flat_base_options():
    o = SbomFixOptions()
    assert o.reorder is True
    assert o.set_spec_version is True
    assert o.spec_version == "1.7"
    assert o.increment_version is True
    assert o.add_timestamp is True
    assert o.add_manufacturer is True
    assert o.manufacturer == "Positive Technologies"
    assert o.components.fill_missing_gost_properties is False
    assert o.optional_fields.keep == list(DEFAULT_KEEP_FIELDS)
    for removed in ("root", "metadata"):
        assert not hasattr(o, removed)
    for removed in ("reorder", "remove_dependencies", "remove_services"):
        assert not hasattr(o.components, removed)
```

Переименовать `test_all_enabled_rules_yield_eleven_stats_in_canonical_order` в `test_all_enabled_rules_yield_eight_stats_in_canonical_order` и оставить тело (оно сверяется с `NEW_RULE_IDS`). В `test_fix_sbom_copies_input_and_emits_zero_stats_for_enabled_rules` заменить `len(result.stats) == 10` на `len(result.stats) == 7`.

Перевести все конструкторы опций на плоскую форму:

| Было | Стало |
|---|---|
| `SbomFixOptions(root={"spec_version": value})` | `SbomFixOptions(spec_version=value)` |
| `SbomFixOptions(root={"spec_version": " 1.7 "})` | `SbomFixOptions(spec_version=" 1.7 ")` |
| `SbomFixOptions(metadata={"component": {"manufacturer": value}})` | `SbomFixOptions(manufacturer=value)` |
| `SbomFixOptions(metadata={"component": {"add_manufacturer": False}})` | `SbomFixOptions(add_manufacturer=False)` |
| `SbomFixOptions(metadata={"add_timestamp": False})` | `SbomFixOptions(add_timestamp=False)` |
| `SbomFixOptions(root={"reorder": False})` | `SbomFixOptions(reorder=False)` |
| `SbomFixOptions(root={"set_spec_version": False})` | `SbomFixOptions(set_spec_version=False)` |
| `SbomFixOptions(root={"set_spec_version": False, "increment_version": False})` | `SbomFixOptions(set_spec_version=False, increment_version=False)` |
| `SbomFixOptions(root={"spec_version": "1.6"})` | `SbomFixOptions(spec_version="1.6")` |
| `SbomFixOptions(metadata={"reorder": False, "component": {"reorder": False}})` | `SbomFixOptions(reorder=False)` |
| `SbomFixOptions(components={"reorder": False})` | `SbomFixOptions(reorder=False)` |

Заменить ключи статистики: `root.set_spec_version` → `set_spec_version`, `root.increment_version` → `increment_version`, `metadata.add_timestamp` → `add_timestamp`, `metadata_component.add_manufacturer` → `add_manufacturer`. В тестах упорядочивания заменить все четыре ключа `*.reorder` на `stats["reorder"]` со следующим ожидаемым числом:

| Тест | Ожидаемый `count` | Почему |
|---|---|---|
| `test_root_reorder_puts_schema_last` | 1 | меняется только корень |
| `test_metadata_reorder_puts_timestamp_and_component_first` | 1 | меняется только `metadata` |
| `test_metadata_component_reorder_puts_canonical_fields_first` | 1 | меняется только `metadata.component` |
| `test_components_reorder_is_recursive_and_counts_each_changed_component` | 2 | меняются первый компонент и вложенный `d` |
| `test_components_reorder_does_not_enter_metadata_component_components` | 0 | все объекты уже каноничны, вложенный не обходится |

В тестах выключения (`test_disabled_reorder_changes_nothing_and_is_absent_from_stats`, `test_disabled_root_rules_leave_fields_untouched_and_are_absent_from_stats`, `test_disabled_metadata_rules_leave_fields_untouched_and_are_absent_from_stats`, `test_disabled_components_rules_leave_fields_untouched`) заменить набор вложенных флагов на плоский (`SbomFixOptions(reorder=False, set_spec_version=False, ...)`) и проверять `"reorder" not in rule_ids`.

Добавить новый тест:

```python
def test_merged_reorder_counts_only_changed_objects():
    data = {
        "components": [{"version": "1", "name": "a", "type": "library"}],
        "metadata": {
            "component": {"name": "root", "type": "application"},
            "timestamp": "2020-01-01T00:00:00Z",
        },
        "specVersion": "1.7",
        "bomFormat": "CycloneDX",
    }
    options = SbomFixOptions(
        reorder=True,
        set_spec_version=False,
        increment_version=False,
        add_timestamp=False,
        add_manufacturer=False,
    )
    result = fix_sbom(data, options)
    assert list(result.fixed_sbom) == ["bomFormat", "specVersion", "metadata", "components"]
    assert list(result.fixed_sbom["metadata"]) == ["timestamp", "component"]
    assert list(result.fixed_sbom["metadata"]["component"]) == ["type", "name"]
    assert list(result.fixed_sbom["components"][0]) == ["type", "name", "version"]
    assert _stats(result)["reorder"] == 4
```

- [ ] **Step 2: Прогнать backend-тесты и убедиться, что они падают**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -q`
Expected: FAIL — `TypeError: SbomFixOptions.__init__() got an unexpected keyword argument 'root'` и/или `AttributeError` на плоских полях.

- [ ] **Step 3: Переписать `tests/test_sbom_fix_options_store.py`**

- Удалить импорт `RootFixOptions`, оставить `SbomFixOptions`.
- `test_save_load_roundtrip_including_spec_version`: `SbomFixOptions(spec_version="1.6")`.
- `test_corrupt_non_utf8_file_returns_defaults`: записывать `b'{"reorder": false}\xff'`.
- `test_invalid_spec_version_returns_defaults`: файл `'{"spec_version": "9.9.9"}'`.
- `test_partial_json_fills_defaults`: файл `'{"reorder": false}'`; проверять `loaded.reorder is False`, `loaded.set_spec_version is True`, `loaded.add_timestamp is True`.
- `test_save_writes_indented_utf8_json_with_trailing_newline`: `options = SbomFixOptions.model_construct(spec_version="1.7-тест")`; проверять `'\n  "spec_version": "1.7-тест"' in text`.
- `test_load_ignores_legacy_remove_keys` переименовать в `test_load_ignores_legacy_nested_options`; файл содержит `{"root": {"reorder": false, "remove_dependencies": true}, "metadata": {"component": {"rename_supplier": true}}, "components": {"remove_hashes": true}}`; после загрузки `options == SbomFixOptions()`, `not hasattr(options, "root")`, `options.optional_fields.keep == list(DEFAULT_KEEP_FIELDS)`.

- [ ] **Step 4: Переписать опции в `tests/test_sbom_fix_api.py`**

- `options = {"metadata": {"component": {"manufacturer": "Acme"}}}` → `options = {"manufacturer": "Acme"}`; `stats` проверяет `add_manufacturer`; `len(data["stats"]) == 10` → `7`.
- `test_missing_options_uses_defaults`: `len(data["stats"]) == 10` → `7`.
- `json.dumps({"root": {"spec_version": "9.9.9"}})` → `json.dumps({"spec_version": "9.9.9"})`.
- corrupt bytes: `b'{"reorder": false}\xff'`.
- сохранение с обрезкой: `json={"options": {"spec_version": " 1.7 "}}`; проверка `response.json()["options"]["spec_version"] == "1.7"`.
- roundtrip: `SbomFixOptions(manufacturer="Acme")`.

- [ ] **Step 5: Прогнать все backend-тесты и убедиться, что они падают**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py tests/test_sbom_fix_options_store.py tests/test_sbom_fix_api.py -q`
Expected: FAIL — старые модели и rule id.

- [ ] **Step 6: Переписать модели и `RULE_IDS` в `src/purl_resolver/sbom/fixer.py`**

```python
class ComponentsFixOptions(BaseModel):
    filter_external_references: bool = True
    filter_properties: bool = True
    fill_missing_gost_properties: bool = False


class OptionalFieldsFixOptions(BaseModel):
    keep: list[str] = Field(default_factory=lambda: list(DEFAULT_KEEP_FIELDS))

    @field_validator("keep", mode="before")
    @classmethod
    def _validate_keep(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("keep must be a list of field paths")
        return normalize_keep(value)


class SbomFixOptions(BaseModel):
    reorder: bool = True
    set_spec_version: bool = True
    spec_version: str = "1.7"
    increment_version: bool = True
    add_timestamp: bool = True
    add_manufacturer: bool = True
    manufacturer: str = "Positive Technologies"
    components: ComponentsFixOptions = Field(default_factory=ComponentsFixOptions)
    optional_fields: OptionalFieldsFixOptions = Field(default_factory=OptionalFieldsFixOptions)

    @field_validator("spec_version", mode="before")
    @classmethod
    def _validate_spec_version(cls, value: object) -> str:
        if isinstance(value, str):
            value = value.strip()
        if not isinstance(value, str) or not SPEC_VERSION_PATTERN.fullmatch(value):
            raise ValueError("spec_version must match ^\\d+\\.\\d+$")
        return value

    @field_validator("manufacturer", mode="before")
    @classmethod
    def _validate_manufacturer(cls, value: object) -> str:
        if isinstance(value, str):
            value = value.strip()
        if not isinstance(value, str) or not value:
            raise ValueError("manufacturer must be a non-empty string")
        return value
```

`RULE_IDS` заменить на кортеж из Global Constraints. `_rule_enabled` заменить на:

```python
def _rule_enabled(rule_id: str, options: SbomFixOptions) -> bool:
    if rule_id.startswith("components."):
        return getattr(options.components, rule_id.removeprefix("components."))
    return getattr(options, rule_id)
```

- [ ] **Step 7: Перевести примененение правил на плоские поля и объединить `reorder`**

- `_apply_root_rules`: `_rule_enabled("set_spec_version", options)`, `options.spec_version`, `_rule_enabled("increment_version", options)`.
- `_apply_metadata_rules`: `_rule_enabled("add_timestamp", ...)`, `_rule_enabled("add_manufacturer", ...)`, `options.manufacturer`.
- `_apply_components_rules`: без изменений, кроме отсутствия `components.reorder` в проверках.
- Заменить `_apply_reorders` на `_apply_reorder(data, options, counts) -> None`:

```python
def _apply_reorder(data: dict, options: SbomFixOptions, counts: dict[str, int]) -> None:
    if not options.reorder:
        return
    count = int(_reorder_in_place(data, ROOT_PRIORITY))
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        count += int(_reorder_in_place(metadata, METADATA_PRIORITY))
        metadata_component = metadata.get("component")
        if isinstance(metadata_component, dict):
            count += int(
                _reorder_in_place(metadata_component, METADATA_COMPONENT_PRIORITY)
            )
    components = data.get("components")
    if isinstance(components, list):
        count += sum(
            _reorder_component_tree(component)
            for component in components
            if isinstance(component, dict)
        )
    counts["reorder"] = count
```

- В `fix_sbom()` вызвать `_apply_reorder(fixed_sbom, options, counts)` и оставить `stats`/`changed` как есть.
- Удалить `RootFixOptions`, `MetadataFixOptions`, `MetadataComponentFixOptions`; проверить, что они не импортируются нигде, кроме тестов (grep по `RootFixOptions`).

- [ ] **Step 8: Прогнать backend-тесты**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py tests/test_sbom_fix_options_store.py tests/test_sbom_fix_api.py -q`
Expected: PASS.

- [ ] **Step 9: Коммит**

```bash
git add src/purl_resolver/sbom/fixer.py tests/test_sbom_fixer.py tests/test_sbom_fix_options_store.py tests/test_sbom_fix_api.py
git commit -m "refactor: flatten sbom fix options and merge reorder rules"
```

---

### Task 2: Frontend — типы, каталог правил, три подраздела, i18n

**Files:**
- Modify: `frontend/src/types/api.ts:195-230`
- Modify: `frontend/src/views/sbomFixerRules.ts` (полная замена)
- Modify: `frontend/src/views/SbomFixer.vue:24-214`, `frontend/src/views/SbomFixer.vue:394-531`
- Modify: `frontend/src/i18n/locales/ru.json`, `frontend/src/i18n/locales/en.json` (ветка `sbomFixer`)
- Test: `frontend/src/views/sbomFixerRules.test.ts`
- Test: `frontend/src/views/SbomFixer.test.ts`

**Interfaces:**
- Consumes: `SbomFixOptions` из Task 1 (плоские поля) через JSON API; `RuleHelp` (без изменений).
- Produces: `BASE_RULES: readonly FixRule<BaseRuleKey>[]` (5 записей), `COMPONENTS_RULES: readonly FixRule<ComponentsRuleKey>[]` (3 записи), `ALL_FIX_RULES` (8); элементы DOM `data-group="basic"` и `data-group="components"`.

- [ ] **Step 1: Обновить `frontend/src/types/api.ts`**

Удалить `RootFixOptions`, `MetadataFixOptions`, `MetadataComponentFixOptions`; оставить:

```ts
export interface ComponentsFixOptions {
  filter_external_references: boolean
  filter_properties: boolean
  fill_missing_gost_properties: boolean
}

export interface OptionalFieldsFixOptions {
  keep: string[]
}

export interface SbomFixOptions {
  reorder: boolean
  set_spec_version: boolean
  spec_version: string
  increment_version: boolean
  add_timestamp: boolean
  add_manufacturer: boolean
  manufacturer: string
  components: ComponentsFixOptions
  optional_fields: OptionalFieldsFixOptions
}
```

- [ ] **Step 2: Обновить `frontend/src/views/sbomFixerRules.test.ts` и прогнать — тесты падают**

```ts
import { ALL_FIX_RULES, BASE_RULES, COMPONENTS_RULES } from './sbomFixerRules'

const GROUPS = [
  { rules: BASE_RULES, prefix: '', size: 5 },
  { rules: COMPONENTS_RULES, prefix: 'components.', size: 3 },
]
```

- `covers all 11 rules` → `covers all 8 rules`: `toHaveLength(8)`, `Set(...).size === 8`.
- Проверку `replaces rename_supplier...` заменить на `expect(ids).toContain('add_manufacturer')` + список запрещённых id (без `metadata_component.rename_supplier`).
- Заменить `keeps each group complete and starts it with the reorder rule` на `starts the base group with the merged reorder rule`: `expect(BASE_RULES[0].id).toBe('reorder')`; для `COMPONENTS_RULES` проверить префикс `components.` и размер 3.
- Остальные проверки (примеры, локали, отсутствие `sbomFixer.warning`) оставить.

Run: `npm --prefix frontend run test -- src/views/sbomFixerRules.test.ts`
Expected: FAIL — `BASE_RULES` не экспортируется.

- [ ] **Step 3: Переписать `frontend/src/views/sbomFixerRules.ts`**

Типы:

```ts
import type { ComponentsFixOptions } from '../types/api'

export interface FixRuleExample {
  readonly before: string
  readonly after: string
}

export interface FixRule<K extends string> {
  readonly id: string
  readonly key: K
  readonly example: FixRuleExample
}

export type BaseRuleKey =
  | 'reorder'
  | 'set_spec_version'
  | 'increment_version'
  | 'add_timestamp'
  | 'add_manufacturer'
export type ComponentsRuleKey = keyof ComponentsFixOptions
```

`BASE_RULES` в порядке: `reorder`, `set_spec_version`, `increment_version`, `add_timestamp`, `add_manufacturer`; `id` каждого равен `key`. Примеры `set_spec_version`, `increment_version`, `add_timestamp`, `add_manufacturer` перенести из прежних `ROOT_RULES`/`METADATA_RULES`/`METADATA_COMPONENT_RULES` без изменения JSON. Новый пример для `reorder`:

```ts
{
  id: 'reorder',
  key: 'reorder',
  example: {
    before: `{
  "components": [
    { "purl": "pkg:npm/left-pad@1.3.0", "name": "left-pad", "type": "library" }
  ],
  "metadata": {
    "component": { "name": "app", "type": "application" },
    "timestamp": "2026-10-29T12:00:00Z"
  },
  "bomFormat": "CycloneDX"
}`,
    after: `{
  "bomFormat": "CycloneDX",
  "metadata": {
    "timestamp": "2026-10-29T12:00:00Z",
    "component": { "type": "application", "name": "app" }
  },
  "components": [
    { "type": "library", "name": "left-pad", "purl": "pkg:npm/left-pad@1.3.0" }
  ]
}`,
  },
}
```

`COMPONENTS_RULES` — три прежних правила без `components.reorder`. `ALL_FIX_RULES = [...BASE_RULES, ...COMPONENTS_RULES]`.

- [ ] **Step 4: Обновить фикстуры и ожидания в `frontend/src/views/SbomFixer.test.ts` и прогнать — тесты падают**

`defaultOptions` заменить на:

```ts
const defaultOptions: SbomFixOptions = {
  reorder: true,
  set_spec_version: true,
  spec_version: '1.7',
  increment_version: true,
  add_timestamp: true,
  add_manufacturer: true,
  manufacturer: 'Positive Technologies',
  components: {
    filter_external_references: true,
    filter_properties: true,
    fill_missing_gost_properties: false,
  },
  optional_fields: { keep: [/* 10 путей из текущей фикстуры */] },
}
```

Замены по всему файлу:

| Было | Стало |
|---|---|
| `saved.root.reorder` / `rule('root.reorder')` | `saved.reorder` / `rule('reorder')` |
| `rule('root.set_spec_version')` | `rule('set_spec_version')` |
| `rule('root.increment_version')` | `rule('increment_version')` |
| `rule('metadata.add_timestamp')` | `rule('add_timestamp')` |
| `rule('metadata.reorder')` | `rule('reorder')` |
| `rule('metadata_component.add_manufacturer')` | `rule('add_manufacturer')` |
| `rule('metadata_component.reorder')` | `rule('reorder')` |
| `rule('components.reorder')` | `rule('reorder')` |
| `masterFor(wrapper, 'root')` | `masterFor(wrapper, 'basic')` |
| `[data-help-for="root.reorder"]` | `[data-help-for="reorder"]` |
| `[data-help-for="root.increment_version"]` | `[data-help-for="increment_version"]` |
| `[data-rule-row="root.reorder"]` | `[data-rule-row="reorder"]` |
| `[data-rule-row="root.increment_version"]` | `[data-rule-row="increment_version"]` |
| `.group-card[data-group="root"]` | `.group-card[data-group="basic"]` |

- `renders help for every rule...`: `toHaveLength(8)`.
- `test 'root master toggles every root option'` → `basic master toggles every base option`; список id: `['reorder','set_spec_version','increment_version','add_timestamp','add_manufacturer']`.
- Удалить тесты `metadata master also toggles metadata.component options` и `metadata-component master does not change metadata options`.
- `marks partially selected masters as indeterminate`: `basic` — false/не indeterminate; `components` — indeterminate true; после `rule('add_manufacturer').setValue(false)` — `basic` indeterminate true и checked false.
- `select all and clear all operate within their own group`: очистка `data-group="basic"` выключает `reorder` и не трогает `components.filter_properties`; очистка `data-group="components"` выключает три компонентных правила и не трогает `reorder`; затем «Выбрать всё» в каждой группе возвращает флаги.
- `loads options and settings on mount...`: options `{ ...cloneOptions(), spec_version: '1.6', increment_version: false }`; проверки по `rule('increment_version')` и `rule('reorder')`.
- `statsResponse` / `issuesResponse`: `rule_id: 'root.reorder'` → `'reorder'`.
- В `renders change statistics...`: `rows[0].text()` содержит `'Reorder fields'` (новый en-label), `rows[1]` — `'Keep only GOST properties'`.
- Остальные тесты (сохранение, сброс, ошибки, анализ, скачивание) — только переименование id по таблице.

Run: `npm --prefix frontend run test -- src/views/SbomFixer.test.ts src/views/sbomFixerRules.test.ts`
Expected: FAIL — карточки/каталог ещё старые.

- [ ] **Step 5: Переписать разметку карточек в `frontend/src/views/SbomFixer.vue`**

Удалить три карточки (`root`, `metadata` с подблоком `metadata-component`, `components.reorder`) и поставить две:

1. Карточка `data-group="basic"` с заголовком `t('sbomFixer.groups.basic')`, мастер-чекбоксом `basicMaster`, `:indeterminate.prop="basicIndeterminate"` и кнопками, которые ставят `basicMaster`; строки — `v-for="rule in BASE_RULES"` с `:data-rule-row="rule.id"`, чекбокс `v-model="options[rule.key]"`, `:data-rule="rule.id"`; условные контролы:
   - `rule.id === 'set_spec_version'`: `v-model="options.spec_version"`, `:disabled="!options.set_spec_version"`;
   - `rule.id === 'add_manufacturer'`: `v-model="options.manufacturer"`, `:disabled="!options.add_manufacturer"`.
2. Карточка `data-group="components"` с заголовком `t('sbomFixer.groups.components')`, мастер-чекбоксом `componentsMaster`, `v-for="rule in COMPONENTS_RULES"`, `v-model="options.components[rule.key]"`.

Блок `RuleHelp` в обеих карточках остаётся прежним. Карточка `optional-fields` не меняется. Удалить `data-group="metadata-component"` и `data-group="root"`.

- [ ] **Step 6: Обновить скрипт `SbomFixer.vue`**

- Импорт: `BASE_RULES, COMPONENTS_RULES` вместо четырёх массивов.
- `defaultFixOptions()` — плоский объект из Step 4.
- `applyOptions(next)`: присвоить каждое плоское поле (`options.reorder = next.reorder` … `options.manufacturer = next.manufacturer`) и слить `components`/`optional_fields` как сейчас.
- `rootValues`, `metadataValues`, `metadataComponentValues` заменить на `baseValues = () => BASE_RULES.map((rule) => options[rule.key])`; `basicMaster`/`basicIndeterminate` — по образцу прежних мастеров; `componentsMaster`/`componentsIndeterminate` оставить.
- Удалить `rootMaster`, `rootIndeterminate`, `metadataMaster`, `metadataIndeterminate`, `metadataComponentMaster`, `metadataComponentIndeterminate`.

- [ ] **Step 7: Обновить локали `ru.json` и `en.json`**

`sbomFixer.groups`:

```json
"groups": {
  "basic": "Базовые правки",
  "components": "Правки массива components[]"
}
```

```json
"groups": {
  "basic": "Basic fixes",
  "components": "components[] edits"
}
```

`sbomFixer.rules` (ru):

```json
"rules": {
  "reorder": "Упорядочить поля",
  "set_spec_version": "Установить $.specVersion",
  "increment_version": "Увеличить $.version",
  "add_timestamp": "Добавить $.metadata.timestamp, если отсутствует",
  "add_manufacturer": "Добавить $.metadata.component.manufacturer, если отсутствует",
  "components": {
    "filter_external_references": "Оставить только VCS и source-distribution ссылки",
    "filter_properties": "Оставить только GOST-свойства",
    "fill_missing_gost_properties": "Добавить недостающие ГОСТ-свойства"
  }
}
```

`sbomFixer.rules` (en):

```json
"rules": {
  "reorder": "Reorder fields",
  "set_spec_version": "Set $.specVersion",
  "increment_version": "Increment $.version",
  "add_timestamp": "Add $.metadata.timestamp if missing",
  "add_manufacturer": "Add $.metadata.component.manufacturer if missing",
  "components": {
    "filter_external_references": "Keep only VCS and source-distribution references",
    "filter_properties": "Keep only GOST properties",
    "fill_missing_gost_properties": "Add missing GOST properties"
  }
}
```

`sbomFixer.help`: перенести тексты `root.set_spec_version`, `root.increment_version`, `metadata.add_timestamp`, `metadata_component.add_manufacturer` на плоские ключи `set_spec_version`, `increment_version`, `add_timestamp`, `add_manufacturer`; ключ `reorder` получает объединённое описание:

```json
"reorder": "Приводит ключи корневого объекта, metadata, metadata.component и каждого компонента дерева components[] к каноническому порядку. У корня: bomFormat, specVersion, serialNumber, version, metadata, components, annotations. У metadata: timestamp, component. У metadata.component: type, name, version, manufacturer. У компонента: type, name, version, purl, externalReferences, properties, components. Остальные ключи сохраняют исходный относительный порядок; вложенные объекты внутри компонентов не упорядочиваются."
```

Английский текст — тот же смысл. Удалить старые вложенные ключи `rules.root`, `rules.metadata`, `rules.metadata_component`, `help.root`, `help.metadata`, `help.metadata_component`; `help.components` оставить без `reorder`.

- [ ] **Step 8: Прогнать frontend-тесты и сборку**

Run: `npm --prefix frontend run test -- src/views/SbomFixer.test.ts src/views/sbomFixerRules.test.ts`
Expected: PASS.

Run: `npm --prefix frontend run build`
Expected: PASS (vue-tsc не находит удалённых полей/типов).

- [ ] **Step 9: Коммит**

```bash
git add frontend/src/types/api.ts frontend/src/views/sbomFixerRules.ts frontend/src/views/sbomFixerRules.test.ts frontend/src/views/SbomFixer.vue frontend/src/views/SbomFixer.test.ts frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json
git commit -m "feat: group fix rules into base and components sections"
```

---

### Task 3: Таблица несоответствий без обрезания

**Files:**
- Modify: `frontend/src/views/SbomFixer.vue:361-383` (ячейки), `frontend/src/views/SbomFixer.vue:975-1005` (стили)
- Test: `frontend/src/views/SbomFixer.test.ts` (тест `renders issues in a closed spoiler...`)

**Interfaces:**
- Consumes: разметка `issues-table` из Task 2 (структура не менялась).
- Produces: ячейки без `title`, стили без `text-overflow`; обёртка только с вертикальной прокруткой.

- [ ] **Step 1: Добавить ожидания в тест таблицы несоответствий**

В `renders issues in a closed spoiler and builds the table only when opened` заменить `expect(rows[0].findAll('td')[0].attributes('title')).toBeTruthy()` на:

```ts
expect(rows[0].findAll('td')[0].attributes('title')).toBeUndefined()
```

Добавить тест:

```ts
it('renders long issue values in full without truncation attributes', async () => {
  const longPath = '$.components[0].components[1].components[2].components[3]'
  const longName = 'very-long-component-name-without-any-break-opportunities'
  fixSbomMock.mockResolvedValueOnce({
    ...issuesResponse,
    issues: [
      {
        code: 'component.missing_name',
        path: longPath,
        component: longName,
        details: { expected: 'a-very-long-value-that-must-remain-visible' },
      },
    ],
  })
  const wrapper = await mountFixer()
  await selectFile(wrapper)
  await wrapper.find('.fix-button').trigger('click')
  await flushPromises()

  const spoiler = wrapper.find('.issues-spoiler')
  ;(spoiler.element as HTMLDetailsElement).open = true
  await spoiler.trigger('toggle')
  await wrapper.vm.$nextTick()

  const cells = wrapper.findAll('.issues-table tbody tr td')
  expect(cells[1].text()).toBe(longPath)
  expect(cells[2].text()).toBe(longName)
  expect(cells[3].text()).toBe('{"expected":"a-very-long-value-that-must-remain-visible"}')
})
```

Замечание: перенос строк задаётся CSS в `<style scoped>`, а jsdom не вычисляет scoped-стили, поэтому тест фиксирует полный текст и отсутствие `title`; визуальный перенос проверяется на ревью.

Run: `npm --prefix frontend run test -- src/views/SbomFixer.test.ts`
Expected: FAIL — в существующем тесте таблицы ячейка ещё имеет атрибут `title`.

- [ ] **Step 2: Убрать `title` у ячеек таблицы несоответствий**

В шаблоне заменить:

```html
<td class="issue-code" :title="issueLabel(issue)">{{ issueLabel(issue) }}</td>
<td class="issue-path" :title="issue.path">{{ issue.path }}</td>
<td class="issue-component" :title="issue.component ?? ''">{{ issue.component ?? '' }}</td>
<td class="issue-details" :title="issueDetails(issue)">{{ issueDetails(issue) }}</td>
```

на те же ячейки без `:title`.

- [ ] **Step 3: Разрешить перенос и убрать фиксированную раскладку**

В `<style scoped>`:

- удалить `.issues-table { table-layout: fixed; }`;
- удалить правила `overflow: hidden; text-overflow: ellipsis; white-space: nowrap;` у `.issues-table th, .issues-table td`;
- удалить `.issue-code { width: 30%; }`, `.issue-path { width: 25%; }`, `.issue-component { width: 15%; }`, `.issue-details { width: 30%; }`;
- `.issues-table-wrapper` заменить на `max-height: 24rem; overflow-y: auto; overflow-x: hidden;`;
- добавить перенос для длинных значений:

```css
.issues-table td {
  overflow-wrap: anywhere;
  word-break: break-word;
}
```

- [ ] **Step 4: Прогнать тесты**

Run: `npm --prefix frontend run test -- src/views/SbomFixer.test.ts`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/views/SbomFixer.vue frontend/src/views/SbomFixer.test.ts
git commit -m "fix: show full issue values in the sbom fixer table"
```

---

### Task 4: Project specs

**Files:**
- Modify: `specs/domains/sbom-fixing.md`
- Modify: `specs/contracts/api-contract.md`
- Modify: `specs/domains/web-ui.md`

**Interfaces:**
- Consumes: финальные модели, `RULE_IDS`, статистика и интерфейс из Task 1–3.
- Produces: согласованное описание домена, контракта и web-интерфейса.

- [ ] **Step 1: Обновить `specs/domains/sbom-fixing.md`**

- В описании и списке ключевых файлов заменить «11 static rules» на «8 static rules».
- В блоке `RULE_IDS` оставить 8 id из Global Constraints.
- В блоке моделей: `SbomFixOptions` с плоскими полями и валидаторами; `ComponentsFixOptions` без `reorder`; удалить `RootFixOptions`, `MetadataFixOptions`, `MetadataComponentFixOptions`.
- В разделе про defaults заменить «10 entries (the 11 static rules minus ...)» на «7 entries (the 8 static rules minus ...)».
- Таблицу правил переписать: правило 1 — `reorder` (охват четырёх объектов, `count` — число объектов с изменённым порядком, по 1 за объект), далее `set_spec_version`, `increment_version`, `add_timestamp`, `add_manufacturer`, затем три `components.*`; нумерация 1–8.
- В Flow: «6. reorder pass LAST» → «6. reorder rule LAST (root → metadata → metadata.component → all components)».
- В notes заменить «The reorder pass (rules 1, 5, 6, 8)» на «The `reorder` rule (rule 1)».
- В статистике: строка `reorder` одна; default 7; пример ответа с `"rule_id": "reorder"`.
- В инвариантах: «The reorder pass is the final mutation» оставить, уточнив единственное правило.
- В Configuration: legacy-ключи опций игнорируются, миграции нет; описать плоскую форму сохранённого JSON.

- [ ] **Step 2: Обновить `specs/contracts/api-contract.md`**

- Строка 120: «grouped fix options with master checkboxes» → три подраздела: базовых правок, `components[]`, белого списка.
- Строка 133: defaults — все статические правила включены, кроме `components.fill_missing_gost_properties`.
- JSON-пример опций (строки 136–163) заменить на плоскую форму из дизайна, раздел 6.2.
- Пример успешного ответа: `"rule_id": "root.reorder"` → `"rule_id": "reorder"`.
- Проверить, что больше нет упоминаний `root`/`metadata`/`metadata.component` как групп опций.

- [ ] **Step 3: Обновить `specs/domains/web-ui.md`**

- Ключевые файлы: «11 static fix rules» → «8 static fix rules».
- Раздел «Fix SBOM Page»:
  - каталог — 8 правил, `BASE_RULES` (5) + `COMPONENTS_RULES` (3);
  - опции сгруппированы в «Базовые правки» (`data-group="basic"`), «Правки массива components[]» (`data-group="components"`) и карточку белого списка; отдельных карточек `root`, `metadata`, `metadata.component` нет;
  - мастер-чекбоксы: у «Базовых правок» управляет пятью флагами, у компонентной карточки — тремя; «Выбрать всё»/«Снять всё» действуют в своей карточке;
  - текстовые поля `spec_version` и `manufacturer` активны при включённых `set_spec_version`/`add_manufacturer`;
  - названия базовых пунктов содержат путь (`$.specVersion`, `$.version`, `$.metadata.timestamp`, `$.metadata.component.manufacturer`), у `reorder` перечислены все объекты;
  - пункт про `title` в таблице несоответствий заменить: значения переносятся и видны целиком, `title` не используется, таблица прокручивается только по вертикали.

- [ ] **Step 4: Проверить, что старые имена не остались**

Run: `grep -rn "root\.reorder\|metadata\.reorder\|metadata_component\.reorder\|components\.reorder\|RootFixOptions\|MetadataComponentFixOptions\|11 static" specs/ src/ frontend/src tests/`
Expected: пусто (кроме исторических design/plan документов в `docs/superpowers/`).

- [ ] **Step 5: Коммит**

```bash
git add specs/domains/sbom-fixing.md specs/contracts/api-contract.md specs/domains/web-ui.md
git commit -m "docs: describe merged reorder rule and new fix sections"
```

---

## Self-Review

- **Spec coverage:** плоская модель (Task 1), единое правило и статистика (Task 1), типы и каталог (Task 2), три подраздела и i18n (Task 2), перенос строк в таблице (Task 3), specs (Task 4). Пункты дизайна 5.1–5.4, 6, 7, 8, 9, 10 покрыты.
- **Step scan:** каждый шаг даёт одно проверяемое действие; тела функций приведены только там, где сигнатура и тесты не определяют реализацию (`_apply_reorder`, модели).
- **Type consistency:** `BASE_RULES`/`COMPONENTS_RULES`/`ALL_FIX_RULES`, `SbomFixOptions` с плоскими полями, `RULE_IDS` из 8 id совпадают во всех задачах; rule id в тестах и статистике совпадают.
- **Review Focus:** пять строк покрыты тестами Task 1 и Task 3; CSS-перенос отмечен как проверяемый ревью.
