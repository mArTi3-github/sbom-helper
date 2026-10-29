# «Исправить SBOM»: встроенная справка по правилам — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Убрать предупреждающую плашку со страницы «Исправить SBOM» и добавить каждому из 21 правила раскрывающуюся справку с описанием и примерами «до/после», переведя список правил на единый каталог.

**Architecture:** Единый TS-каталог правил (id, ключ опции, JSON-примеры) заменяет дублирующиеся массивы ключей и ручную разметку 21 строки. Презентационный компонент `RuleHelp.vue` рисует кнопку «(i)» и панель; состоянием «открыта одна панель» управляет страница. Тексты — в ru/en локалях, примеры общие.

**Tech Stack:** Vue 3.5 (`<script setup>`, `useId`), TypeScript, vue-i18n 11, Vitest 4 + @vue/test-utils 2, happy-dom.

**Spec:** `docs/superpowers/specs/2026-10-29-sbom-fixer-rule-help-design.md` (приложение A — точные тексты и примеры).

## Global Constraints

- Backend, API и модели опций не меняются; `rule_id` и `data-rule` остаются прежними.
- Любой видимый текст — только через `t()`; ключи добавляются и в `ru.json`, и в `en.json`.
- JSON-примеры хранятся один раз в TS (не дублируются в локалях) и копируются из приложения A спеки дословно.
- В `METADATA_RULES` правило `metadata.reorder` идёт первым; остальные группы тоже начинаются с `*.reorder`. Порядок статистики не меняется (его задаёт backend).
- Новые зависимости не добавляются; подсветки синтаксиса нет.
- Комментарии в коде не добавляются.
- Коммиты в план не включены: пользователь не просил коммитить. При необходимости — отдельным шагом после подтверждения.

## Review Focus

1. Клик по «(i)» не должен переключать чекбокс правила (кнопка не внутри `<label>`) — тест в Task 3.
2. Каждое правило должно иметь непустое описание в ru и en; ключ справки выводится из `id` и не должен разъезжаться — тест в Task 1.
3. Одновременно открыта только одна панель; Escape закрывает её — тесты в Task 2 и Task 3.
4. После перехода на `v-for` чекбокс должен менять именно свою опцию и попадать в сохраняемый payload — тесты в Task 3 (плюс существующие тесты мастеров и сохранения).
5. Клик по полю «Версия спецификации» не должен переключать `root.set_spec_version` — тест в Task 3.

---

### Task 1: Каталог правил и тексты справки

**Files:**
- Create: `frontend/src/views/sbomFixerRules.ts`
- Create: `frontend/src/views/sbomFixerRules.test.ts`
- Modify: `frontend/src/i18n/locales/ru.json` (секция `sbomFixer`)
- Modify: `frontend/src/i18n/locales/en.json` (секция `sbomFixer`)

**Interfaces:**
- Consumes: типы `RootFixOptions`, `MetadataFixOptions`, `MetadataComponentFixOptions`, `ComponentsFixOptions` из `frontend/src/types/api.ts`.
- Produces:
  - `interface FixRuleExample { readonly before: string; readonly after: string }`
  - `interface FixRule<K extends string> { readonly id: string; readonly key: K; readonly example: FixRuleExample }`
  - `ROOT_RULES: readonly FixRule<RootRuleKey>[]` (5), `METADATA_RULES: readonly FixRule<MetadataRuleKey>[]` (4), `METADATA_COMPONENT_RULES: readonly FixRule<MetadataComponentRuleKey>[]` (6), `COMPONENTS_RULES: readonly FixRule<ComponentsRuleKey>[]` (6)
  - `ALL_FIX_RULES: readonly FixRule<string>[]` (все 21)
  - ключи локалей: `sbomFixer.help.<id>`, `sbomFixer.exampleBefore`, `sbomFixer.exampleAfter`

- [ ] **Step 1: Написать падающий тест каталога**

