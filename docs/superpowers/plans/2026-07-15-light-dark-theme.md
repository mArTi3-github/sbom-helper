# Light/Dark Theme Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a light theme alongside the existing dark theme, with a toggle in Settings > Browser that persists to localStorage.

**Architecture:** CSS custom properties under `.light-theme { ... }` override the `:root` dark values. A shared composable (`useTheme.ts`) provides a reactive `theme` ref. `main.ts` applies the initial class; `App.vue` watches the ref and syncs DOM class + localStorage; `Settings.vue` exposes a `<select>` in the Browser card.

**Tech Stack:** Vue 3 (Composition API), CSS custom properties, localStorage

## Global Constraints

- No backend changes — theme is purely client-side
- Dark remains the default
- Same CSS variable names are reused; `.light-theme` overrides `:root` values
- All scoped Vue component styles using `var(--color-*)` inherit automatically

---

### Task 1: CSS — Light Theme Variables

**Files:**
- Modify: `frontend/src/assets/main.css` — add `.light-theme` block after `:root`

**Interfaces:**
- Produces: `.light-theme` CSS class that can be toggled on `<html>` to switch all color variables

- [ ] **Step 1: Add `.light-theme` block with all 28 CSS variable overrides**

After the closing `}` of `:root`, add:

```css
.light-theme {
  --color-primary: #5582ff;
  --color-primary-hover: #4070f0;
  --color-primary-disabled: #a0b8ff;
  --color-primary-focus: rgba(85, 130, 255, 0.15);
  --color-accent: #8b6cf7;
  --color-danger: #e05050;
  --color-danger-hover: #c0392b;
  --color-success: #22a67e;
  --color-success-bg: #d1fae5;
  --color-warning: #d97706;
  --color-warning-bg: #fef3cd;
  --color-error: #dc2626;
  --color-error-bg: #fee2e2;
  --color-error-border: #fca5a5;
  --color-warning-border: #fbbf24;
  --color-body-bg: #f5f7fa;
  --color-body-text: #1e293b;
  --color-card-bg: #ffffff;
  --color-card-border: #e2e8f0;
  --color-card-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  --color-muted: #64748b;
  --color-muted-light: #94a3b8;
  --color-muted-lighter: #cbd5e1;
  --color-input-border: #d1d5db;
  --color-toggle-off: #d1d5db;
  --color-toggle-on: #5582ff;
  --color-delete-border: #e05050;
  --color-delete-bg-hover: #fef2f2;
  --color-table-header-bg: #f1f5f9;
  --color-row-border: #e2e8f0;
  --color-setting-border: #f1f5f9;
}
```

- [ ] **Step 2: Fix `.btn-secondary:hover` for light theme**

In `main.css`, the existing `.btn-secondary:hover` uses `rgba(255, 255, 255, 0.05)`. Add an override in the `.light-theme` block (before the closing `}`):

```css
.light-theme .btn-secondary:hover {
  background: rgba(0, 0, 0, 0.05);
}
```

- [ ] **Step 3: Verify visually**

Add `class="light-theme"` to `<html>` in `frontend/index.html` temporarily, run `npm run dev`, and confirm the page renders with light backgrounds and readable text. Remove the temporary class after verification.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/assets/main.css
git commit -m "feat: add light theme CSS variables"
```

---

### Task 2: Infrastructure — Composable + Bootstrap + Watcher

**Files:**
- Create: `frontend/src/composables/useTheme.ts`
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/App.vue`

**Interfaces:**
- Consumes: `.light-theme` CSS class (from Task 1)
- Produces: `useTheme()` composable returning `{ theme: Ref<'dark' | 'light'> }`

- [ ] **Step 1: Create `useTheme.ts` composable**

```ts
import { ref } from 'vue'

const theme = ref<'dark' | 'light'>(
  localStorage.getItem('theme') === 'light' ? 'light' : 'dark'
)

export function useTheme() {
  return { theme }
}
```

- [ ] **Step 2: Add theme initialization in `main.ts`**

After the locale block (line 10) and before `createApp` (line 12), add:

```ts
const savedTheme = localStorage.getItem('theme')
if (savedTheme === 'light') {
  document.documentElement.classList.add('light-theme')
}
```

- [ ] **Step 3: Add theme watcher in `App.vue`**

Replace the script section with:

```ts
<script setup lang="ts">
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTheme } from '../composables/useTheme'
import AppNav from './components/AppNav.vue'
const { t, locale } = useI18n()
const { theme } = useTheme()

watch(locale, (lang) => {
  document.documentElement.lang = lang
}, { immediate: true })

watch(theme, (val) => {
  document.documentElement.classList.toggle('light-theme', val === 'light')
  localStorage.setItem('theme', val)
}, { immediate: true })
</script>
```

