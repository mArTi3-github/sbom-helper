# «Исправить SBOM» — удаление необязательных полей по белому списку: дизайн

Документ дополняет и частично заменяет `2026-10-26-sbom-fixer-design.md` (разделы 6.2–6.4, 7, 9, 10) и `2026-10-29-sbom-fixer-rule-help-design.md` (состав правил). При расхождениях приоритет у этого документа.

## 1. Задача и зачем

Сейчас удаление полей в разделе «Исправить SBOM» задано фиксированными булевыми опциями: `root.remove_dependencies`, `root.remove_services`, `metadata.remove_properties`, `metadata.remove_tools`, `metadata_component.remove_external_references`, `metadata_component.remove_properties`, `metadata_component.remove_purl`, `metadata_component.remove_scope`, `components.remove_hashes`, `components.remove_scope`. Набор жёстко зашит в код и не зависит от того, какие поля реально есть в документе.

Нужен отдельный подраздел **«Удаление необязательных полей по „белому списку“»**, который:

- по кнопке «Проанализировать» показывает, какие поля, не описанные в требованиях ФСТЭК, реально присутствуют в загруженном SBOM;
- позволяет отметить подмножество этих полей для удаления;
- удаляет отмеченные поля при нажатии общей кнопки «Исправить»;
- явно демонстрирует в UI два белых списка: неизменяемый справочник полей из требований ФСТЭК и редактируемый список «практически полезных» полей, которые не рекомендуется удалять.

Это **косметическая чистка**, а не приведение SBOM в соответствие с методикой: вводный абзац П.1 прямо допускает дополнительные поля CycloneDX. UI должен это объяснять.

## 2. Цели, не-цели и анти-цели

### Цели

- Подраздел «Удаление необязательных полей по „белому списку“» на странице `/fix-sbom`.
- Кнопка «Проанализировать»: анализ загруженного файла без его изменения.
- Список кандидатов: только реально присутствующие поля, которых нет ни в списке 1, ни в списке 2; путь, число вхождений, чекбокс; по умолчанию ничего не отмечено; кнопки «Выбрать всё»/«Снять всё».
- Список 1 (read-only): все поля из таблиц П.1–П.8 со статусом «Обязательно»/«Опционально» и оговорками для условно обязательных полей.
- Список 2 (редактируемый): «не рекомендуется удалять», 10 значений по умолчанию, хранение на сервере, сохранение общей кнопкой «Сохранить», сброс общей кнопкой «Вернуть значения по умолчанию».
- Все 10 прежних правил удаления переносятся в новую механику и удаляются из статического каталога правил.
- Правило `metadata_component.rename_supplier` заменяется на `metadata_component.add_manufacturer` с текстовым значением.
- Статистика по каждому выбранному пути; отчёт о несоответствиях не меняется.
- Полная локализация en/ru, тесты backend и frontend, обновление project specs.

### Не-цели

- Полная проверка соответствия методике ФСТЭК.
- Проверка перекрёстных ссылок (`bom-ref` ↔ `dependencies`) и предупреждение о них.
- Рекурсивный обход произвольных вложенных структур: анализируются только прямые ключи объектов, описанных в ФСТЭК, и рекурсия по `components[]`.
- Сохранение выбранных для удаления полей на сервере: выбор живёт в рамках текущего файла.
- Поддержка обратной совместимости со старым `data/sbom_fix_options.json`: старые ключи игнорируются, миграции нет.
- История запусков, БД, очередь.
- Изменение существующих проверок отчёта и их кодов.

### Анти-цели

- Удалять поле, которое пользователь не отмечал.
- Позволять удалить поле из списков 1 или 2.
- Молча менять документ, не отражая это в статистике.
- Падать с 500 на неожиданной форме документа или на некорректной строке списка 2.
- Выдавать анализ за проверку соответствия ФСТЭК.

## 3. Ограничения и допущения

