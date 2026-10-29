# «Исправить SBOM» — дизайн

## 1. Задача и зачем

В веб-интерфейсе sbom-helper появляется новый раздел **«Исправить SBOM»** (английская версия — **«Fix SBOM»**). Он принимает CycloneDX SBOM в JSON, применяет выбранное пользователем подмножество формальных правок, возвращает исправленный документ, статистику изменений и отчёт о несоответствиях, которые остались после применения выбранных правок.

Задача раздела — устранять конкретные формальные дефекты, перечисленные ниже, а не полностью приводить SBOM в соответствие с методикой ФСТЭК. Генерацией корректного SBOM занимается другой сервис; sbom-helper на текущем этапе только выявляет и исправляет описанные недостатки.

Справочник требований: `.misc/addictional_materials/sbom_description_fstec.md` (таблицы П.1–П.8).

## 2. Цели, не-цели и анти-цели

### Цели

- Новая страница `/fix-sbom`, доступная из навигации и с домашней страницы.
- Загрузка CycloneDX JSON и применение выбранных правок.
- Каждая правка включается отдельно; группы имеют мастер-переключатели.
- По умолчанию включены все правки, кроме `metadata_component.remove_purl` и `components.fill_missing_gost_properties`; `specVersion` по умолчанию `1.7`.
- Целевая `specVersion` задаётся текстовым полем.
- Отдельные опции «увеличить `version` на 1», «добавить `metadata.timestamp`, если отсутствует» и «добавить недостающие ГОСТ-свойства».
- Набор опций сохраняется в конфигурации сервера (JSON-файл) и загружается при открытии страницы.
- Статистика по каждому включённому правилу.
- Отчёт о несоответствиях, оставшихся в итоговом документе.
- Объёмные отчёты в UI скрываются в спойлеры, чтобы не перегружать страницу.
- Скачивание исправленного JSON с отступом из настройки `json_indent`.
- Работа без PostgreSQL и без фоновой очереди.
- Детерминированный результат при фиксированном времени; входной документ не мутируется.
- Полная локализация en/ru.

### Не-цели

- Полная валидация соответствия методике ФСТЭК.
- Автоматическое добавление остальных обязательных полей (`manufacturer`, `type`/`name`/`version`/`purl` компонентов, внешние ссылки, хэши STREEBOG и т. п.). Исключение — `metadata.timestamp`, для которого есть отдельная опция.
- Нормализация PURL, дедупликация компонентов, анализ уязвимостей, преобразование XML ↔ JSON.
- Изменение поля `group` где бы то ни было.
- Удаление `hashes` внутри `externalReferences`.
- История запусков и запись результатов в БД.
- Проверка формата уже существующего `timestamp` и корректности URL.

### Анти-цели

- Молча удалять данные, не отражая это в статистике.
- Менять поля, которые пользователь не выбрал.
- Считать структурно некорректный SBOM «исправленным» без предупреждения.
- Требовать PostgreSQL для работы раздела.
- Возвращать 500 при неожиданной форме компонента вместо понятного отчёта.
- Выдавать отчёт за полную проверку соответствия ФСТЭК.

## 3. Ограничения и допущения

- Вход валидируется существующим `CycloneDXParser`: корень — объект, `bomFormat == "CycloneDX"`.
- Максимальный размер файла — `sbom_settings.max_file_size` (по умолчанию 200 МБ), как у остальных SBOM-инструментов.
- Python `dict` сохраняет порядок вставки, `json.loads` сохраняет порядок полей документа. Переупорядочивание выполняется построением нового `dict`; массивы не переупорядочиваются.
- Не-ASCII символы сохраняются (`ensure_ascii=False` на стороне API, `JSON.stringify` на стороне фронтенда).
- Новых внешних зависимостей нет. Для опций используется уже имеющийся Pydantic.
- Настройки раздела хранятся в JSON-файле на сервере, по аналогии с `IgnorePatternsStore`; БД не требуется.
- `metadata.timestamp` добавляется по текущему времени UTC в формате `YYYY-MM-DDTHH:MM:SSZ`. Для тестируемости время передаётся в `fix_sbom` параметром `now`; в production используется `datetime.now(timezone.utc)`.
- Все пользовательские строки — через `vue-i18n`; все ошибки API — машиночитаемые коды без `message`.
- Проверки и тесты запускаются в `.venv`; фронтенд — через `npm --prefix frontend`.

## 4. Рассмотренные подходы

### Подход 1 — явные опции + упорядоченный конвейер правил (выбран)

Новый чистый модуль `sbom/fixer.py` по образцу `sbom/images_list_converter.py`. Модель `SbomFixOptions` с явными булевыми полями; `fix_sbom(data, options, now=None)` делает глубокую копию, последовательно применяет именованные правила, собирает `stats` и `issues`. Роут `POST /api/v1/sbom/fix` принимает файл и JSON-опции. Настройки опций сохраняются на сервере через `SbomFixOptionsStore` (JSON-файл), по аналогии с `IgnorePatternsStore`. Страница повторяет устройство `ImagesListConverter.vue`, но с загрузкой/сохранением опций и сворачиваемым отчётом.

Плюсы: совпадает со стилем проекта, каждое правило тестируется отдельно, нет зависимости от БД и очереди, минимум абстракций. Минусы: новое правило затрагивает модель опций, модуль, i18n и UI; список правил конечен, поэтому это приемлемо.

### Подход 2 — декларативный реестр правил

Каждое правило — дескриптор с `id`, группой, функцией применения и функцией проверки; каталог отдаётся отдельным endpoint, UI строит чекбоксы динамически.

Плюсы: проще добавлять правила, меньше дублирования. Минусы: обобщённый движок и динамический UI для фиксированного набора; i18n-подписи всё равно ведутся вручную; лишняя абстракция на текущем этапе.

### Подход 3 — фоновая задача с профилями настроек

Новый тип задачи в `JobManager`, сохранённые профили в `SettingsStore`, опрос статуса и скачивание.

Плюсы: история, аудит, большие файлы. Минусы: требует PostgreSQL, добавляет состояния, polling и отмену, хотя преобразование быстрое и синхронное, как у Images List Converter. Для текущей задачи неоправданно тяжело.

**Решение:** подход 1. Обоснование — минимальное расхождение с существующей архитектурой, конечный набор правил, простая тестируемость.

## 5. Пользовательский сценарий