- [ ] **Step 4: Verify the watcher works**

Run `npm run dev`, open DevTools console, run:
```js
document.documentElement.classList.add('light-theme')
```
Confirm the page switches to light theme. Then:
```js
document.documentElement.classList.remove('light-theme')
```
Confirm it reverts to dark.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/composables/useTheme.ts frontend/src/main.ts frontend/src/App.vue
git commit -m "feat: add theme composable, bootstrap and watcher"
```

---

### Task 3: i18n Keys — Theme Translations

**Files:**
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/ru.json`

**Interfaces:**
- Produces: `settings.theme`, `settings.themeDesc`, `settings.themeDark`, `settings.themeLight` keys

- [ ] **Step 1: Add English keys**

In `en.json`, in the `settings` section, after `"languageDesc": "Interface language",` (line 146), add:

```json
    "theme": "Theme",
    "themeDesc": "Color theme",
    "themeDark": "Dark",
    "themeLight": "Light",
```

- [ ] **Step 2: Add Russian keys**

In `ru.json`, in the `settings` section, after `"languageDesc": "Язык веб-интерфейса",` (line 146), add:

```json
    "theme": "Тема",
    "themeDesc": "Цветовая тема",
    "themeDark": "Тёмная",
    "themeLight": "Светлая",
```

- [ ] **Step 3: Verify i18n integrity**

Run `npm run dev` and confirm no i18n warnings in console. Optionally run the existing Settings test to confirm no key-related breakage:

```bash
npx vitest run src/views/Settings.test.ts
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/i18n/locales/en.json frontend/src/i18n/locales/ru.json
git commit -m "feat: add theme i18n keys"
```

---

### Task 4: Settings — Theme Selector in Browser Card

**Files:**
- Modify: `frontend/src/views/Settings.vue`
- Modify: `frontend/src/views/Settings.test.ts`

**Interfaces:**
- Consumes: `useTheme()` composable (from Task 2), i18n keys (from Task 3)
- Consumes: `.light-theme` CSS class sync via watcher (from Task 2)

- [ ] **Step 1: Add theme `<select>` to the template**

In the "Browser" card (`<div class="card">` with `card-title` = `t('settings.browserSection')`), after the language `<select>` block (after line 27 `</select>`), add:

```vue
<div class="setting-row">
  <div>
    <div class="setting-label">{{ t('settings.theme') }}</div>
    <div class="setting-desc">{{ t('settings.themeDesc') }}</div>
  </div>
  <select :value="theme" @change="setTheme" class="select-input">
    <option value="dark">{{ t('settings.themeDark') }}</option>
    <option value="light">{{ t('settings.themeLight') }}</option>
  </select>
</div>
```

- [ ] **Step 2: Add `setTheme` function and import in script**

In the `<script setup>` block, add the import and function. After the existing `setLanguage` function (line 441), add:

```ts
import { useTheme } from '../composables/useTheme'
const { theme } = useTheme()

function setTheme(e: Event) {
  const val = (e.target as HTMLSelectElement).value as 'dark' | 'light'
  theme.value = val
}
```

- [ ] **Step 3: Update Settings test**

In `Settings.test.ts`, add a new test block after the existing tests. Before the test, set up localStorage mock in the `beforeEach` block (add `localStorage.clear()`). Then add:

```ts
it('renders theme selector and switches theme', async () => {
  const wrapper = mountSettings()
  await flushPromises()

  const themeSelect = wrapper.findAll('select').find((s) => {
    const options = s.findAll('option')
    return options.length === 2 &&
      options.some((o) => o.text() === 'Dark') &&
      options.some((o) => o.text() === 'Light')
  })
  expect(themeSelect).toBeDefined()

  await themeSelect!.setValue('light')
  await flushPromises()
  expect(document.documentElement.classList.contains('light-theme')).toBe(true)
  expect(localStorage.getItem('theme')).toBe('light')

  await themeSelect!.setValue('dark')
  await flushPromises()
  expect(document.documentElement.classList.contains('light-theme')).toBe(false)
  expect(localStorage.getItem('theme')).toBe('dark')
})
```

- [ ] **Step 4: Run tests**

```bash
npx vitest run src/views/Settings.test.ts
```

Expected: all tests pass, including the new theme test.

- [ ] **Step 5: Manual verification**

```bash
npm run dev
```
1. Open Settings page
2. Switch theme to Light — page should switch to light colors
3. Reload the page — should stay on light theme
4. Switch to Dark — should revert
5. Reload — should stay on dark

- [ ] **Step 6: TypeScript check**

```bash
npx vue-tsc --noEmit
```

Expected: no type errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/Settings.vue frontend/src/views/Settings.test.ts
git commit -m "feat: add theme selector to Settings page"
```