- Вход валидируется существующим `CycloneDXParser`; лимит размера — `sbom_settings.max_file_size` (200 МБ).
- Новых внешних зависимостей нет; backend — Pydantic + stdlib, frontend — Vue 3 + vue-i18n.
- Файл передаётся на сервер дважды: при анализе и при исправлении. Файл остаётся выбранным в браузере, повторный выбор не нужен.
- Ответ анализа компактный (уникальные пути и счётчики), поэтому фильтрация по спискам 1 и 2 выполняется на фронтенде и не зависит от размера файла.
- Python `dict` сохраняет порядок; удаление ключей порядок остальных не меняет.
- Все пользовательские строки — через i18n; ошибки API — машиночитаемые коды.
- Проверки запускаются в `.venv`; фронтенд — `npm --prefix frontend`.

## 4. Рассмотренные подходы

### Подход 1 — каталог и анализ на сервере (выбран)

Единый каталог полей и анализатор в Python; отдельные endpoint'ы каталога и анализа; выбранные пути передаются в fix отдельным параметром. Фронтенд фильтрует компактный инвентарь по спискам 1 и 2.

Плюсы: единый источник истины, серверная валидация выбранных путей, совпадение с текущей архитектурой, тестируемость на Python. Минусы: два новых endpoint'а, двойная передача файла, каталог поддерживается в коде.

### Подход 2 — анализ на фронтенде по общему JSON-каталогу

Каталог — статический JSON для Python и Vue; браузер сам читает и обходит файл.

Минусы: разбор 100+ МБ JSON блокирует UI и требует много памяти; логика обхода дублируется; риск расхождения анализа и исправления. Отклонён.

### Подход 3 — одна загрузка с серверной сессией

Сервер кэширует разобранный документ под токеном. Минусы: серверное состояние, TTL, конкурентность, память на 100+ МБ; противоречит stateless-принципу раздела. Отклонён.

**Решение:** подход 1.

## 5. Пользовательский сценарий

1. Пользователь открывает `/fix-sbom`; параллельно загружаются сохранённые опции, каталог полей и настройки приложения.
2. Загружает JSON. Анализ, результаты и выбранные поля сбрасываются; опции не сбрасываются.
3. Нажимает «Проанализировать». Появляется список кандидатов с числом вхождений; все чекбоксы сняты.
4. При необходимости правит список 2, сохраняет настройки. Список кандидатов пересчитывается сразу после правки; путь, добавленный в список 2, исчезает из кандидатов, и его отметка снимается.
5. Отмечает поля (вручную или «Выбрать всё») и нажимает общую «Исправить».
6. Получает исправленный документ, статистику (включая строки по удалённым полям) и отчёт о несоответствиях.
7. Скачивает `<имя>_fixed.json`.

Если анализ не запускался, «Исправить» работает как раньше: удаляются только поля, отмеченные в предыдущем анализе (после нового выбора файла — ни одного), остальные правила применяются.

## 6. Белые списки

### 6.1. Список 1 — справочник ФСТЭК (read-only)

Каталог хранится в коде (`FSTEC_FIELDS`) и отдаётся в UI. Строка: `path`, `status` (`mandatory` | `optional`), необязательный `condition_key` для условной обязательности. Порядок — по таблицам П.1–П.8.