1. Пользователь открывает `/fix-sbom`. Страница загружает сохранённые на сервере опции; если сохранений нет — встроенные значения по умолчанию (включено всё, кроме `metadata_component.remove_purl` и `components.fill_missing_gost_properties`), `specVersion = "1.7"`.
2. Загружает `.json` (drag-and-drop или выбор файла).
3. Просматривает и при необходимости меняет правки. Кнопка «Сохранить настройки» записывает текущий набор в конфигурацию сервера; без сохранения набор действует только на текущий запуск.
4. Нажимает «Исправить».
5. Получает статус (изменения были / не требовались), статистику и отчёт о несоответствиях; отчёт по умолчанию свёрнут в спойлер.
6. Скачивает `<имя>_fixed.json`.

Если пользователь вручную снимет все правки, страница работает как проверка: возвращает исходный документ, пустую статистику и полный отчёт о несоответствиях. Это осознанное поведение. Поскольку по умолчанию включены почти все правки (включая удаление полей), над формой показывается предупреждение о том, что набор нужно проверить перед запуском.

## 6. Правила преобразования

### 6.1. Порядок применения

1. Глубокая копия входного документа.
2. Корень: установить `specVersion`, удалить `dependencies`, удалить `services`.
3. `metadata`: добавить `timestamp`, если он отсутствует; удалить `properties`, удалить `tools`.
4. `metadata.component`: удалить `externalReferences`, `properties`, `purl`, `scope`; переименовать `supplier` → `manufacturer`.
5. `components`: рекурсивно удалить `hashes` и `scope`, отфильтровать `externalReferences` и `properties`, добавить недостающие ГОСТ-свойства.
6. Корень: увеличить `version`.
7. Переупорядочивание: корень, `metadata`, `metadata.component`, все компоненты. Выполняется **последним отдельным проходом**, чтобы порядок отражал итоговый набор полей и ни одно более позднее правило его не нарушало.
8. Построение статистики и отчёта по итоговому документу.

Все правила работают с копией. Если правило выключено, соответствующие поля не меняются. Переупорядочивание уже стоит последним в конвейере; дополнительных проходов после него нет.

### 6.2. Группа 1 — корневой объект

| ID опции | По умолчанию | Поведение | Счётчик статистики |
|---|---|---|---|
| `root.reorder` | on | Порядок: `bomFormat`, `specVersion`, `serialNumber`, `version`, `metadata`, `components`, `annotations`, затем прочие поля в исходном относительном порядке. Отсутствующие ключи пропускаются. | 1, если порядок ключей изменился, иначе 0 |
| `root.set_spec_version` | on | Установить `specVersion` в значение из поля `spec_version` (trim). Если ключа нет — добавить; если есть — заменить значение. | 1, если значение изменилось или поле добавлено |
| `root.remove_dependencies` | on | Удалить ключ `dependencies`, если он есть. | 1, если ключ удалён |
| `root.remove_services` | on | Удалить ключ `services`, если он есть. | 1, если ключ удалён |
| `root.increment_version` | on | Если `version` — целое число (не `bool`), увеличить на 1. Если поле отсутствует или не целое — не менять; отчёт зафиксирует `root.missing_version` или `root.invalid_version`. | 1, если значение увеличено |

Примечания:

- Все правила группы по умолчанию включены; набор можно изменить и сохранить на сервере.
- Если `root.set_spec_version` добавляет отсутствующий ключ, а `root.reorder` выключен, ключ окажется в конце документа. Это допустимо: правило меняет только значение/наличие, но не порядок.
- `spec_version` валидируется как строка вида `^\d+\.\d+$`. Значения вне `1.6`/`1.7` разрешены, но попадут в отчёт как несоответствие.
- `$schema` и любые другие поля, не перечисленные в приоритете, остаются в конце в исходном относительном порядке.

### 6.3. Группа 2 — `metadata`

| ID опции | По умолчанию | Поведение | Счётчик |
|---|---|---|---|
| `metadata.add_timestamp` | on | Если `metadata.timestamp` отсутствует, `null` или пустая строка — установить текущее время UTC в формате `YYYY-MM-DDTHH:MM:SSZ`. Существующее значение не перезаписывать. | 1, если поле добавлено |
| `metadata.reorder` | on | Порядок: `timestamp`, `component`, затем прочие поля в исходном порядке. | 1/0 |
| `metadata.remove_properties` | on | Удалить `metadata.properties`, если есть. | 1/0 |
| `metadata.remove_tools` | on | Удалить `metadata.tools`, если есть (и массив, и объект). | 1/0 |
| `metadata_component.reorder` | on | Для `metadata.component`: порядок `type`, `name`, `version`, `manufacturer`, затем прочие. | 1/0 |
| `metadata_component.remove_external_references` | on | Удалить `metadata.component.externalReferences`. | 1/0 |
| `metadata_component.remove_properties` | on | Удалить `metadata.component.properties`. | 1/0 |
| `metadata_component.remove_purl` | **off** | Удалить `metadata.component.purl`. | 1/0 |
| `metadata_component.remove_scope` | on | Удалить `metadata.component.scope`. | 1/0 |
| `metadata_component.rename_supplier` | on | Если есть `supplier`: при отсутствии `manufacturer` перенести значение в `manufacturer`; если `manufacturer` уже есть — оставить его, а `supplier` удалить. | 1, если `supplier` удалён |

Примечания:

- Все правила группы по умолчанию включены, кроме `metadata_component.remove_purl`.
- `add_timestamp` срабатывает только если `timestamp` отсутствует, равен `null` или пустой строке. Существующее значение не перезаписывается, даже если его формат неверен; формат существующего значения не проверяется.
- `add_timestamp` выполняется до `metadata.reorder`, поэтому при включённом reorder `timestamp` встаёт первым.
- Поле `group` не изменяется ни в `metadata.component`, ни в компонентах.
- `metadata.component` может отсутствовать. Тогда правила `metadata_component.*` пропускаются, в отчёт добавляется `metadata.missing_component`.
- Переименование `supplier` → `manufacturer` выполняется до переупорядочивания, поэтому `manufacturer` встаёт на четвёртое место.
- `metadata.component.purl` не требуется таблицей П.3, поэтому его удаление — допустимая косметическая правка; по умолчанию она выключена.

### 6.4. Группа 3 — `components` (рекурсивно)

Обход: корневой `components` (массив) → каждый элемент-объект → его `components` (если массив) → и так далее. Порядок обхода — pre-order, в порядке массива. Обход не заходит в `metadata.component.components`: правила группы 3 относятся только к элементам корневого массива `components` и их вложенным `components`.

