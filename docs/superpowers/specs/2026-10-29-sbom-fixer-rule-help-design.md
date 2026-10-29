# «Исправить SBOM» — встроенная справка по правилам: дизайн

## 1. Задача и зачем

Раздел «Исправить SBOM» содержит 21 правило, включаемое чекбоксами. Сейчас пользователь видит только короткое название правила и должен сам догадываться, что именно и в каких границах оно меняет. Нужно, чтобы рядом с каждым правилом была справка: что правило делает, чего оно не трогает и как выглядит результат на фрагменте SBOM «до → после».

Дополнительно убирается предупреждающая плашка «По умолчанию включены почти все правки, включая удаление полей. Проверьте набор перед запуском»: аудитория раздела знает, зачем он нужен, и плашка только занимает место.

## 2. Цели и не-цели

### Цели

- Убрать плашку `sbomFixer.warning` из шапки страницы (и её ключи в ru/en, и CSS).
- У каждого из 21 правила — значок «(i)», открывающий встроенную справку.
- Справка содержит: краткое описание поведения и ограничений правила, пример «До» и «После» на фрагменте CycloneDX JSON.
- Справка доступна с клавиатуры, работает без наведения мыши (тач-экраны), не обрезается границами карточек.
- Убрать тройное дублирование списка правил (шаблон, массивы ключей, `defaultFixOptions()`), введя единый каталог правил.
- Тексты — в ru/en локалях; JSON-примеры — одни на оба языка.
- Покрыть поведение тестами и обновить спецификации.

### Не-цели

- Изменения backend, API, моделей опций и самих правил.
- Подсветка синтаксиса JSON в примерах.
- Поиск/фильтрация по справке, отдельная страница документации.
- Всплывающие подсказки по наведению (см. «Подходы»).
- Помощь для мастер-чекбоксов групп (только для отдельных правил).

## 3. Подходы

Рассматривались три способа показа справки.

- **A. Встроенная раскрывающаяся панель под строкой правила (выбран).** Клик по «(i)» раскрывает панель внутри карточки группы: описание, ниже блоки «До» и «После». Ничего не позиционируется и не обрезается, работает на тач-экранах и с клавиатуры. Цена — раскрытие сдвигает строки вниз, что предсказуемо.
- **B. Всплывающий поповер у значка.** Не сдвигает вёрстку, но требует расчёта позиции и переворота у краёв, обрезается внутри карточек с прокруткой, на узких экранах всё равно превращается в панель. Существующий CSS-тултип `SbomUpdater.vue` (`data-tooltip`, одна строка) для длинного текста и кода не годится.
- **C. Боковая панель справки.** Избыточна для 21 короткого правила, теряет связь «значок — текст».

Вариант A выбран пользователем.

## 4. Архитектура решения

### 4.1 Каталог правил

Новый модуль `frontend/src/views/sbomFixerRules.ts` — единственный источник списка правил для страницы.

```ts
export interface FixRuleExample {
  readonly before: string
  readonly after: string
}

export interface FixRule<K extends string> {
  readonly id: string        // совпадает с rule_id из stats и data-rule
  readonly key: K            // ключ булевой опции в своей группе
  readonly example: FixRuleExample
}

type RootBooleanKey = Exclude<keyof RootFixOptions, 'spec_version'>

export const ROOT_RULES: readonly FixRule<RootBooleanKey>[] = [...]
export const METADATA_RULES: readonly FixRule<Exclude<keyof MetadataFixOptions, 'component'>>[] = [...]
export const METADATA_COMPONENT_RULES: readonly FixRule<keyof MetadataComponentFixOptions>[] = [...]
export const COMPONENTS_RULES: readonly FixRule<keyof ComponentsFixOptions>[] = [...]
export const ALL_FIX_RULES = [...ROOT_RULES, ...METADATA_RULES, ...METADATA_COMPONENT_RULES, ...COMPONENTS_RULES]
```

Ключи локали выводятся из `id`: `sbomFixer.rules.${id}` (уже используется для статистики) и `sbomFixer.help.${id}`. Благодаря вложенной структуре локалей это даёт `sbomFixer.help.metadata_component.rename_supplier`.