| Путь | Статус | Оговорка |
|---|---|---|
| `root.bomFormat` | mandatory | |
| `root.specVersion` | mandatory | |
| `root.serialNumber` | optional | |
| `root.version` | mandatory | |
| `root.metadata` | mandatory | |
| `root.components` | mandatory | обязательно при наличии компонентов |
| `root.annotations` | optional | |
| `metadata.timestamp` | mandatory | |
| `metadata.component` | mandatory | |
| `metadata.component.type` | mandatory | |
| `metadata.component.name` | mandatory | |
| `metadata.component.version` | mandatory | |
| `metadata.component.manufacturer` | mandatory | |
| `metadata.component.manufacturer.name` | mandatory | |
| `components[].type` | mandatory | |
| `components[].name` | mandatory | |
| `components[].version` | mandatory | |
| `components[].purl` | mandatory | |
| `components[].cpe` | optional | |
| `components[].externalReferences` | mandatory | |
| `components[].properties` | mandatory | |
| `components[].components` | optional | |
| `components[].externalReferences[].type` | mandatory | |
| `components[].externalReferences[].url` | mandatory | |
| `components[].externalReferences[].hashes` | optional | обязательно для `source-distribution` |
| `components[].externalReferences[].hashes[].alg` | mandatory | |
| `components[].externalReferences[].hashes[].content` | mandatory | |
| `components[].properties[].name` | mandatory | |
| `components[].properties[].value` | mandatory | |

Вложенные пути (`manufacturer.name`, `externalReferences[]`, `properties[]`, `hashes[]`) входят в список 1 для прозрачности, но в словарь кандидатов не входят и потому никогда не предлагаются к удалению. Защита вложенных полей обеспечивается защитой родительского ключа.

`FSTEC_FIELDS` — единственный источник списка 1; локализуются только подписи статусов и оговорок, сами пути показываются как есть.

### 6.2. Список 2 — «не рекомендуется удалять» (редактируемый)

Хранится в опциях как `optional_fields.keep: list[str]`. Значения по умолчанию (`DEFAULT_KEEP_FIELDS`):

```
metadata.tools
metadata.component.properties
metadata.component.group
metadata.component.purl
metadata.component.externalReferences
metadata.component.bom-ref
components[].group
components[].licenses
components[].description
components[].bom-ref
```

Канонические пути `bom-ref` — `metadata.component.bom-ref` и `components[].bom-ref`: в грамматике раздела 6.3 нет префикса `component.`. `bom-ref` не описан в таблицах П.1–П.8, поэтому без списка 2 он попадал бы в кандидаты; по умолчанию он защищён, чтобы не рвать ссылки в `dependencies`.

Семантика: поле из списка 2 не может быть удалено — оно исключается из кандидатов и игнорируется сервером, если всё же пришло в `remove_fields`. Список 2 может содержать пути, которых нет в текущем документе; это нормально.

### 6.3. Синтаксис путей

```
root.<field>
metadata.<field>
metadata.component.<field>
components[].<field>
```

`<field>` — один или более символов из `[A-Za-z0-9_$@.-]`. Проверка префикса — по самому длинному совпадению (`metadata.component.` раньше `metadata.`). Регистр значим.

Валидация списка 2 разделена на два уровня:

- **Модель (fix и загрузка настроек) — толерантная.** Валидатор `keep` обрезает строки, отбрасывает пустые, дубликаты, строки вне грамматики и строки из списка 1. Ошибки не возникает: невалидная строка просто не участвует в обработке. Это гарантирует, что «Исправить» не падает из-за недописанной строки в ещё не сохранённом списке 2.
- **Сохранение (`POST /options`) — строгая.** До валидации модели route проверяет исходный массив: строка вне грамматики или строка из списка 1 даёт `400 invalid_options` с перечислением ошибочных строк в `detail`. Пустой список допустим.

При загрузке повреждённого файла настроек действует существующее поведение: warning в лог и полный набор значений по умолчанию.

## 7. Анализ документа

### 7.1. Словарь кандидатов

Анализатор обходит:

- прямой объект корня;
- `metadata`, если это объект;
- `metadata.component`, если это объект;
- элементы массива `components` и рекурсивно их вложенные `components` (pre-order).

Для каждого объекта собираются **прямые ключи**. Внутрь значений не спускаются: `externalReferences`, `properties`, `licenses`, `hashes`, `manufacturer`, `supplier` и любые другие объекты/массивы рассматриваются как единое поле. `metadata.component.components` — прямой ключ `metadata.component`, который может быть удалён целиком; его поддерево не обходится. Ключи, не соответствующие грамматике пути из раздела 6.3 (пробелы, двоеточия, слэши и т. п.), в анализ не попадают: иначе в UI появился бы чекбокс, который сервер молча игнорирует.