Создать `frontend/src/views/sbomFixerRules.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import ru from '../i18n/locales/ru.json'
import en from '../i18n/locales/en.json'
import {
  ALL_FIX_RULES,
  COMPONENTS_RULES,
  METADATA_COMPONENT_RULES,
  METADATA_RULES,
  ROOT_RULES,
} from './sbomFixerRules'

function lookup(messages: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((acc, part) => {
    if (typeof acc !== 'object' || acc === null) return undefined
    return (acc as Record<string, unknown>)[part]
  }, messages)
}

const GROUPS = [
  { rules: ROOT_RULES, prefix: 'root.', size: 5 },
  { rules: METADATA_RULES, prefix: 'metadata.', size: 4 },
  { rules: METADATA_COMPONENT_RULES, prefix: 'metadata_component.', size: 6 },
  { rules: COMPONENTS_RULES, prefix: 'components.', size: 6 },
]

describe('sbomFixerRules catalog', () => {
  it('covers all 21 rules with unique ids', () => {
    expect(ALL_FIX_RULES).toHaveLength(21)
    expect(new Set(ALL_FIX_RULES.map((rule) => rule.id)).size).toBe(21)
  })

  it('keeps each group complete and starts it with the reorder rule', () => {
    for (const group of GROUPS) {
      expect(group.rules).toHaveLength(group.size)
      expect(group.rules[0].id).toBe(`${group.prefix}reorder`)
      for (const rule of group.rules) {
        expect(rule.id.startsWith(group.prefix), rule.id).toBe(true)
      }
    }
  })

  it('provides valid JSON examples that actually differ', () => {
    for (const rule of ALL_FIX_RULES) {
      expect(() => JSON.parse(rule.example.before), rule.id).not.toThrow()
      expect(() => JSON.parse(rule.example.after), rule.id).not.toThrow()
      expect(rule.example.before, rule.id).not.toBe(rule.example.after)
    }
  })

  it('has labels and help texts in both locales for every rule', () => {
    for (const locale of [ru, en]) {
      for (const rule of ALL_FIX_RULES) {
        const label = lookup(locale, `sbomFixer.rules.${rule.id}`)
        const help = lookup(locale, `sbomFixer.help.${rule.id}`)
        expect(typeof label, rule.id).toBe('string')
        expect((label as string).length, rule.id).toBeGreaterThan(0)
        expect(typeof help, rule.id).toBe('string')
        expect((help as string).length, rule.id).toBeGreaterThan(20)
      }
    }
  })

  it('has example labels in both locales', () => {
    for (const locale of [ru, en]) {
      expect(lookup(locale, 'sbomFixer.exampleBefore')).toBeTruthy()
      expect(lookup(locale, 'sbomFixer.exampleAfter')).toBeTruthy()
    }
  })
})
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `cd frontend && npm test -- src/views/sbomFixerRules.test.ts`
Expected: FAIL — не удаётся разрешить `./sbomFixerRules`.

- [ ] **Step 3: Создать каталог `sbomFixerRules.ts`**

Структура (примеры `before`/`after` — дословно из приложения A спеки, включая отступы):

```ts
import type {
  ComponentsFixOptions,
  MetadataComponentFixOptions,
  MetadataFixOptions,
  RootFixOptions,
} from '../types/api'

export interface FixRuleExample {
  readonly before: string
  readonly after: string
}

export interface FixRule<K extends string> {
  readonly id: string
  readonly key: K
  readonly example: FixRuleExample
}

export type RootRuleKey = Exclude<keyof RootFixOptions, 'spec_version'>
export type MetadataRuleKey = Exclude<keyof MetadataFixOptions, 'component'>
export type MetadataComponentRuleKey = keyof MetadataComponentFixOptions
export type ComponentsRuleKey = keyof ComponentsFixOptions

