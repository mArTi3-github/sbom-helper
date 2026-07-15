# Light/Dark Theme Toggle for sbom-helper

## Overview

Add a light color theme alongside the existing dark theme, with a toggle in Settings > Browser to switch between them. The choice persists across sessions via `localStorage`, following the exact same pattern as the language selector.

## Architecture

No backend changes — this is purely a frontend client-side feature. The theme is stored in the browser, not in `data/settings.json`.

```
User selects theme in Settings.vue
→ localStorage.setItem('theme', 'dark'|'light')
→ document.documentElement.classList.toggle('light-theme')
→ CSS custom properties swap via .light-theme { --color-body-bg: ... }
```

### Modified Files

| File | Change |
|------|--------|
| `frontend/src/assets/main.css` | Add `.light-theme { ... }` block with all 28 CSS variable overrides |
| `frontend/src/main.ts` | Read `localStorage.getItem('theme')` and apply class at bootstrap |
| `frontend/src/App.vue` | Add `watch` on theme ref to sync `<html>` class (immediate) |
| `frontend/src/views/Settings.vue` | Add `<select>` for theme in the "Browser" card, under language |
| `frontend/src/i18n/locales/en.json` | Add `theme`, `themeDesc`, `themeDark`, `themeLight` keys |
| `frontend/src/i18n/locales/ru.json` | Same keys in Russian |

### New File

| File | Purpose |
|------|---------|
| `frontend/src/composables/useTheme.ts` | Shared reactive `theme` ref + initialisation from localStorage |

No new dependencies, no Pinia store changes.

## Frontend Details

### Shared Composable (`composables/useTheme.ts`)

```ts
import { ref } from 'vue'

const theme = ref<'dark' | 'light'>(
  localStorage.getItem('theme') === 'light' ? 'light' : 'dark'
)

export function useTheme() {
  return { theme }
}
```

Module-level `ref` ensures the same reactive instance is shared by all callers.

### Theme Initialization (`main.ts`)

```ts
const savedTheme = localStorage.getItem('theme')
if (savedTheme === 'light') {
  document.documentElement.classList.add('light-theme')
}
```

Placed right after the locale initialization, before `createApp`. This prevents a flash of wrong theme before Vue mounts.

### Theme Watcher (`App.vue`)

```ts
import { watch } from 'vue'
import { useTheme } from '../composables/useTheme'

const { theme } = useTheme()
watch(theme, (val) => {
  document.documentElement.classList.toggle('light-theme', val === 'light')
  localStorage.setItem('theme', val)
}, { immediate: true })
```

The watcher reacts to any change to `theme` (whether from Settings.vue or a future automation) and syncs both the DOM class and localStorage.

### Settings.vue Selector

Placed in the "Browser" card, directly after the language `<select>`:

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

### Theme Change Handler

```ts
import { useTheme } from '../composables/useTheme'
const { theme } = useTheme()

function setTheme(e: Event) {
  const val = (e.target as HTMLSelectElement).value as 'dark' | 'light'
  theme.value = val
}
```

Both call `useTheme()` and receive the same reactive `theme` ref (module-level singleton). The watcher in App.vue handles DOM + localStorage sync. No debounce or API call needed.

### i18n Keys

**`en.json`:**
```json
"theme": "Theme",
"themeDesc": "Color theme",
"themeDark": "Dark",
"themeLight": "Light"
```

**`ru.json`:**
```json
"theme": "Тема",
"themeDesc": "Цветовая тема",
"themeDark": "Тёмная",
"themeLight": "Светлая"
```

## Light Theme Palette

All 28 CSS variables under `.light-theme` selector, preserving the same primary/accent/semantic character but inverted for light backgrounds:

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

### Design Decisions

- **Body background `#f5f7fa`** — cool off-white, easier on the eyes than pure `#fff` for extended sessions
- **Primary `#5582ff`** — slightly deeper than dark theme's `#6b8cff` to maintain WCAG AA contrast on white
- **Card `#ffffff`** with subtle `#e2e8f0` border — clean, layered look
- **Semantic bg colors** (success/warning/error) — switched from dark `#064e3b`-style to light pastels `#d1fae5`-style, matching standard light-theme conventions
- **Shadows** — reduced opacity from 0.3 to 0.08, more appropriate for light theme

## `.btn-secondary` hover edge case

Current code in `main.css`:
```css
.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.05);
}
```
This works on dark backgrounds (makes button slightly lighter). On light theme, it would make the button barely visibly lighter on white. Fix: override in `.light-theme`:
```css
.light-theme .btn-secondary:hover {
  background: rgba(0, 0, 0, 0.05);
}
```

## Invariants

- Theme choice survives page refresh (localStorage only)
- No backend changes — theme is purely client-side
- Dark remains the default (no `prefers-color-scheme` detection — explicit choice only)
- Same CSS variable names are reused; `.light-theme` overrides `:root` values
- All scoped Vue component styles that use `var(--color-*)` inherit automatically — no component changes needed