Порядок правил в массивах задаёт порядок строк в UI, а не порядок применения и не порядок статистики (их определяет backend-константа `RULE_IDS`). В частности, в `METADATA_RULES` правило `metadata.reorder` идёт первым — как «Упорядочить поля» в остальных подразделах, — далее `add_timestamp`, `remove_properties`, `remove_tools`. В таблице статистики порядок остаётся прежним (по `RULE_IDS`).

Страница перестаёт хранить массивы `rootKeys`, `metadataKeys`, `metadataComponentKeys`, `componentKeys` и дублирующую разметку 21 строки: каждая карточка рендерит свои правила через `v-for="rule in ROOT_RULES"` и т. п. Мастер-чекбоксы и их `indeterminate` считаются по тем же массивам. `defaultFixOptions()` остаётся единственным описанием значений по умолчанию (типы `SbomFixOptions` уже это гарантируют).

### 4.2 Компонент справки

Новый презентационный компонент `frontend/src/components/RuleHelp.vue`.

```
props: {
  description: string
  before: string
  after: string
  beforeLabel: string
  afterLabel: string
  ruleTitle: string      // для aria-label области
  open: boolean
}
emits: toggle, close
```

- Состояние открытия контролирует родитель; компонент ничего не хранит (кроме id из `useId()` для `aria-controls` / `aria-labelledby`).
- Кнопка: `<button type="button" class="rule-help-button" :aria-expanded="open" :aria-controls="panelId">i</button>`; клик эмитит `toggle`.
- Панель: `v-if="open"`, `:id="panelId"`, `role="region"`, `:aria-labelledby="buttonId"`; внутри `<p class="rule-help-description">`, затем два блока `.rule-example` с подписями и `<pre><code>`.
- `@keydown.esc` на корне компонента эмитит `close`.
- На узком экране примеры идут друг под другом, на широком — в две колонки (`grid`, `@media`).
- JSON вставляется как текст (`{{ }}`), без `v-html`; переносы внутри `<pre>`.

Состояние «открыта одна панель за раз» держит страница: `const openHelpId = ref<string | null>(null)`, `toggleHelp(id)` ставит `id` или `null`, `closeHelp()` ставит `null`.

### 4.3 Разметка строки правила

Текущая строка — `<label class="rule-row">`, внутри чекбокс, название и (для `set_spec_version`) текстовый инпут. Кнопку «(i)» нельзя класть внутрь `<label>`, иначе её клик переключит чекбокс. Строка становится `<div class="rule-row">`:

```
<div class="rule-row" :data-rule-row="rule.id">
  <label class="rule-label">
    <input v-model="options.root[rule.key]" type="checkbox" :data-rule="rule.id" />
    <span>{{ t(`sbomFixer.rules.${rule.id}`) }}</span>
  </label>
  [spec-version label + input — только для root.set_spec_version, вне label]
  <RuleHelp ... />
  <div v-if="openHelpId === rule.id" class="rule-help-slot"> ... </div>
</div>
```

`data-rule` остаётся на инпуте — существующие тесты и селекторы не ломаются. Побочный полезный эффект: клик по полю «Версия спецификации» больше не переключает чекбокс правила.

## 5. Содержимое справки

Тексты — короткие (1–3 предложения), только поведение правила и его границы; без пересказа методики ФСТЭК. В описаниях явно указано, когда правило не срабатывает (нецелый `version`, существующий `timestamp`, уже заданный `manufacturer`) и что оно не трогает (`metadata.component` для правил `components.*`, хеши внутри `externalReferences`).

Полные тексты на русском и примеры — в приложении A. Английские тексты — смысловой перевод, примеры общие.

## 6. Тестирование

- `frontend/src/components/RuleHelp.test.ts`: закрытая панель не рендерится; открытая показывает описание, «До» и «После»; клик эмитит `toggle`; `Escape` эмитит `close`; `aria-expanded`/`aria-controls` согласованы.
- `frontend/src/views/sbomFixerRules.test.ts`: ровно 21 правило, `id` уникальны; каждый пример — валидный JSON (`JSON.parse`) с непустыми `before`/`after`; для каждого `id` есть непустые `sbomFixer.help.*` и `sbomFixer.rules.*` в ru и en (проверка по импортированным JSON локалей); ключ `sbomFixer.warning` отсутствует в обеих локалях.
- `frontend/src/views/SbomFixer.test.ts`:
  - тест про плашку заменяется тестом «плашки нет, у каждого правила есть кнопка справки»;
  - тест «settings fail не блокирует страницу» перестаёт опираться на `.warning-banner`;
  - новые тесты: клик открывает описание и оба примера; повторный клик закрывает; открытие другой справки закрывает предыдущую; клик по «(i)» не меняет чекбокс; `Escape` закрывает; мастер-чекбоксы и сохранение работают как раньше (существующие тесты).