export const ROOT_RULES: readonly FixRule<RootRuleKey>[] = [
  { id: 'root.reorder', key: 'reorder', example: { before: `…`, after: `…` } },
  // далее: root.set_spec_version, root.remove_dependencies,
  // root.remove_services, root.increment_version
]
```

Порядок по группам:
- `ROOT_RULES`: `root.reorder`, `root.set_spec_version`, `root.remove_dependencies`, `root.remove_services`, `root.increment_version`
- `METADATA_RULES`: `metadata.reorder`, `metadata.add_timestamp`, `metadata.remove_properties`, `metadata.remove_tools`
- `METADATA_COMPONENT_RULES`: `metadata_component.reorder`, `metadata_component.remove_external_references`, `metadata_component.remove_properties`, `metadata_component.remove_purl`, `metadata_component.remove_scope`, `metadata_component.rename_supplier`
- `COMPONENTS_RULES`: `components.reorder`, `components.remove_hashes`, `components.remove_scope`, `components.filter_external_references`, `components.filter_properties`, `components.fill_missing_gost_properties`

`key` для каждого правила — последний сегмент `id` после точки (`'reorder'`, `'set_spec_version'`, …). В конце файла:

```ts
export const ALL_FIX_RULES: readonly FixRule<string>[] = [
  ...ROOT_RULES,
  ...METADATA_RULES,
  ...METADATA_COMPONENT_RULES,
  ...COMPONENTS_RULES,
]
```

- [ ] **Step 4: Добавить тексты справки в локали**

В `ru.json` и `en.json` внутри секции `sbomFixer`, рядом с `rules`, добавить:

```json
"exampleBefore": "До",
"exampleAfter": "После",
"help": {
  "root": { "reorder": "…", "set_spec_version": "…", "remove_dependencies": "…", "remove_services": "…", "increment_version": "…" },
  "metadata": { "reorder": "…", "add_timestamp": "…", "remove_properties": "…", "remove_tools": "…" },
  "metadata_component": { "reorder": "…", "remove_external_references": "…", "remove_properties": "…", "remove_purl": "…", "remove_scope": "…", "rename_supplier": "…" },
  "components": { "reorder": "…", "remove_hashes": "…", "remove_scope": "…", "filter_external_references": "…", "filter_properties": "…", "fill_missing_gost_properties": "…" }
}
```

Русские тексты — дословно из приложения A спеки (абзацы, выделенные жирным, без самого жирного заголовка). Английские — смысловой перевод тех же текстов; `exampleBefore` = `"Before"`, `exampleAfter` = `"After"`. Ключ `warning` пока не трогать.

- [ ] **Step 5: Запустить тест и убедиться, что он проходит**

Run: `cd frontend && npm test -- src/views/sbomFixerRules.test.ts`
Expected: PASS (5 тестов).

- [ ] **Step 6: Проверить типы**

Run: `cd frontend && npx vue-tsc -b`
Expected: без ошибок (временные ошибки в `SbomFixer.vue` не ожидаются — каталог пока никем не используется).

---

### Task 2: Компонент `RuleHelp.vue`

**Files:**
- Create: `frontend/src/components/RuleHelp.vue`
- Create: `frontend/src/components/RuleHelp.test.ts`

**Interfaces:**
- Consumes: ничего из предыдущих задач.
- Produces: компонент с props `{ ruleId: string; description: string; before: string; after: string; beforeLabel: string; afterLabel: string; ruleTitle: string; open: boolean }` и emits `toggle`, `close`.

- [ ] **Step 1: Написать падающий тест компонента**

Создать `frontend/src/components/RuleHelp.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RuleHelp from './RuleHelp.vue'

const baseProps = {
  ruleId: 'components.remove_hashes',
  description: 'Removes direct hashes.',
  before: '{\n  "hashes": []\n}',
  after: '{\n}',
  beforeLabel: 'Before',
  afterLabel: 'After',
  ruleTitle: 'Remove hashes',
  open: false,
}