Канонический путь: ключ корня → `root.<key>`; ключ `metadata` → `metadata.<key>`; ключ `metadata.component` → `metadata.component.<key>`; ключ компонента на любом уровне → `components[].<key>`.

### 7.2. Статус и счётчик

Для каждого встреченного пути:

- если путь есть в `FSTEC_FIELDS` — статус из каталога (`mandatory`/`optional`);
- иначе — `additional` (дополнительное поле CycloneDX, допускается методикой).

`count`: для `root`, `metadata`, `metadata.component` — 1, если ключ присутствует; для `components[]` — число объектов-компонентов (на всех уровнях), в которых ключ присутствует.

Порядок результата детерминирован: `root`, `metadata`, `metadata.component`, `components[]`; внутри группы — по алфавиту.

### 7.3. Кандидаты в UI

Кандидат = запись анализа со статусом `additional`, чей путь не входит в `optional_fields.keep`. Записи со статусом `mandatory`/`optional` показываются только в списке 1 и в кандидаты не попадают.

Фильтрация выполняется на фронтенде по закэшированному результату анализа; сервер повторно проверяет выбор при исправлении. Правка списка 2 пересчитывает кандидатов без повторной загрузки файла.

## 8. Удаление полей

### 8.1. Выбор

`remove_fields: list[str]` передаётся в `POST /api/v1/sbom/fix` отдельным form-полем (JSON-массив строк) и **не сохраняется** в настройках. Сервер:

1. проверяет, что значение — JSON-массив строк; иначе `400 invalid_remove_fields`;
2. отбрасывает строки, не соответствующие грамматике;
3. отбрасывает пути из `FSTEC_FIELDS` и из переданного `options.optional_fields.keep`;
4. схлопывает дубликаты;
5. удаляет оставшиеся пути.

Невалидные и запрещённые строки не дают ошибки и не попадают в статистику.

### 8.2. Применение

- `root.<field>` → удалить ключ корня.
- `metadata.<field>` → удалить ключ, если `metadata` — объект.
- `metadata.component.<field>` → удалить ключ, если `metadata.component` — объект.
- `components[].<field>` → удалить ключ из каждого объекта-компонента на всех уровнях вложенности **внутри корневого `components`**. Поддерево `metadata.component.components` не обходится — ровно как и при анализе, поэтому статистика удаления не может превысить числа вхождений из анализа. Сам ключ `metadata.component.components` (прямой ключ `metadata.component`) удаляется целиком по обычному правилу `metadata.component.<field>`.

Удаляется ключ целиком (вместе со значением любой формы, включая пустой массив/объект). Отсутствие ключа даёт `count = 0`. Поле `group` теперь может быть удалено, если пользователь убрал его из списка 2 — прежнее ограничение «group не меняется нигде» отменяется.

### 8.3. Порядок конвейера

1. Глубокая копия.
2. Удаление выбранных необязательных полей.
3. Корень: `specVersion`, инкремент `version`.
4. `metadata`: `add_timestamp`; `metadata.component`: `add_manufacturer`.
5. `components`: фильтр `externalReferences`, фильтр `properties`, добавление недостающих ГОСТ-свойств.
6. Переупорядочивание — последним проходом.
7. Статистика и отчёт.

Удаление выполняется до `add_manufacturer`, чтобы добавленное поле не могло быть удалено тем же запуском. `add_manufacturer` не зависит от `supplier`: `supplier` остаётся в документе и попадает в кандидаты как дополнительное поле.

## 9. Правило `add_manufacturer`

Заменяет `metadata_component.rename_supplier`.

Модель: `add_manufacturer: bool = True`, `manufacturer: str = "Positive Technologies"`.