| ID опции | По умолчанию | Поведение | Счётчик |
|---|---|---|---|
| `components.reorder` | on | Для каждого компонента порядок: `type`, `name`, `version`, `purl`, `externalReferences`, `properties`, `components`, затем прочие. | Число компонентов, у которых порядок ключей изменился |
| `components.remove_hashes` | on | Удалить непосредственный ключ `hashes` компонента. **Не трогать** `hashes` внутри элементов `externalReferences`. | Число компонентов, у которых ключ удалён |
| `components.remove_scope` | on | Удалить непосредственный ключ `scope` компонента. | Число компонентов, у которых ключ удалён |
| `components.filter_external_references` | on | Оставить элементы массива `externalReferences`, у которых `type` — строго `vcs` или `source-distribution`. Остальные (включая не-объекты и элементы без `type`) удалить. Пустой массив сохранить. | Число удалённых элементов |
| `components.filter_properties` | on | Оставить элементы массива `properties`, у которых `name` — строка, начинающаяся ровно с `GOST:` (регистрозависимо). Остальные удалить. Пустой массив сохранить. | Число удалённых элементов |
| `components.fill_missing_gost_properties` | **off** | Для каждого компонента: если `properties` отсутствует или `null` — создать `[]`; если это не массив — не трогать (отчёт зафиксирует `component.invalid_properties`). Добавить недостающие `{"name": "GOST:attack_surface", "value": "no"}` и `{"name": "GOST:security_function", "value": "no"}`. Существующие свойства не изменять. | Число добавленных свойств |

Примечания:

- Все правила группы по умолчанию включены, кроме `fill_missing_gost_properties`.
- `fill_missing_gost_properties` применяется **после** `filter_properties`: сначала удаляются не-GOST свойства, затем добавляются недостающие GOST-свойства.
- Добавление GOST-свойств выполняется только для компонентов из `components[]`, не для `metadata.component`.
- Если `properties` — массив, но в нём есть `GOST:attack_surface` с любым значением, свойство считается присутствующим и не дублируется. Значения существующих GOST-свойств не проверяются и не исправляются.
- Если `components` отсутствует или пуст, группа 3 не даёт ошибок: по таблице П.1 массив обязателен только при наличии компонентов.

### 6.5. Крайние случаи и трактовка значений

- Входной документ не мутируется: используется `copy.deepcopy`.
- Повторный запуск с теми же опциями идемпотентен, кроме `root.increment_version` (он увеличивает `version` каждый раз); `metadata.add_timestamp` после первого запуска уже не меняет документ.
- `metadata.add_timestamp` получает время через параметр `now` (`datetime | None`). Если `now` не передан, используется `datetime.now(timezone.utc)`; naive-значение трактуется как UTC. Формат — `YYYY-MM-DDTHH:MM:SSZ`.
- Переупорядочивание — финальный проход; после него никакие правила не меняют набор или порядок ключей.
- **Issues создаются только в `_collect_issues` по итоговому документу.** Правила преобразования не создают issues. Поэтому один дефект не может попасть в отчёт несколько раз, и отдельное слияние/дедупликация не нужно.
- Если `metadata` отсутствует или `null` — правила группы 2 пропускаются; отчёт даст `root.missing_metadata`. Если `metadata` присутствует, не `null` и не объект — отчёт даст `root.invalid_metadata`.
- Если `metadata.component` отсутствует или `null` — правила `metadata_component.*` пропускаются; отчёт даст `metadata.missing_component`. Если присутствует, не `null` и не объект — `metadata.invalid_component`.
- Если `components` отсутствует или `null` — компонентов нет, ошибки нет. Если присутствует, не `null` и не массив — правила группы 3 пропускаются, отчёт даст `root.invalid_components`.
- Если элемент `components[]` не объект — он пропускается, отчёт даст `component.invalid_entry`; остальные элементы обрабатываются.
- Если `properties` / `externalReferences` / вложенный `components` имеют неожиданный тип — соответствующее правило пропускает узел; отчёт фиксирует `invalid_*`-код. Падения и 500 не происходит.
- Если `hashes` присутствует с неожиданным типом, ключ всё равно удаляется: правило сформулировано как удаление ключа, а не массива.
- `supplier: null` удаляется, `manufacturer` не создаётся; отчёт даст `metadata_component.missing_manufacturer`.
- `manufacturer: null`, `manufacturer: {}` и `manufacturer: {"name": ""}` считаются отсутствием manufacturer.

Трактовка значений при проверках:

| Ситуация | Трактовка |
|---|---|
| Ключ отсутствует или `null`, либо пустая строка для `specVersion`, `timestamp`, `type`, `name`, `purl` | «отсутствует» → `missing_*` |
| `version` присутствует, но не является целым числом (включая пустую строку) | «неверный тип» → `root.invalid_version` |
| Присутствует, не `null`, но неверный тип для `specVersion` или `version` | «неверный тип» → `invalid_*` |
| Присутствует, не `null`, но неверный тип для `timestamp`, `type`, `name`, `purl` | «отсутствует» → `missing_*` (отдельных `invalid_*` для этих полей нет) |
| Обязательный объект (`metadata`, `metadata.component`) отсутствует или `null` | «отсутствует» → `missing_*` |
| Обязательный объект присутствует, не `null`, но не объект | «неверный тип» → `invalid_*` |
| Массив `properties` / `externalReferences` отсутствует или `null` | «пустой/отсутствующий» → `missing_*` |
| Массив `properties` / `externalReferences` присутствует, не `null`, но не массив | «неверный тип» → `invalid_*` |
| Массив `components` отсутствует или `null` | компонентов нет, ошибки нет |
| Массив `components` присутствует, не `null`, но не массив | «неверный тип» → `invalid_*` |

- Ограничения на количество issues нет: отчёт должен быть полным. UI сворачивает его в спойлер и не рендерит таблицу до раскрытия, но API возвращает полный набор.

## 7. Статистика

`stats` — список объектов `{ "rule_id": string, "count": int }` в каноническом порядке правил. В список попадают **все включённые** правила, даже если `count == 0`: пользователь видит, что правило применялось, но изменений не потребовалось.

Канонический порядок:

1. `root.reorder`
2. `root.set_spec_version`
3. `root.remove_dependencies`
4. `root.remove_services`
5. `root.increment_version`
6. `metadata.add_timestamp`
7. `metadata.reorder`
8. `metadata.remove_properties`
9. `metadata.remove_tools`
10. `metadata_component.reorder`
11. `metadata_component.remove_external_references`
12. `metadata_component.remove_properties`
13. `metadata_component.remove_purl`
14. `metadata_component.remove_scope`
15. `metadata_component.rename_supplier`
16. `components.reorder`
17. `components.remove_hashes`
18. `components.remove_scope`
19. `components.filter_external_references`
20. `components.filter_properties`
21. `components.fill_missing_gost_properties`