function mountRuleHelp(overrides: Partial<typeof baseProps> = {}) {
  return mount(RuleHelp as any, { props: { ...baseProps, ...overrides } })
}

describe('RuleHelp', () => {
  it('renders only the button when closed', () => {
    const wrapper = mountRuleHelp()
    const button = wrapper.find('.rule-help-button')
    expect(button.exists()).toBe(true)
    expect(button.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.rule-help-panel').exists()).toBe(false)
  })

  it('renders description and both examples when open', () => {
    const wrapper = mountRuleHelp({ open: true })
    const panel = wrapper.find('.rule-help-panel')
    expect(panel.text()).toContain('Removes direct hashes.')
    expect(panel.text()).toContain('Before')
    expect(panel.text()).toContain('After')
    expect(panel.findAll('pre')).toHaveLength(2)
    expect(panel.findAll('pre')[0].text()).toBe(baseProps.before)
    expect(panel.findAll('pre')[1].text()).toBe(baseProps.after)
    expect(wrapper.find('.rule-help-button').attributes('aria-expanded')).toBe('true')
  })

  it('links the button and the panel with aria attributes', () => {
    const wrapper = mountRuleHelp({ open: true })
    const button = wrapper.find('.rule-help-button')
    const panel = wrapper.find('.rule-help-panel')
    expect(button.attributes('aria-controls')).toBe(panel.attributes('id'))
    expect(panel.attributes('aria-labelledby')).toBe(button.attributes('id'))
    expect(panel.attributes('role')).toBe('region')
  })

  it('emits toggle on button click', async () => {
    const wrapper = mountRuleHelp()
    await wrapper.find('.rule-help-button').trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(1)
  })

  it('emits close on Escape', async () => {
    const wrapper = mountRuleHelp({ open: true })
    await wrapper.trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('exposes the rule id for tests and layout', () => {
    const wrapper = mountRuleHelp()
    expect(wrapper.find('[data-help-for="components.remove_hashes"]').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `cd frontend && npm test -- src/components/RuleHelp.test.ts`
Expected: FAIL — не удаётся разрешить `./RuleHelp.vue`.

- [ ] **Step 3: Реализовать `RuleHelp.vue`**

Требования к реализации:
- `<script setup lang="ts">`, `defineProps`/`defineEmits` строго по интерфейсу, `useId()` из `vue` дважды (`buttonId`, `panelId`).
- Корень — `<div class="rule-help" @keydown.esc="emit('close')">` со стилем `display: contents`, чтобы кнопка и панель участвовали в flex-раскладке строки правила.
- Кнопка: `<button type="button" class="rule-help-button" :id="buttonId" :aria-expanded="open" :aria-controls="panelId" :aria-label="ruleTitle" :data-help-for="ruleId" @click="emit('toggle')">i</button>`.
- Панель: `<div v-if="open" class="rule-help-panel" :id="panelId" role="region" :aria-labelledby="buttonId">`; внутри `<p class="rule-help-description">{{ description }}</p>` и `<div class="rule-examples">` с двумя `.rule-example`, каждый: `<span class="rule-example-label">{{ beforeLabel }}</span><pre><code>{{ before }}</code></pre>` (аналогично `after`).
- CTE: код вставляется интерполяцией, без `v-html`; `<pre>` с `white-space: pre`, `overflow-x: auto`.
- Scoped CSS: кнопка — кружок 1rem, как `.info-icon` в `SbomUpdater.vue` (border `var(--color-muted-light)`, `font-size: 0.6rem`, `margin-left: auto`, `cursor: pointer`, `:focus-visible` с контуром); панель — `flex-basis: 100%`, `width: 100%`, фон `var(--color-card-bg)`, рамка `var(--color-row-border)`, отступ `0.75rem`, `margin-top: 0.5rem`; `.rule-examples { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }`; `@media (max-width: 640px) { .rule-examples { grid-template-columns: 1fr; } }`.

- [ ] **Step 4: Запустить тест и убедиться, что он проходит**

Run: `cd frontend && npm test -- src/components/RuleHelp.test.ts`
Expected: PASS (6 тестов).

---

### Task 3: Перевести страницу на каталог, добавить справку, убрать плашку

**Files:**
- Modify: `frontend/src/views/SbomFixer.vue` (шаблон строк 26–203, импорт, `script` 352–418, CSS 554–561 и `.rule-row`)
- Modify: `frontend/src/views/SbomFixer.test.ts`
- Modify: `frontend/src/views/sbomFixerRules.test.ts`
- Modify: `frontend/src/i18n/locales/ru.json`, `en.json` (удалить `warning`)

**Interfaces:**
- Consumes: `ROOT_RULES`, `METADATA_RULES`, `METADATA_COMPONENT_RULES`, `COMPONENTS_RULES`, `FixRule` из Task 1; `RuleHelp.vue` из Task 2.
- Produces: DOM-контракт для тестов — `.rule-row[data-rule-row="<id>"]`, `.rule-label`, `[data-rule="<id>"]` (ввод), `[data-help-for="<id>"]`, `.rule-help-panel`.

- [ ] **Step 1: Обновить тесты страницы (падающие)**

В `frontend/src/views/SbomFixer.test.ts`:

1. Заменить тест `renders the warning banner about almost all fixes being enabled` на:

```ts
it('renders help for every rule and no warning banner', async () => {
  const wrapper = await mountFixer()
  expect(wrapper.find('.warning-banner').exists()).toBe(false)
  expect(wrapper.findAll('.rule-help-button')).toHaveLength(21)
  for (const rule of ALL_FIX_RULES) {
    expect(wrapper.find(`[data-help-for="${rule.id}"]`).exists(), rule.id).toBe(true)
  }
})
```

(добавить `import { ALL_FIX_RULES } from './sbomFixerRules'` вверху файла).

2. В тесте `does not block the page when settings fail to load` заменить проверку плашки:

```ts
expect(wrapper.find('.group-card').exists()).toBe(true)
```

3. Добавить новые тесты:

```ts
it('opens rule help with description and both examples', async () => {
  const wrapper = await mountFixer()
  await wrapper.find('[data-help-for="components.remove_hashes"]').trigger('click')
  const panel = wrapper.find('[data-rule-row="components.remove_hashes"] .rule-help-panel')
  expect(panel.exists()).toBe(true)
  expect(panel.text()).toContain('externalReferences')
  expect(panel.findAll('pre')).toHaveLength(2)
})

it('closes the same help on a second click and keeps only one panel open', async () => {
  const wrapper = await mountFixer()
  const first = wrapper.find('[data-help-for="root.reorder"]')
  await first.trigger('click')
  expect(wrapper.findAll('.rule-help-panel')).toHaveLength(1)

  await wrapper.find('[data-help-for="root.remove_services"]').trigger('click')
  expect(wrapper.findAll('.rule-help-panel')).toHaveLength(1)
  expect(wrapper.find('[data-rule-row="root.remove_services"] .rule-help-panel').exists()).toBe(true)

  await wrapper.find('[data-help-for="root.remove_services"]').trigger('click')
  expect(wrapper.findAll('.rule-help-panel')).toHaveLength(0)
})

it('closes help on Escape', async () => {
  const wrapper = await mountFixer()
  await wrapper.find('[data-help-for="root.reorder"]').trigger('click')
  await wrapper.find('[data-rule-row="root.reorder"] .rule-help').trigger('keydown', { key: 'Escape' })
  expect(wrapper.findAll('.rule-help-panel')).toHaveLength(0)
})

it('does not change the checkbox when its help is opened', async () => {
  const wrapper = await mountFixer()
  const checkbox = wrapper.find(rule('components.remove_hashes'))
  expect((checkbox.element as HTMLInputElement).checked).toBe(true)
  await wrapper.find('[data-help-for="components.remove_hashes"]').trigger('click')
  expect((checkbox.element as HTMLInputElement).checked).toBe(true)
})

it('does not toggle the spec version rule when the text input is clicked', async () => {
  const wrapper = await mountFixer()
  const checkbox = wrapper.find(rule('root.set_spec_version'))
  expect((checkbox.element as HTMLInputElement).checked).toBe(true)
  await wrapper.find('.spec-version-input').trigger('click')
  expect((checkbox.element as HTMLInputElement).checked).toBe(true)
})

it('saves the option bound to the row that was toggled', async () => {
  const wrapper = await mountFixer()
  await wrapper.find(rule('components.fill_missing_gost_properties')).setValue(true)
  await wrapper.find('.save-settings').trigger('click')
  await flushPromises()
  expect(saveFixOptionsMock).toHaveBeenCalledTimes(1)
  const saved = saveFixOptionsMock.mock.calls[0][0] as SbomFixOptions
  expect(saved.components.fill_missing_gost_properties).toBe(true)
  expect(saved.root.reorder).toBe(true)
})
```

4. В `frontend/src/views/sbomFixerRules.test.ts` добавить тест:

```ts
it('removes the obsolete warning message from both locales', () => {
  expect(lookup(ru, 'sbomFixer.warning')).toBeUndefined()
  expect(lookup(en, 'sbomFixer.warning')).toBeUndefined()
})
```

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `cd frontend && npm test -- src/views/SbomFixer.test.ts src/views/sbomFixerRules.test.ts`
Expected: FAIL — нет `.rule-help-button`, плашка ещё есть, ключ `warning` ещё есть.

- [ ] **Step 3: Переписать шаблон и скрипт `SbomFixer.vue`**

Шаблон:
- Удалить `<div class="warning-banner">…</div>` (строка 6).
- В каждой карточке заменить ручные `<label class="rule-row">…</label>` на цикл. Для `root`:

```vue
<div
  v-for="rule in ROOT_RULES"
  :key="rule.id"
  class="rule-row"
  :data-rule-row="rule.id"
>
  <label class="rule-label">
    <input v-model="options.root[rule.key]" type="checkbox" :data-rule="rule.id" />
    <span>{{ t(`sbomFixer.rules.${rule.id}`) }}</span>
  </label>
  <template v-if="rule.id === 'root.set_spec_version'">
    <span class="spec-version-label">{{ t('sbomFixer.specVersion') }}</span>
    <input
      v-model="options.root.spec_version"
      type="text"
      class="spec-version-input"
      :disabled="!options.root.set_spec_version"
    />
  </template>
  <RuleHelp
    :rule-id="rule.id"
    :description="t(`sbomFixer.help.${rule.id}`)"
    :before="rule.example.before"
    :after="rule.example.after"
    :before-label="t('sbomFixer.exampleBefore')"
    :after-label="t('sbomFixer.exampleAfter')"
    :rule-title="t(`sbomFixer.rules.${rule.id}`)"
    :open="openHelpId === rule.id"
    @toggle="toggleHelp(rule.id)"
    @close="openHelpId = null"
  />
</div>
```

- Аналогично `METADATA_RULES` с `options.metadata[rule.key]` и `METADATA_COMPONENT_RULES`/`COMPONENTS_RULES` со своими объектами опций. Текстовый инпут `spec_version` остаётся только в строке `root.set_spec_version`.
- Мастер-чекбоксы и кнопки «Выбрать всё / Снять всё» остаются как есть.

Скрипт:
- Импортировать `RuleHelp` и группы правил; удалить `rootKeys`, `metadataKeys`, `metadataComponentKeys`, `componentKeys`.
- Добавить `const openHelpId = ref<string | null>(null)` и `function toggleHelp(id: string): void { openHelpId.value = openHelpId.value === id ? null : id }`.
- Переписать вычисляемые значения:
  - `rootValues = () => ROOT_RULES.map((rule) => options.root[rule.key])`
  - `metadataValues = () => [...METADATA_RULES.map((r) => options.metadata[r.key]), ...METADATA_COMPONENT_RULES.map((r) => options.metadata.component[r.key])]`
  - `metadataComponentValues = () => METADATA_COMPONENT_RULES.map((r) => options.metadata.component[r.key])`
  - `componentValues = () => COMPONENTS_RULES.map((r) => options.components[r.key])`
- Сеттеры мастеров: циклы `for (const rule of ROOT_RULES) options.root[rule.key] = value` и т. п. (metadata-мастер — по обоим массивам).

- [ ] **Step 4: Удалить ключ `warning` и поправить CSS**

- Удалить `"warning": …` из секций `sbomFixer` в `ru.json` и `en.json`.
- Удалить CSS-блок `.warning-banner` (строки 554–561).
- `.rule-row`: оставить `display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;`, убрать `font-size` и `cursor` (они переезжают в `.rule-label`).
- Добавить `.rule-label { display: flex; align-items: center; gap: 0.5rem; font-size: 0.9rem; cursor: pointer; }`.
- У `.spec-version-label` убрать `margin-left: auto` (кнопка справки сама прижимается вправо через `margin-left: auto`).

- [ ] **Step 5: Запустить тесты страницы**

Run: `cd frontend && npm test -- src/views/SbomFixer.test.ts src/views/sbomFixerRules.test.ts`
Expected: PASS.

- [ ] **Step 6: Прогнать весь frontend-набор тестов**

Run: `cd frontend && npm test`
Expected: PASS, без новых предупреждений.

---

### Task 4: Обновить спецификации

**Files:**
- Modify: `specs/domains/web-ui.md` (Key Files ~12–13, раздел «Fix SBOM Page» ~194–215)
- Modify: `specs/domains/sbom-fixing.md` (Key Files ~7–21, после таблицы Rules ~154–161)

**Interfaces:**
- Consumes: итоговое поведение из Task 3.
- Produces: документация, соответствующая коду.

- [ ] **Step 1: Обновить `specs/domains/web-ui.md`**

- В Key Files добавить `frontend/src/components/RuleHelp.vue` и `frontend/src/views/sbomFixerRules.ts` с короткими описаниями (кнопка «(i)» + панель; каталог 21 правила с примерами).
- В разделе «Fix SBOM Page»:
  - удалить пункт «A warning banner above the form states…»;
  - добавить пункты: у каждого правила есть кнопка «(i)», раскрывающая встроенную справку под строкой (описание, примеры «До»/«После»); одновременно открыта одна панель; повторный клик и Escape закрывают; кнопка не переключает чекбокс; строки правил рендерятся из каталога `sbomFixerRules.ts`, в `metadata` правило `metadata.reorder` стоит первым; порядок в статистике по-прежнему определяется backend.

- [ ] **Step 2: Обновить `specs/domains/sbom-fixing.md`**

- В Key Files добавить `frontend/src/components/RuleHelp.vue` и `frontend/src/views/sbomFixerRules.ts`.
- После примечаний к таблице правил добавить одну строку: каждое правило документировано в UI встроенной справкой с примером «до/после», примеры отражают границы правил из таблицы.

- [ ] **Step 3: Прогнать финальную проверку**

Run: `cd frontend && npm test && npm run build`
Expected: тесты PASS, `vue-tsc` и `vite build` без ошибок.

- [ ] **Step 4: Сверить спеку и реализацию**

Проверить по чек-листу:
- 21 кнопка `[data-help-for]`, у каждой непустое описание в ru/en;
- в `metadata` первой строкой идёт «Упорядочить поля metadata»;
- плашки и ключа `warning` нет;
- статистика и отчёт о несоответствиях работают как раньше (существующие тесты зелёные).