- Значение обрезается по краям; пустая строка отклоняется валидатором (как `spec_version`), независимо от флага.
- Если `add_manufacturer` включено и `metadata.component` — объект: `manufacturer` считается отсутствующим, если это не объект или его `name` не непустая строка. В этом случае записывается `{"name": "<значение>"}`; счётчик 1. Существующий корректный `manufacturer` не меняется; счётчик 0.
- `supplier` не читается и не изменяется.
- Если `metadata.component` отсутствует, правило ничего не делает; отчёт даёт `metadata_component.missing_manufacturer`.
- UI: рядом с чекбоксом — текстовый input, доступный только при включённом правиле (как `specVersion` у `root.set_spec_version`).

## 10. Модель опций

```python
class RootFixOptions(BaseModel):
    reorder: bool = True
    set_spec_version: bool = True
    spec_version: str = "1.7"
    increment_version: bool = True

class MetadataComponentFixOptions(BaseModel):
    reorder: bool = True
    add_manufacturer: bool = True
    manufacturer: str = "Positive Technologies"

class MetadataFixOptions(BaseModel):
    add_timestamp: bool = True
    reorder: bool = True
    component: MetadataComponentFixOptions = Field(default_factory=MetadataComponentFixOptions)

class ComponentsFixOptions(BaseModel):
    reorder: bool = True
    filter_external_references: bool = True
    filter_properties: bool = True
    fill_missing_gost_properties: bool = False

class OptionalFieldsFixOptions(BaseModel):
    keep: list[str] = Field(default_factory=lambda: list(DEFAULT_KEEP_FIELDS))

class SbomFixOptions(BaseModel):
    root: RootFixOptions = Field(default_factory=RootFixOptions)
    metadata: MetadataFixOptions = Field(default_factory=MetadataFixOptions)
    components: ComponentsFixOptions = Field(default_factory=ComponentsFixOptions)
    optional_fields: OptionalFieldsFixOptions = Field(default_factory=OptionalFieldsFixOptions)
```

Удалены: `remove_dependencies`, `remove_services`, `metadata.remove_properties`, `remove_tools`, `metadata_component.remove_external_references`, `remove_properties`, `remove_purl`, `remove_scope`, `components.remove_hashes`, `remove_scope`, `rename_supplier`. Старый файл настроек читается без ошибки: лишние ключи игнорируются, отсутствующие получают значения по умолчанию.

## 11. Статистика и отчёт

Статический канонический порядок (11 правил):

1. `root.reorder`
2. `root.set_spec_version`
3. `root.increment_version`
4. `metadata.add_timestamp`
5. `metadata.reorder`
6. `metadata_component.reorder`
7. `metadata_component.add_manufacturer`
8. `components.reorder`
9. `components.filter_external_references`
10. `components.filter_properties`
11. `components.fill_missing_gost_properties`

В статическую часть попадают **только включённые** правила, как и раньше. При значениях по умолчанию это 10 строк: `components.fill_missing_gost_properties` выключено. После статических строк идут строки удаления — по одной на каждый выбранный и принятый путь, в порядке «root → metadata → metadata.component → components[], внутри группы по алфавиту». Строка удаления включается и при `count = 0`.

Формат:

```json
{ "rule_id": "optional_fields.remove", "field": "components[].hashes", "count": 4 }
```

`field` присутствует только у строк удаления. `changed` — `true`, если хотя бы один `count > 0`.

Отчёт о несоответствиях (`issues`) не меняется. Побочный эффект: удаление `components[].licenses` может привести к появлению `component.missing_source_reference` у proprietary-компонентов; удаление `bom-ref` при сохранённом `dependencies` даёт висячие ссылки, которые раздел не проверяет.

## 12. API

### 12.1. `GET /api/v1/sbom/fix/field-catalog`