`changed` в ответе — `true`, если хотя бы один `count > 0`.

Семантика счётчиков зафиксирована в таблицах раздела 6. Для правил удаления корневых полей счётчик равен 1 (удалён ключ), а не числу элементов массива. При значениях по умолчанию в `stats` будет 19 записей: все правила, кроме `metadata_component.remove_purl` и `components.fill_missing_gost_properties`.

## 8. Отчёт о несоответствиях

Отчёт строится **по итоговому документу** после применения выбранных правок. Он проверяет только дефекты, относящиеся к этому разделу, и не является полной проверкой по таблицам П.1–П.8.

Каждая issue:

```json
{
  "code": "component.missing_gost_properties",
  "path": "$.components[0].components[1]",
  "component": "openssl",
  "details": { "missing": ["GOST:security_function"] }
}
```

- `code` — стабильный идентификатор для i18n.
- `path` — JSON-путь до объекта (`$` — корень).
- `component` — `name` компонента, если доступен; иначе `null`.
- `details` — дополнительные данные для подстановки в перевод (обычно `field`, `missing`, `expected`).

### 8.1. Проверки корня

| Код | Условие |
|---|---|
| `root.missing_spec_version` | `specVersion` отсутствует, `null` или пустая строка |
| `root.invalid_spec_version` | `specVersion` присутствует, не `null` и не строка |
| `root.spec_version_not_allowed` | `specVersion` — строка, но не входит в `{"1.6", "1.7"}` |
| `root.missing_version` | `version` отсутствует или `null` |
| `root.invalid_version` | `version` присутствует, не `null` и не является целым числом (bool не считается) |
| `root.missing_metadata` | `metadata` отсутствует или `null` |
| `root.invalid_metadata` | `metadata` присутствует, не `null`, но не объект |
| `root.invalid_components` | `components` присутствует, не `null`, но не массив |

Коды для одного поля взаимоисключающие:

- `missing_*` — ключ отсутствует, `null` или пустая строка;
- `invalid_*` — ключ присутствует, не `null`, но имеет неверный тип;
- `not_allowed` — значение имеет правильный тип, но недопустимо по требованиям.

Для одного поля выдаётся не более одной issue из этой группы. `bomFormat` всегда равен `CycloneDX` из-за входной валидации, поэтому отдельной issue нет. `serialNumber` опционален. Отсутствие, `null` или пустота `components` не являются ошибкой.

При `root.missing_metadata` или `root.invalid_metadata` проверки `metadata.*` не выполняются, чтобы не дублировать одну причину множеством issue.

### 8.2. Проверки `metadata`

| Код | Условие |
|---|---|
| `metadata.missing_timestamp` | `timestamp` отсутствует, `null`, пустой или не строка (формат не проверяется) |
| `metadata.missing_component` | `component` отсутствует или `null` |
| `metadata.invalid_component` | `component` присутствует, не `null`, но не объект |

При включённой `metadata.add_timestamp` отсутствующий, `null` или пустой `timestamp` исправляется и в отчёт не попадает. Если `timestamp` присутствует, но не является строкой, опция его не перезаписывает — остаётся `metadata.missing_timestamp`.

Если `metadata.component` отсутствует или `null`, выдаётся `metadata.missing_component`; если присутствует, не `null` и не объект — `metadata.invalid_component`; вложенные проверки в этих случаях не выполняются.

### 8.3. Проверки `metadata.component`

Выполняются, если `metadata.component` — объект. Пустые строки и `null` считаются отсутствием.

| Код | Условие |
|---|---|
| `metadata_component.missing_type` | `type` отсутствует/пустой/не строка |
| `metadata_component.missing_name` | `name` отсутствует/пустой/не строка |
| `metadata_component.missing_version` | `version` отсутствует/пустой/не строка |
| `metadata_component.missing_manufacturer` | `manufacturer` отсутствует, не объект или не содержит непустого строкового `name` |

`purl`, `externalReferences`, `properties`, `scope` для `metadata.component` не обязательны и не проверяются.

### 8.4. Проверки компонентов

Выполняются рекурсивно для тех же компонентов, которые обходит группа 3. Для каждого компонента:

| Код | Условие |
|---|---|
| `component.invalid_entry` | элемент массива не является объектом |
| `component.missing_type` | `type` отсутствует/пустой/не строка |
| `component.missing_name` | `name` отсутствует/пустой/не строка |
| `component.missing_version` | `version` отсутствует/пустой/не строка |
| `component.missing_purl` | `purl` отсутствует/пустой/не строка |
| `component.invalid_properties` | `properties` присутствует, не `null`, но не массив; проверка GOST не выполняется |
| `component.missing_gost_properties` | `properties` отсутствует, `null` или массив, в котором нет `GOST:attack_surface` и/или `GOST:security_function`; `details.missing` — список отсутствующих имён |
| `component.invalid_external_references` | `externalReferences` присутствует, не `null`, но не массив; проверка источника не выполняется |
| `component.missing_source_reference` | `externalReferences` отсутствует, `null` или массив без элемента с `type` = `vcs` или `source-distribution`, и компонент не подпадает под исключение |
| `component.invalid_subcomponents` | вложенный `components` присутствует, не `null`, но не массив; вложенный обход не выполняется |

Исключения для `component.missing_source_reference` (по таблице П.5):

1. У компонента есть непустой массив `components` — исходный код определяется подкомпонентами.
2. В `properties` есть элемент с `name == "GOST:provided_by"` и непустым строковым `value` — компонент заимствован из сертифицированного СЗИ.
3. В `licenses` есть элемент вида `{"license": {"name": "Proprietary"}}` — компонент не является open source.

Если `externalReferences` присутствует, не `null` и не является массивом, выдаётся `component.invalid_external_references`, а `component.missing_source_reference` не дублируется. Отсутствие или `null` для `properties` / `externalReferences` трактуется при проверке как пустой массив: это даёт `missing_gost_properties` / `missing_source_reference` соответственно (если нет исключения).

Проверка наличия ссылки не валидирует URL и не проверяет хэши STREEBOG: это вне рамок раздела.

### 8.5. Порядок и объём