- Команды: `cd frontend && npm test` и `cd frontend && npm run build` (`vue-tsc`).

Backend не меняется; pytest не требуется.

## 7. Документация

- `specs/domains/web-ui.md`: убрать пункт про плашку, добавить описание справки и новые файлы (`RuleHelp.vue`, `sbomFixerRules.ts`).
- `specs/domains/sbom-fixing.md`: добавить новые frontend-файлы в Key Files и одну строку о том, что каждое правило документировано в UI примером «до/после».
- `specs/contracts/api-contract.md`: без изменений.
- Этот документ лежит в `docs/superpowers/`, который в репозитории в `.gitignore` (как и предыдущие дизайн-документы).

## 8. Что остаётся на усмотрение исполнителя

- Точные формулировки английских текстов (смысл зафиксирован русскими).
- CSS-оформление панели в рамках существующих переменных темы (`--color-card-bg`, `--color-row-border`, `--color-muted`).
- Порядок блоков в ширине < 640px (примеры друг под другом).

---

## Приложение A. Тексты и примеры (ru)

Иллюстративный `timestamp` в примерах — `2026-10-29T12:00:00Z`; фактическое значение — текущее время UTC.

### root.reorder

**Упорядочить поля корня.** Приводит ключи корневого объекта к порядку `bomFormat`, `specVersion`, `serialNumber`, `version`, `metadata`, `components`, `annotations`; остальные ключи остаются после них в исходном относительном порядке. Вложенные объекты не меняет.

До:
```json
{
  "components": [],
  "version": 3,
  "bomFormat": "CycloneDX",
  "specVersion": "1.7"
}
```
После:
```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.7",
  "version": 3,
  "components": []
}
```

### root.set_spec_version

**Установить specVersion.** Записывает в `specVersion` значение из поля «Версия спецификации» (по умолчанию `1.7`), обрезая пробелы; если поля не было — добавляет его. Значение вне `1.6`/`1.7` установить можно, но итоговый документ получит несоответствие.

До:
```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5"
}
```
После:
```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.7"
}
```

### root.remove_dependencies

**Удалить dependencies.** Удаляет корневой массив `dependencies` целиком. Сами компоненты и их вложенные поля не меняются.

До:
```json
{
  "bomFormat": "CycloneDX",
  "dependencies": [
    { "ref": "pkg:npm/left-pad@1.3.0" }
  ]
}
```
После:
```json
{
  "bomFormat": "CycloneDX"
}
```

### root.remove_services

**Удалить services.** Удаляет корневой массив `services` целиком. Компоненты не меняются.

До:
```json
{
  "bomFormat": "CycloneDX",
  "services": [
    { "name": "auth-api", "version": "1.0.0" }
  ]
}
```
После:
```json
{
  "bomFormat": "CycloneDX"
}
```

### root.increment_version

**Увеличить version.** Увеличивает целочисленное поле `version` на 1. Если `version` отсутствует или не является целым числом, правило его не трогает и сообщает `0` изменений.

До:
```json
{
  "bomFormat": "CycloneDX",
  "version": 3
}
```
После:
```json
{
  "bomFormat": "CycloneDX",
  "version": 4
}
```

### metadata.add_timestamp

**Добавить timestamp, если отсутствует.** Записывает `metadata.timestamp` с текущим временем UTC в формате `YYYY-MM-DDTHH:MM:SSZ`, только если поле отсутствует, равно `null` или пустой строке. Существующее непустое значение не перезаписывается.

До:
```json
{
  "metadata": {
    "component": { "type": "application", "name": "app", "version": "1.0.0" }
  }
}
```
После:
```json
{
  "metadata": {
    "timestamp": "2026-10-29T12:00:00Z",
    "component": { "type": "application", "name": "app", "version": "1.0.0" }
  }
}
```