```json
{
  "fstec_fields": [
    { "path": "root.bomFormat", "status": "mandatory" },
    { "path": "components[].externalReferences[].hashes", "status": "optional",
      "condition_key": "sourceDistributionHashes" }
  ],
  "default_keep": ["metadata.tools", "..."]
}
```

### 12.2. `POST /api/v1/sbom/fix/analyze`

`multipart/form-data`, поле `file`. Ошибки те же, что у fix: `413 file_too_large`, `400 invalid_json`, `400 invalid_sbom`, `422` без файла. Документ не изменяется.

```json
{
  "fields": [
    { "path": "root.version", "status": "mandatory", "count": 1 },
    { "path": "components[].scope", "status": "additional", "count": 21931 }
  ]
}
```

### 12.3. `POST /api/v1/sbom/fix`

Добавляется необязательное form-поле `remove_fields` — JSON-строка с массивом путей. Отсутствие = пустой массив. Ошибка разбора или не-массив → `400 invalid_remove_fields`. Остальное без изменений.

### 12.4. `GET/POST /api/v1/sbom/fix/options`

Форма ответа расширяется блоком `optional_fields`. При сохранении `keep` проверяется строго по разделу 6.3: невалидная строка → `400 invalid_options` (`detail` содержит ошибочные строки). В fix и при загрузке файла настроек действует толерантная нормализация: невалидные строки отбрасываются без ошибки.

## 13. Frontend

### 13.1. Каталог правил

`frontend/src/views/sbomFixerRules.ts` приводится к 11 правилам: из `ROOT_RULES`, `METADATA_RULES`, `METADATA_COMPONENT_RULES`, `COMPONENTS_RULES` удаляются перенесённые правила, `rename_supplier` заменяется на `add_manufacturer` с примером «до/после». `METADATA_COMPONENT_RULES` получает поле значения для `add_manufacturer` (аналогично `spec_version`).

### 13.2. Новая карточка

Карточка `data-group="optional-fields"` размещается после карточки `components`, перед панелью с кнопкой «Исправить»:

- заголовок и пояснение, что это косметическая чистка (дополнительные поля CycloneDX допускаются);
- кнопка «Проанализировать», disabled без файла и во время запроса;
- до анализа — подсказка загрузить файл и запустить анализ;
- после анализа — таблица кандидатов: путь, число вхождений, чекбокс; кнопки «Выбрать всё»/«Снять всё» (только по кандидатам); пустой список — сообщение «Необязательных полей не найдено»;
- список 1 — read-only, в сворачиваемом блоке (`<details>`, закрыт по умолчанию), таблица «Путь | Статус» с локализованными статусами и оговорками;
- список 2 — редактируемый `<textarea>` (один путь на строку), подпись «Не рекомендуется удалять», inline-ошибка валидации после неудачного сохранения.

Ошибки анализа отображаются в существующем блоке ошибок страницы. Новый файл сбрасывает результат анализа, кандидатов и выбранные пути.

### 13.3. Состояние

- `analysis: OptionalFieldInfo[] | null`, `selectedRemoveFields: Set<string>`.
- Кандидаты — `computed` от `analysis` и `options.optional_fields.keep`.
- Правка `keep` фильтрует кандидатов сразу; пути, переставшие быть кандидатами, удаляются из `selectedRemoveFields`.
- «Вернуть значения по умолчанию» восстанавливает статические опции, `spec_version`, `manufacturer` и `optional_fields.keep` из `default_keep`, полученного в ответе каталога. Фронтенд не хранит собственную копию десяти путей — единственный источник это `DEFAULT_KEEP_FIELDS` на сервере.
- Каталог загружается при монтировании параллельно опциям. Если запрос каталога не удался, карточка показывает некритичное предупреждение: список 1 скрыт, «Вернуть значения по умолчанию» сбрасывает статические опции, но оставляет `optional_fields.keep` без изменений. Анализ и выбор полей при этом работают: статусы приходят в ответе анализа, каталог для фильтрации не нужен.
- «Сохранить» отправляет `optional_fields.keep` вместе с остальными опциями.
- «Исправить» отправляет `remove_fields` только из принятых кандидатов.
- Статистика: для строк с `field` отображается локализованное название `optional_fields.remove` и путь; для остальных — как сейчас.