Порядок issue детерминирован: сначала корень, затем `metadata`, затем `metadata.component`, затем компоненты в порядке pre-order. Внутри одного объекта порядок кодов — как в таблицах выше.

## 9. API

### 9.1. `POST /api/v1/sbom/fix`

`multipart/form-data`:

- `file` — обязательный файл CycloneDX JSON.
- `options` — необязательная строка с JSON-объектом опций. Если не передана, используются встроенные значения `SbomFixOptions()`: включено всё, кроме `metadata_component.remove_purl` и `components.fill_missing_gost_properties`, `spec_version = "1.7"`. Endpoint не читает сохранённые настройки сам — страница всегда передаёт актуальный набор явно.

Максимальный размер файла — `sbom_settings.max_file_size`.

Пример `options` (значения по умолчанию):

```json
{
  "root": {
    "reorder": true,
    "set_spec_version": true,
    "spec_version": "1.7",
    "remove_dependencies": true,
    "remove_services": true,
    "increment_version": true
  },
  "metadata": {
    "add_timestamp": true,
    "reorder": true,
    "remove_properties": true,
    "remove_tools": true,
    "component": {
      "reorder": true,
      "remove_external_references": true,
      "remove_properties": true,
      "remove_purl": false,
      "remove_scope": true,
      "rename_supplier": true
    }
  },
  "components": {
    "reorder": true,
    "remove_hashes": true,
    "remove_scope": true,
    "filter_external_references": true,
    "filter_properties": true,
    "fill_missing_gost_properties": false
  }
}
```

### 9.2. Модель опций

В `sbom/fixer.py`:

```python
class RootFixOptions(BaseModel):
    reorder: bool = True
    set_spec_version: bool = True
    spec_version: str = "1.7"
    remove_dependencies: bool = True
    remove_services: bool = True
    increment_version: bool = True

class MetadataComponentFixOptions(BaseModel):
    reorder: bool = True
    remove_external_references: bool = True
    remove_properties: bool = True
    remove_purl: bool = False
    remove_scope: bool = True
    rename_supplier: bool = True

class MetadataFixOptions(BaseModel):
    add_timestamp: bool = True
    reorder: bool = True
    remove_properties: bool = True
    remove_tools: bool = True
    component: MetadataComponentFixOptions = Field(default_factory=MetadataComponentFixOptions)

class ComponentsFixOptions(BaseModel):
    reorder: bool = True
    remove_hashes: bool = True
    remove_scope: bool = True
    filter_external_references: bool = True
    filter_properties: bool = True
    fill_missing_gost_properties: bool = False

class SbomFixOptions(BaseModel):
    root: RootFixOptions = Field(default_factory=RootFixOptions)
    metadata: MetadataFixOptions = Field(default_factory=MetadataFixOptions)
    components: ComponentsFixOptions = Field(default_factory=ComponentsFixOptions)
```

`spec_version` валидируется регулярным выражением `^\d+\.\d+$` независимо от `set_spec_version`; пустая строка недопустима.

### 9.3. Хранение опций (`SbomFixOptionsStore`)

По аналогии с `IgnorePatternsStore`:

- Файл по умолчанию: `./data/sbom_fix_options.json`; конструктор принимает необязательный путь для тестов.
- `load() -> SbomFixOptions`: файла нет → `SbomFixOptions()`; битый JSON или ошибка валидации → warning в лог и `SbomFixOptions()`; частичный JSON → Pydantic заполняет отсутствующие поля значениями по умолчанию.
- `save(options) -> None`: создаёт родительский каталог, пишет JSON с `indent=2, ensure_ascii=False` и завершающим переводом строки.
- Хранится весь объект опций, включая `spec_version`. БД не требуется.
- Экземпляр создаётся в `main.py` как `app.state.sbom_fix_options_store`.

Endpoints:

| Метод | Путь | Назначение | Ответ |
|---|---|---|---|
| `GET` | `/api/v1/sbom/fix/options` | Загрузить сохранённые опции | `200 {"options": {...}}`; при ошибке чтения — значения по умолчанию, тоже 200 |
| `POST` | `/api/v1/sbom/fix/options` | Сохранить опции | `200 {"status": "saved"}` |

Тело POST: `{"options": {...}}`. Оно валидируется вручную через `SbomFixOptions.model_validate`, чтобы при ошибке вернуть `400 invalid_options`, а не стандартный 422. При ошибке записи — `500 options_save_failed`.

### 9.4. Успешный ответ (200)

```json
{
  "changed": true,
  "fixed_sbom": { "bomFormat": "CycloneDX", "...": "..." },
  "stats": [
    { "rule_id": "root.reorder", "count": 1 },
    { "rule_id": "components.remove_hashes", "count": 3 }
  ],
  "issues": [
    {
      "code": "component.missing_gost_properties",
      "path": "$.components[0]",
      "component": "openssl",
      "details": { "missing": ["GOST:security_function"] }
    }
  ]
}
```

- `changed` — были ли фактические изменения.
- `fixed_sbom` — итоговый документ (всегда возвращается, даже если изменений нет).
- `stats` — все включённые правила в каноническом порядке.
- `issues` — оставшиеся несоответствия; пустой массив, если их нет.

### 9.5. Ошибки

| Условие | HTTP | Код |
|---|---|---|
| Некорректный JSON файла | 400 | `invalid_json` |
| Корень не объект / `bomFormat` не `CycloneDX` | 400 | `invalid_sbom` (`detail` — текст `SbomParseError`) |
| `options` в fix-запросе — невалидный JSON или не проходит Pydantic-валидацию | 400 | `invalid_options` (`detail` — текст ошибки) |
| `options` в запросе сохранения невалиден | 400 | `invalid_options` (`detail` — текст ошибки) |
| Не удалось записать файл настроек | 500 | `options_save_failed` |
| Файл больше лимита | 413 | `file_too_large` (`max_size_mb`) |
| Не передан `file` | 422 | стандартная ошибка FastAPI/Pydantic |

Ошибки 400 и 413 возвращаются через `JSONResponse` с верхнеуровневым полем `error` (как в контракте), а не через `HTTPException(detail=...)`, иначе код оказался бы внутри `detail` и фронтенд не смог бы его перевести.

## 10. Frontend

### 10.1. Маршрут и навигация

- Маршрут `/fix-sbom`, имя `fix-sbom`, view `frontend/src/views/SbomFixer.vue`.
- Пункт навигации между «Обогатить SBOM» и «Генерировать список образов»: `nav.sbomFixer`.
- Плитка на домашней странице (теперь 6 плиток): namespace `sbomFixer`, ключи `title` и `subtitle`.
- Новый namespace i18n `sbomFixer` в `en.json` и `ru.json` с одинаковой структурой.