### metadata.reorder

**Упорядочить поля metadata.** Ставит `timestamp` и `component` в начало, остальные ключи `metadata` идут после них в исходном порядке. Содержимое не меняется.

До:
```json
{
  "metadata": {
    "component": { "name": "app" },
    "timestamp": "2026-10-29T12:00:00Z"
  }
}
```
После:
```json
{
  "metadata": {
    "timestamp": "2026-10-29T12:00:00Z",
    "component": { "name": "app" }
  }
}
```

### metadata.remove_properties

**Удалить metadata.properties.** Удаляет свойства самого документа (`metadata.properties`). Свойства компонентов этим правилом не затрагиваются.

До:
```json
{
  "metadata": {
    "timestamp": "2026-10-29T12:00:00Z",
    "properties": [
      { "name": "GOST:attack_surface", "value": "no" }
    ]
  }
}
```
После:
```json
{
  "metadata": {
    "timestamp": "2026-10-29T12:00:00Z"
  }
}
```

### metadata.remove_tools

**Удалить metadata.tools.** Удаляет `metadata.tools` в любой форме — и массив, и объект.

До:
```json
{
  "metadata": {
    "timestamp": "2026-10-29T12:00:00Z",
    "tools": [
      { "vendor": "Acme", "name": "sbom-generator" }
    ]
  }
}
```
После:
```json
{
  "metadata": {
    "timestamp": "2026-10-29T12:00:00Z"
  }
}
```

### metadata_component.reorder

**Упорядочить поля metadata.component.** Ставит `type`, `name`, `version`, `manufacturer`, затем остальные ключи в исходном порядке.

До:
```json
{
  "metadata": {
    "component": {
      "manufacturer": { "name": "ООО Ромашка" },
      "version": "1.0.0",
      "type": "application",
      "name": "app"
    }
  }
}
```
После:
```json
{
  "metadata": {
    "component": {
      "type": "application",
      "name": "app",
      "version": "1.0.0",
      "manufacturer": { "name": "ООО Ромашка" }
    }
  }
}
```

### metadata_component.remove_external_references

**Удалить externalReferences.** Удаляет `metadata.component.externalReferences` целиком. Внешние ссылки компонентов в `components[]` этим правилом не затрагиваются.

До:
```json
{
  "metadata": {
    "component": {
      "name": "app",
      "externalReferences": [
        { "type": "vcs", "url": "https://github.com/acme/app" }
      ]
    }
  }
}
```
После:
```json
{
  "metadata": {
    "component": {
      "name": "app"
    }
  }
}
```

### metadata_component.remove_properties

**Удалить properties.** Удаляет `metadata.component.properties`. Свойства компонентов в `components[]` этим правилом не затрагиваются.

До:
```json
{
  "metadata": {
    "component": {
      "name": "app",
      "properties": [
        { "name": "GOST:security_function", "value": "no" }
      ]
    }
  }
}
```
После:
```json
{
  "metadata": {
    "component": {
      "name": "app"
    }
  }
}
```

### metadata_component.remove_purl

**Удалить purl.** Удаляет `purl` только у `metadata.component`. `purl` компонентов в `components[]` сохраняются.

До:
```json
{
  "metadata": {
    "component": {
      "type": "application",
      "name": "app",
      "purl": "pkg:generic/app@1.0.0"
    }
  }
}
```
После:
```json
{
  "metadata": {
    "component": {
      "type": "application",
      "name": "app"
    }
  }
}
```

### metadata_component.remove_scope

**Удалить scope.** Удаляет `scope` только у `metadata.component`. `scope` компонентов в `components[]` обрабатывается отдельным правилом.

До:
```json
{
  "metadata": {
    "component": {
      "name": "app",
      "scope": "required"
    }
  }
}
```
После:
```json
{
  "metadata": {
    "component": {
      "name": "app"
    }
  }
}
```

### metadata_component.rename_supplier

**Переименовать supplier в manufacturer.** Удаляет `supplier` и переносит его значение в `manufacturer`, только если `manufacturer` отсутствует или равен `null`. Если `manufacturer` уже задан, `supplier` просто удаляется.