### 13.4. API-клиент и типы

`frontend/src/api/sbom.ts`: `analyzeSbom(file)`, `getFieldCatalog()`; `fixSbom(file, options, removeFields)`.

`frontend/src/types/api.ts`: `OptionalFieldStatus`, `OptionalFieldInfo`, `FieldCatalogResponse`, `OptionalFieldsFixOptions`; `SbomFixOptions.optional_fields`; `SbomFixStat.field?`.

### 13.5. Локали

Удаляются ключи `rules`/`help` для 10 перенесённых правил и `rename_supplier`; добавляются `add_manufacturer` (правило, справка, пример), ключи новой карточки, статусы и оговорки каталога, `errors.invalid_remove_fields`. Структура ru/en идентична.

## 14. Файлы

| Файл | Изменение |
|---|---|
| `src/purl_resolver/sbom/optional_fields.py` | **NEW** — каталог, грамматика путей, анализ, удаление, валидация `keep` |
| `src/purl_resolver/sbom/fixer.py` | **EDIT** — модель опций, `add_manufacturer`, новый конвейер, динамическая статистика |
| `src/purl_resolver/sbom/__init__.py` | **EDIT** — экспорт новых функций/констант |
| `src/purl_resolver/routes/sbom_fix.py` | **EDIT** — каталог, анализ, `remove_fields`, валидация keep |
| `src/purl_resolver/router.py` | без изменений |
| `src/purl_resolver/sbom_fix_options_store.py` | без изменений |
| `frontend/src/views/SbomFixer.vue` | **EDIT** — новая карточка, анализ, выбор полей |
| `frontend/src/views/sbomFixerRules.ts` | **EDIT** — 11 правил, `add_manufacturer` |
| `frontend/src/api/sbom.ts` | **EDIT** — новые вызовы |
| `frontend/src/types/api.ts` | **EDIT** — типы |
| `frontend/src/i18n/locales/{ru,en}.json` | **EDIT** — ключи |
| `tests/test_sbom_optional_fields.py` | **NEW** |
| `tests/test_sbom_fixer.py` | **EDIT** |
| `tests/test_sbom_fix_api.py` | **EDIT** |
| `frontend/src/views/sbomFixerRules.test.ts`, `SbomFixer.test.ts` | **EDIT** |
| `specs/domains/sbom-fixing.md` | **EDIT** |
| `specs/contracts/api-contract.md` | **EDIT** |
| `specs/domains/web-ui.md` | **EDIT** |
| `specs/architecture/layers.md` | **EDIT** — новый модуль и endpoint'ы |
| `specs/INDEX.md` | **EDIT** — новый документ и файлы |

## 15. Тестирование

### Backend

- Каталог: состав и статусы соответствуют таблице 6.1; `DEFAULT_KEEP_FIELDS` — ровно 10 значений, включая `metadata.component.bom-ref` и `components[].bom-ref`.
- Анализ: корень, `metadata`, `metadata.component`, компоненты на 3+ уровнях; `components[]` нормализует пути на всех уровнях; счётчики; не-объекты пропускаются; отсутствующие объекты не дают путей; внутрь `externalReferences`/`properties`/`licenses`/`hashes` не спускается; `metadata.component.components` не сканируется; порядок детерминирован.
- Удаление: каждый контекст; рекурсия компонентов; отсутствующий ключ → 0; невалидные, запрещённые списком 1 и списком 2 пути игнорируются; невыбранные поля не меняются; `group` удаляется, если не в списке 2; входной документ не мутируется.
- `add_manufacturer`: отсутствие/null/{}/пустой name → `{"name": value}`; существующий корректный не меняется; значение обрезается; пустое значение отклоняется; при отсутствии `metadata.component` — no-op; `supplier` не трогается.
- Порядок: удаление до `add_manufacturer`; reorder последним.
- Статистика: только включённые статические правила в каноническом порядке (по умолчанию 10 строк); строки удаления с `field`, включая нулевые; `changed`.
- API: каталог; анализ (200 и ошибки); fix с `remove_fields` (валидные, невалидные, защищённые); невалидные строки `keep` в fix не дают 400, а игнорируются; save options с валидным и невалидным `keep` (строгий 400); старый файл настроек читается без ошибки.
- Анализ пропускает ключи вне грамматики путей; удаление `components[].<field>` не заходит в `metadata.component.components`.