### 10.2. Компоновка страницы

1. Заголовок и подзаголовок.
2. Предупреждение: «По умолчанию включены почти все правки, включая удаление полей. Проверьте набор перед запуском».
3. `FileUploadZone` с `accept=".json"` и `:max-size="200"`.
4. Панель настроек: кнопка «Сохранить настройки», статус «Сохранено»/ошибка сохранения, кнопка «Вернуть значения по умолчанию».
5. Три карточки групп: «Корневой объект», «metadata», «components».
   - В заголовке группы — мастер-чекбокс: включён, если включены все дочерние опции; промежуточное состояние — если включена часть.
   - Мастер-чекбокс включает/выключает все дочерние опции группы. Для группы `metadata` это включает и вложенные `metadata.component.*`.
   - В группе `metadata` — подблок `metadata.component` со своим мастер-чекбоксом и кнопками; его мастер управляет только опциями `metadata_component.*` и не меняет `metadata.reorder` / `metadata.remove_*` / `metadata.add_timestamp`.
   - В группе `root` рядом с чекбоксом `set_spec_version` — текстовое поле `specVersion`, доступное только при включённом чекбоксе; по умолчанию `1.7`.
   - У каждой группы и у подблока `metadata.component` есть кнопки «Выбрать всё» и «Снять всё». «Вернуть значения по умолчанию» восстанавливает встроенные значения (всё включено, кроме `metadata_component.remove_purl` и `components.fill_missing_gost_properties`; `specVersion = "1.7"`), но не сохраняет их на сервер автоматически.
6. Кнопка «Исправить»: disabled, пока файл не выбран или идёт запрос.
7. Спиннер во время запроса.
8. Блок ошибки.
9. Результаты:
   - Статусная карточка: «Изменения внесены» / «Изменений не потребовалось».
   - Статистика: спойлер «Статистика изменений», открытый по умолчанию, с таблицей «Правило» / «Изменений». Показываются все включённые правила, включая нулевые (не более 21 строки).
   - Несоответствия: если массив пуст — зелёная карточка «Несоответствий не осталось»; иначе карточка с количеством и спойлер «Показать несоответствия (N)», закрытый по умолчанию. Таблица внутри спойлера рендерится только при раскрытии (`v-if`) и имеет ограниченную высоту с вертикальной прокруткой.
   - Кнопка «Скачать исправленный SBOM».
10. Скачивание: `downloadJson(fixed_sbom, <имя без .json> + '_fixed.json', store.jsonIndent)`.

### 10.3. Состояние и поведение

- При монтировании страница параллельно загружает сохранённые опции (`GET /api/v1/sbom/fix/options`) и настройки приложения (`useSettingsStore().load()` для `json_indent`).
- Если запрос `GET /options` завершился ошибкой (сеть/500), используются встроенные значения по умолчанию и показывается некритичное предупреждение; страница остаётся работоспособной. Повреждённый файл на сервере обрабатывается внутри store: возвращаются значения по умолчанию с записью warning в лог, клиент получает 200.
- Ошибка загрузки настроек приложения не блокирует страницу: для скачивания используется `jsonIndent = 4`.
- Опции хранятся в локальном `reactive`-объекте, повторяющем `SbomFixOptions`, и заполняются из ответа `GET /options`. На первом запуске без сохранённого файла действуют встроенные значения по умолчанию.
- Текущий набор из формы используется для запуска сразу, независимо от сохранения. «Сохранить настройки» записывает его на сервер для следующих визитов; статус сохранения показывается рядом с кнопкой.
- При новом выборе файла результаты и ошибки сбрасываются; опции не сбрасываются.
- Ошибки API переводятся через `t('errors.' + e.error, e.data)`; сетевые — `errors.network_error`; прочие — `errors.unexpected_error`.
- Новые ключи ошибок `errors.invalid_options` и `errors.options_save_failed` в обоих локалях.
- Все подписи правил и кодов issue — через i18n; коды не показываются пользователю как есть, кроме случая отсутствующего перевода (fallback на код).
- Детали issue форматируются из `details` (например, список отсутствующих GOST-свойств через запятую); длинные значения обрезаются CSS с полным значением в `title`.
- Спойлер статистики открыт по умолчанию, но может быть свёрнут.
- Спойлер несоответствий закрыт по умолчанию и не рендерит таблицу, пока его не откроют; это защищает страницу от большого DOM при тысячах issues.

### 10.4. API-клиент и типы

- `frontend/src/api/sbom.ts`: функции `fixSbom(file, options)` (FormData с полями `file` и `options` — JSON-строка), `getFixOptions()` (`GET /api/v1/sbom/fix/options`), `saveFixOptions(options)` (`POST /api/v1/sbom/fix/options`).
- `frontend/src/types/api.ts`: интерфейсы `SbomFixOptions` (вложенные), `SbomFixStat`, `SbomFixIssue`, `SbomFixResponse`, `SbomFixOptionsResponse`.

## 11. Архитектура и файлы

### 11.1. Размещение слоёв

```
HTTP Client (Browser)
    |
    | POST /api/v1/sbom/fix (multipart: file + options JSON)
    v
API Layer (routes/sbom_fix.py) -----> CycloneDXParser
    |                         |        (sbom/parser.py)
    |                         | GET/POST /api/v1/sbom/fix/options
    v                         v
SBOM Module             SbomFixOptionsStore
(sbom/fixer.py)         (sbom_fix_options_store.py)
    |                         |
    v                         v
Pydantic + stdlib       ./data/sbom_fix_options.json
```

`sbom/fixer.py` не импортирует Storage, Resolver, БД, API-схемы и `CycloneDXParser`: входной SBOM валидируется в API-слое (`routes/sbom_fix.py` через `CycloneDXParser`), а сам `fixer.py` зависит только от Pydantic и стандартной библиотеки. `SbomFixOptionsStore` импортирует `SbomFixOptions` из `sbom/fixer.py` и отвечает только за JSON-персистентность; экземпляр создаётся в `main.py` как `app.state.sbom_fix_options_store`.

### 11.2. Файлы