До:
```json
{
  "metadata": {
    "component": {
      "type": "application",
      "name": "app",
      "supplier": { "name": "ООО Ромашка" }
    }
  }
}
```
После:
```json
{
  "metadata": {
    "component": {
      "type": "application",
      "name": "app",
      "manufacturer": { "name": "ООО Ромашка" }
    }
  }
}
```

### components.reorder

**Упорядочить поля компонентов.** У каждого компонента ставит ключи в порядок `type`, `name`, `version`, `purl`, `externalReferences`, `properties`, `components`, затем остальные в исходном порядке. Применяется рекурсивно ко вложенным `components`. `metadata.component` не затрагивается.

До:
```json
{
  "components": [
    {
      "properties": [],
      "purl": "pkg:npm/left-pad@1.3.0",
      "name": "left-pad",
      "type": "library",
      "version": "1.3.0"
    }
  ]
}
```
После:
```json
{
  "components": [
    {
      "type": "library",
      "name": "left-pad",
      "version": "1.3.0",
      "purl": "pkg:npm/left-pad@1.3.0",
      "properties": []
    }
  ]
}
```

### components.remove_hashes

**Удалить hashes.** Удаляет у компонента его собственное поле `hashes`. Хеши внутри `externalReferences` (например, у ссылки на дистрибутив) сохраняются.

До:
```json
{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0",
      "hashes": [
        { "alg": "SHA-256", "content": "9f86d081884c7d659a2feaa0c55ad015" }
      ]
    }
  ]
}
```
После:
```json
{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0"
    }
  ]
}
```

### components.remove_scope

**Удалить scope.** Удаляет поле `scope` у каждого компонента в `components[]`, рекурсивно. `metadata.component.scope` обрабатывается отдельным правилом.

До:
```json
{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0",
      "scope": "required"
    }
  ]
}
```
После:
```json
{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0"
    }
  ]
}
```

### components.filter_external_references

**Оставить только VCS и source-distribution ссылки.** Оставляет в `externalReferences` только элементы с `type` ровно `vcs` или `source-distribution` (с учётом регистра). Остальные типы (`website`, `distribution`, `issue-tracker` и т. п.) удаляются; если не осталось ничего, массив остаётся пустым. `metadata.component` не затрагивается.

До:
```json
{
  "components": [
    {
      "type": "library",
      "name": "left-pad",
      "version": "1.3.0",
      "externalReferences": [
        { "type": "vcs", "url": "https://github.com/stevemao/left-pad" },
        { "type": "website", "url": "https://example.com/left-pad" },
        { "type": "source-distribution", "url": "https://registry.npmjs.org/left-pad" }
      ]
    }
  ]
}
```
После:
```json
{
  "components": [
    {
      "type": "library",
      "name": "left-pad",
      "version": "1.3.0",
      "externalReferences": [
        { "type": "vcs", "url": "https://github.com/stevemao/left-pad" },
        { "type": "source-distribution", "url": "https://registry.npmjs.org/left-pad" }
      ]
    }
  ]
}
```

### components.filter_properties

**Оставить только GOST-свойства.** Оставляет в `properties` только элементы, имя которых начинается ровно с `GOST:` (с учётом регистра). Остальные удаляются; пустой массив остаётся пустым. `metadata.component` не затрагивается.

До:
```json
{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0",
      "properties": [
        { "name": "GOST:attack_surface", "value": "no" },
        { "name": "internal:owner", "value": "platform-team" }
      ]
    }
  ]
}
```
После:
```json
{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0",
      "properties": [
        { "name": "GOST:attack_surface", "value": "no" }
      ]
    }
  ]
}
```

### components.fill_missing_gost_properties

**Добавить недостающие ГОСТ-свойства.** Добавляет компоненту недостающие `GOST:attack_surface` и `GOST:security_function` со значением `no` в `value`. Если `properties` нет, создаёт массив; существующие свойства не меняет. `metadata.component` не затрагивается.

До:
```json
{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0",
      "properties": [
        { "name": "GOST:attack_surface", "value": "no" }
      ]
    }
  ]
}
```
После:
```json
{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0.0",
      "properties": [
        { "name": "GOST:attack_surface", "value": "no" },
        { "name": "GOST:security_function", "value": "no" }
      ]
    }
  ]
}
```