### Frontend

- «Проанализировать» вызывает `analyzeSbom`, рендерит пути и счётчики, чекбоксы сняты.
- Кандидаты исключают `mandatory`/`optional` и пути из `keep`.
- Правка `keep` сразу пересчитывает кандидатов и снимает отметку с исчезнувшего пути.
- «Выбрать всё»/«Снять всё» работают только по кандидатам.
- «Исправить» передаёт `remove_fields` и полный набор опций.
- Список 1 рендерится read-only со статусами; список 2 редактируется и сохраняется.
- «Вернуть значения по умолчанию» восстанавливает 10 путей и статические опции.
- Новый файл сбрасывает анализ и выбор.
- Ошибки анализа/сохранения отображаются; ошибка загрузки каталога не блокирует страницу, скрывает список 1 и оставляет `keep` при сбросе настроек без изменений.
- Статистика показывает строки с путём.
- Справка `add_manufacturer` открывается; у удалённых правил нет строк.

Команды:

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check src tests
npm test --prefix frontend
npm run build --prefix frontend
```

## 16. Обновление спецификаций

- `specs/domains/sbom-fixing.md` — 21 → 11 статических правил + динамическое удаление; новые опции, endpoint'ы, статистика, каталог, `add_manufacturer`, инвариант «ничего не удаляется по умолчанию».
- `specs/contracts/api-contract.md` — каталог, анализ, `remove_fields`, `invalid_remove_fields`, расширенный `optional_fields`, `field` в статистике.
- `specs/domains/web-ui.md` — новая карточка, анализ, списки, состояние, тесты.
- `specs/architecture/layers.md` — `sbom/optional_fields.py`, зависимости (stdlib + Pydantic, без импорта fixer), маршруты.
- `specs/INDEX.md` — новый дизайн-документ и файлы.

## 17. Риски и компромиссы

- Поведение по умолчанию меняется: удаления больше не включены, документ без отметок не чистится. Это осознанное следствие модели «пользователь выбирает поля по факту».
- Файл передаётся дважды; на 100+ МБ это заметно по сети, но не по памяти сервера (файл не кэшируется).
- Каталог ФСТЭК поддерживается вручную; при изменении методики нужно обновить `FSTEC_FIELDS` и тесты.
- Удаление `licenses` может ухудшить исключения отчёта; удаление `bom-ref` (если пользователь убрал его из списка 2) может порвать связи с `dependencies` — раздел это не проверяет и не предупреждает.
- Список 2 может содержать пути, которых нет в документе; это не ошибка.

## 18. Что остаётся исполнителю

- Точная вёрстка карточки, таблиц и `<textarea>` в рамках существующих CSS-переменных.
- Формулировки ru/en (смысл и ключи зафиксированы).
- Разбиение `optional_fields.py` на приватные функции и их имена.
- Тексты Pydantic-ошибок и `detail` для `invalid_options`/`invalid_remove_fields`.
- Набор фикстур; можно использовать `.misc/addictional_materials/debug/2026-06-11-sbom-enrichment-bug/ptsb@5.24.0.127610-release-5.24.0-cert-config.sbom.json`.
- Открыт ли список 1 по умолчанию (рекомендация: закрыт).