| Файл | Изменение |
|---|---|
| `src/purl_resolver/sbom/fixer.py` | **NEW** — модель опций, правила, статистика, issues |
| `src/purl_resolver/sbom/__init__.py` | **EDIT** — экспорт `fix_sbom`, `SbomFixOptions`, `SbomFixResult`, `FixStat`, `FixIssue` |
| `src/purl_resolver/sbom_fix_options_store.py` | **NEW** — JSON-хранилище опций (`SbomFixOptionsStore`) |
| `src/purl_resolver/routes/sbom_fix.py` | **NEW** — `POST /api/v1/sbom/fix`, `GET/POST /api/v1/sbom/fix/options` |
| `src/purl_resolver/router.py` | **EDIT** — подключить `sbom_fix_router` |
| `src/purl_resolver/main.py` | **EDIT** — создать `app.state.sbom_fix_options_store` |
| `frontend/src/views/SbomFixer.vue` | **NEW** — страница |
| `frontend/src/views/SbomFixer.test.ts` | **NEW** — тесты страницы |
| `frontend/src/api/sbom.ts` | **EDIT** — `fixSbom`, `getFixOptions`, `saveFixOptions` |
| `frontend/src/types/api.ts` | **EDIT** — типы опций, статистики, issues, ответов |
| `frontend/src/router/index.ts` | **EDIT** — маршрут `/fix-sbom` |
| `frontend/src/components/AppNav.vue` | **EDIT** — пункт навигации |
| `frontend/src/views/HomePage.vue` | **EDIT** — плитка |
| `frontend/src/views/HomePage.test.ts` | **EDIT** — 6 плиток, новые маршруты |
| `frontend/src/i18n/locales/en.json` | **EDIT** — namespace `sbomFixer`, `nav.sbomFixer`, `errors.invalid_options`, `errors.options_save_failed` |
| `frontend/src/i18n/locales/ru.json` | **EDIT** — то же |
| `tests/test_sbom_fixer.py` | **NEW** — unit-тесты модуля |
| `tests/test_sbom_fix_options_store.py` | **NEW** — тесты хранилища опций |
| `tests/test_sbom_fix_api.py` | **NEW** — тесты endpoint |
| `specs/domains/sbom-fixing.md` | **NEW** — доменная спека |
| `specs/META.md`, `specs/INDEX.md`, `specs/domains/web-ui.md`, `specs/contracts/api-contract.md`, `specs/architecture/layers.md` | **EDIT** — см. раздел 13 |

### 11.3. Внутреннее устройство `fixer.py`

Рекомендуемая структура (имена могут быть уточнены исполнителем, поведение — нет):

- `_walk_components(root, callback)` — рекурсивный pre-order обход; вызывает callback для каждого компонента-объекта; при неожиданном типе просто останавливает ветку (issue сформирует `_collect_issues`).
- `_reorder(obj, priority) -> tuple[dict, bool]` — новый dict с приоритетными ключами впереди, остальные в исходном порядке; возвращает также флаг изменения порядка.
- Отдельная функция на каждое правило, принимающая документ/узел и возвращающая **только счётчик**. Правила не создают issues.
- `_collect_issues(data) -> list[FixIssue]` — **единственный источник issues**; выполняет все проверки по итоговому документу. Дедупликация не нужна, потому что правила issues не порождают.
- `_add_timestamp(metadata: dict, now: datetime) -> int` — добавляет `timestamp`, если он отсутствует/`null`/пустой; возвращает 1/0.
- `fix_sbom(data: dict, options: SbomFixOptions, now: datetime | None = None) -> SbomFixResult` — оркестратор; `now` нужен для тестируемости, в production не передаётся.
- Переупорядочивание вызывается отдельным финальным проходом после всех мутаций.

Статистика собирается в список в каноническом порядке; выключенные правила в список не попадают.

## 12. Тестирование

### 12.1. Backend unit (`tests/test_sbom_fixer.py`)

- Значения по умолчанию: все правила `True`, кроме `metadata_component.remove_purl` и `components.fill_missing_gost_properties`; `spec_version = "1.7"`.
- Переупорядочивание корня: все поля, часть полей, прочие поля сохраняют относительный порядок, `$schema` уходит в конец.
- Переупорядочивание выполняется последним: при одновременно включённых `add_timestamp`, `rename_supplier`, фильтрах и reorder итоговый порядок соответствует приоритетам, а `timestamp` стоит первым в `metadata`.
- `specVersion`: существующее значение, добавление отсутствующего, значение вне 1.6/1.7 даёт issue.
- Удаление `dependencies`/`services`, в том числе пустых массивов.
- `version`: инкремент целого; отсутствие/строка/bool не меняются и дают issue.
- `metadata.add_timestamp`: отсутствие/`null`/пустая строка → фиксированное время из `now`; существующее значение не перезаписывается; при отсутствии `metadata` timestamp не добавляется; naive `now` трактуется как UTC.
- `metadata`: переупорядочивание, удаление `properties`/`tools`, отсутствие `metadata`.
- `metadata.component`: все удаления, переупорядочивание, `supplier` → `manufacturer`, оба ключа одновременно, отсутствие компонента.
- `group` не меняется нигде.
- Рекурсивная обработка `components` на 3+ уровнях вложенности.
- `hashes`: удаляется только непосредственный ключ; вложенный `externalReferences[].hashes` сохраняется.
- `scope` удаляется на всех уровнях.
- Фильтрация `externalReferences`: `vcs`, `source-distribution`, прочие, отсутствие `type`, не-объекты; пустой массив сохраняется.
- Фильтрация `properties`: `GOST:` в верхнем регистре, `gost:` в нижнем, нестроковый `name`, пустой массив.
- Заполнение GOST: создание массива, добавление только недостающих, сохранение существующих значений, неприменение к `metadata.component`, порядок «фильтр → добавление».
- Статистика: точные счётчики по каждому правилу; включённые правила с нулём присутствуют; `changed`.
- Issues: все коды из раздела 8; исключения для `missing_source_reference` (подкомпоненты, `GOST:provided_by`, `Proprietary`); отсутствие каскадных дублей.
- Отсутствие/`null` для `properties` и `externalReferences` даёт `missing_gost_properties` / `missing_source_reference`; присутствие не-массива (не `null`) — `invalid_properties` / `invalid_external_references`.
- Для одного поля корня выдаётся не более одной issue: `missing_*` / `invalid_*` / `not_allowed` взаимоисключающие.
- `supplier: null` удаляется без создания `manufacturer`; `manufacturer: null` / `{}` / пустой `name` считается отсутствием.
- Идемпотентность повторного запуска (кроме инкремента версии); повторный `add_timestamp` ничего не меняет.
- Входной документ не мутируется.
- Некорректные типы полей не вызывают исключений.

### 12.2. Хранилище опций (`tests/test_sbom_fix_options_store.py`)

- Файла нет → `load()` возвращает значения по умолчанию.
- `save()` → `load()` возвращает тот же набор (roundtrip), включая `spec_version`.
- Битый JSON → значения по умолчанию, без исключения.
- Невалидный `spec_version` в файле → значения по умолчанию.
- Частичный JSON → отсутствующие поля заполняются значениями по умолчанию.
- Переданный в конструктор путь используется вместо `./data/sbom_fix_options.json`.

### 12.3. API (`tests/test_sbom_fix_api.py`)

- 200 с корректным файлом и опциями; проверка формы `changed`/`fixed_sbom`/`stats`/`issues`.
- `options` не передан → применяются встроенные значения по умолчанию (включено всё, кроме двух правил), а не режим проверки.
- 400 `invalid_json`.
- 400 `invalid_sbom`.
- 400 `invalid_options` (невалидный JSON опций и невалидный `spec_version`).
- 413 `file_too_large` (через monkeypatch лимита).
- 422 без файла.
- `GET /api/v1/sbom/fix/options` → 200 с сохранёнными или дефолтными опциями.
- `POST /api/v1/sbom/fix/options` → 200, сохраняет набор; последующий GET возвращает его.
- `POST /api/v1/sbom/fix/options` с невалидными опциями → 400 `invalid_options`.
- Ошибка записи хранилища → 500 `options_save_failed` (через monkeypatch).

### 12.4. Frontend (`frontend/src/views/SbomFixer.test.ts`)

- На монтировании вызывается `getFixOptions`; полученные опции заполняют форму. На первом запуске без сохранений — все опции включены, кроме `remove_purl` и `fill_missing_gost_properties`; `specVersion = "1.7"`.
- Мастер-чекбокс включает/выключает дочерние опции; мастер `metadata` включает и вложенные `metadata.component.*`, а мастер подблока не меняет родительские опции.
- Кнопки «Выбрать всё»/«Снять всё»; «Вернуть значения по умолчанию» восстанавливает встроенный набор и `specVersion = "1.7"`.
- «Сохранить настройки» вызывает `saveFixOptions` с текущим набором; показывается «Сохранено»; ошибка сохранения отображается.
- Ошибка загрузки сохранённых опций не блокирует страницу: используются значения по умолчанию и показывается предупреждение.
- Ошибка загрузки настроек приложения не блокирует страницу; для скачивания используется `jsonIndent = 4`.
- `specVersion` доступно только при включённой опции.
- Кнопка «Исправить» disabled без файла.
- Успешный вызов: `fixSbom` получает правильные опции; отображаются статистика, issues, статус.
- Статистика отображается в открытом по умолчанию спойлере; несоответствия — в закрытом по умолчанию; таблица issues не рендерится до раскрытия.
- Пустой `issues` — зелёная карточка, спойлера нет.
- Скачивание: имя `*_fixed.json`, отступ из store.
- `ApiError` (`invalid_options`, `invalid_sbom`, `options_save_failed`) и сетевая ошибка.

### 12.5. Команды

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check src tests
npm test --prefix frontend
npm run build --prefix frontend
```

## 13. Обновление project specs

- **NEW** `specs/domains/sbom-fixing.md` — назначение, правила, значения по умолчанию, хранение опций, статистика, issue-коды, API-поведение, инварианты.
- `specs/META.md` — добавить новый домен в File Organization.
- `specs/INDEX.md` — строка task-to-spec и новый файл в Directory Listing.
- `specs/domains/web-ui.md` — «пять» → «шесть» страниц; новый view/API-клиент/типы/маршрут/навигация/плитка; загрузка/сохранение опций; спойлер отчёта; flow; инварианты; тесты.
- `specs/contracts/api-contract.md` — `POST /api/v1/sbom/fix`, `GET/POST /api/v1/sbom/fix/options`, коды ошибок, SPA-маршрут `/fix-sbom`.
- `specs/architecture/layers.md` — `sbom/fixer.py`, `sbom_fix_options_store.py`, `routes/sbom_fix.py`, import rules, responsibilities, список маршрутов.
- ADR не требуется: выбор синхронного преобразования зафиксирован в этом дизайне и в `layers.md`.

## 14. Что оставлено исполнителю

- Точная визуальная компоновка карточек и таблиц (в рамках существующих CSS-переменных и классов).
- Формулировки подписей, подсказок и сообщений в en/ru (смысл и ключи зафиксированы).
- Разбиение `fixer.py` на приватные функции и их имена.
- Точные тексты Pydantic-ошибок для `invalid_options`.
- Набор тестовых фикстур и вспомогательных билдеров SBOM.
- Нужно ли выделять общий рекурсивный обходчик компонентов с `images_list_converter.py`. Рекомендация: не рефакторить существующий модуль в рамках этой задачи, реализовать локальный обход в `fixer.py`.
- Точная реализация спойлера и ограничения высоты таблицы issues (API всё равно возвращает всё).

## 15. Риски и компромиссы

- По умолчанию включены почти все правила, включая удаление `dependencies`, `services`, `hashes` и `scope`, а также повышение `version` и смену `specVersion`. Это осознанное требование; для защиты от случайного запуска в UI показывается предупреждение, а статистика перечисляет все изменения. Пользователь может снять правила и сохранить свой набор.
- Сохранённые настройки могут устареть при добавлении новых правил. Pydantic заполняет отсутствующие поля значениями по умолчанию; при повреждённом файле используются встроенные значения, а пользователь видит предупреждение.
- Повышение `specVersion` без преобразования содержимого может быть семантически неоднозначным, хотя схемы 1.6/1.7 всё ещё принимают legacy-формы `tools` и `supplier`. Отчёт предупреждает, если версия вне `1.6`/`1.7`.
- Переупорядочивание полей — косметическая операция, не влияющая на семантику JSON.
- `metadata.timestamp` при добавлении использует текущее время, поэтому результат не побайтово детерминирован между запусками; для тестов время передаётся параметром `now`.
- Отчёт не равен полной проверке ФСТЭК; UI должен называть его отчётом по правилам раздела, чтобы не создавать ложного впечатления полной сертификационной проверки.
- Для очень больших SBOM ответ содержит полный документ и полный список issues; это может быть объёмным. UI сворачивает отчёт в спойлер и не рендерит таблицу до раскрытия, но API всё равно возвращает полный набор.
- Сохранение опций явное (кнопка), а не автоматическое: изменения в форме действуют на текущий запуск, но не становятся сохранёнными до нажатия «Сохранить настройки».
