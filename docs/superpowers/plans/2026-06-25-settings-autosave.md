# Settings Page Auto-Save Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Settings page's "Save" button with auto-save on field change/blur, plus a single bottom-right toast notification replacing all inline feedback messages.

**Architecture:** Single Vue component (`Settings.vue`) is modified. A small in-module `debounce()` helper wraps `autoSave()`, which calls the existing `PATCH /api/v1/settings` API with a partial body. A toast component (rendered inline at the top of `Settings.vue`, positioned via `position: fixed`) replaces all inline `.msg` blocks.

**Tech Stack:** Vue 3 (`<script setup lang="ts">`), TypeScript, existing `frontend/src/api/settings.ts` client, `vue-tsc` for type-checking, no new dependencies.

## Global Constraints

- No new dependencies; debounce must be implemented in-module (`setTimeout` + `clearTimeout`).
- Toast is `position: fixed; bottom: 1rem; right: 1rem; z-index: 1000` so it is always visible regardless of scroll.
- Debounce window: **500ms** for all auto-save calls.
- API keys: save on `@blur`, only when non-empty.
- All other fields: save on `@change` (debounced).
- Clear-token buttons: remain unchanged in trigger, but switch their feedback from inline message to the same toast.
- The existing `frontend/src/types/api.ts` `SettingsUpdate` type is the PATCH body shape; do not change it.

---

## File Structure

**Modify:**
- `frontend/src/views/Settings.vue` — full refactor: replace `saveSettings()` with `autoSave()`, add debounce helper, add toast component, remove Save button and inline `.msg`.
- `specs/domains/web-ui.md` — update lines 164-165 to reflect auto-save + toast.

**No new files. No new dependencies.** (Per YAGNI: extracting toast into a shared component is out of scope until a second page needs it.)

---

### Task 1: Add debounce helper and toast component skeleton in Settings.vue

**Files:**
- Modify: `frontend/src/views/Settings.vue` (script + template + style sections)

**Interfaces:**
- `debounce<T extends (...args: any[]) => any>(fn: T, ms: number): T` — internal helper.
- `toastState: Ref<{ text: string; isError: boolean } | null>` — visible toast, auto-clears after 3s (success) or 5s (error).
- `showToast(text: string, isError: boolean)` — replaces `showMessage()`.

- [ ] **Step 1: Add the debounce helper to the script section**

Insert immediately after the existing `import { ref, onMounted } from 'vue'` line (replace that line):

```ts
import { ref, onMounted, onBeforeUnmount } from 'vue'
```

Then, immediately below `const messageTimer` declaration (which we'll remove), add:

```ts
function debounce<T extends (...args: any[]) => void>(fn: T, ms: number): T {
  let timer: ReturnType<typeof setTimeout> | null = null
  return ((...args: Parameters<T>) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      fn(...args)
    }, ms)
  }) as T
}
```

- [ ] **Step 2: Replace `showMessage` with `showToast`**

Remove the existing `showMessage` function and the `message` ref and `messageTimer` declarations. Replace with:

```ts
const toast = ref<{ text: string; isError: boolean } | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null

function showToast(text: string, isError: boolean) {
  if (toastTimer) clearTimeout(toastTimer)
  toast.value = { text, isError }
  toastTimer = setTimeout(() => {
    toast.value = null
    toastTimer = null
  }, isError ? 5000 : 3000)
}

onBeforeUnmount(() => {
  if (toastTimer) clearTimeout(toastTimer)
})
```

- [ ] **Step 3: Add toast to template**

Remove the inline `.msg` block (lines 202-204 of the original file). Replace it with a single toast element at the very end of the `<template>` root (still inside the `<div class="settings-page">`, after the `<button class="save-btn">` removal in Task 2):

```html
<div v-if="toast" :class="['toast', toast.isError ? 'toast-err' : 'toast-ok']">
  {{ toast.text }}
</div>
```

- [ ] **Step 4: Replace `.msg` styles with `.toast` styles**

Remove the existing `.msg`, `.msg-ok`, `.msg-err` blocks (lines 536-549 of the original file). Add in their place:

```css
.toast {
  position: fixed;
  bottom: 1rem;
  right: 1rem;
  z-index: 1000;
  padding: 0.75rem 1rem;
  border-radius: var(--border-radius);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  max-width: 360px;
  animation: toast-in 0.2s ease-out;
}

.toast-ok {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.toast-err {
  background: var(--color-error-bg);
  color: var(--color-error);
}

@keyframes toast-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/Settings.vue
git commit -m "feat(settings): add debounce helper and toast component"
```

---

### Task 2: Replace `saveSettings()` with `autoSave()` and wire per-field handlers

**Files:**
- Modify: `frontend/src/views/Settings.vue` (script section, template bindings)

**Interfaces:**
- `autoSave(partial: Partial<SettingsUpdate>): Promise<void>` — sends a single-field PATCH, shows toast on success or error, clears the matching password input on success.
- All `<input>` and `<select>` elements get `@change` or `@blur` handlers that invoke `autoSave` via the debounce wrapper.
- One debounced function `debouncedAutoSave = debounce(autoSave, 500)`.

- [ ] **Step 1: Replace the `saveSettings()` function with `autoSave()` and a debounced wrapper**

Remove the entire `saveSettings` function (lines 259-293 of the original file). In its place:

```ts
async function autoSave(partial: Partial<SettingsUpdate>) {
  try {
    await updateSettings(partial)
    showToast('Settings saved', false)
    if ('github_token' in partial) githubTokenInput.value = ''
    if ('librariesio_api_key' in partial) librariesioKeyInput.value = ''
    if ('ecosystems_api_key' in partial) ecosystemsKeyInput.value = ''
    await loadSettings()
  } catch (err) {
    const detail = err instanceof Error ? err.message : 'unknown error'
    showToast(`Failed to save: ${detail}`, true)
  }
}

const debouncedAutoSave = debounce(autoSave, 500)
```

- [ ] **Step 2: Wire toggle handlers**

In the template, add `@change` to each `<input type="checkbox">` inside `.toggle` labels. Concretely:

```html
<label class="toggle">
  <input type="checkbox" v-model="validateDbUrls" @change="debouncedAutoSave({ validate_db_urls: validateDbUrls })">
  <span class="toggle-slider"></span>
</label>
```

Repeat the same pattern for the `librariesioEnabled` and `ecosystemsEnabled` toggles, replacing the boolean field name accordingly:

- `librariesioEnabled` toggle: `@change="debouncedAutoSave({ librariesio_enabled: librariesioEnabled })"`
- `ecosystemsEnabled` toggle: `@change="debouncedAutoSave({ ecosystems_enabled: ecosystemsEnabled })"`

- [ ] **Step 3: Wire number input handlers**

For each `<input type="number">`, add `@change` with the corresponding field. There are six number inputs; use these bindings (replace the bare `v-model.number` lines, keep the rest of the attributes intact):

- `urlValidationTimeout`: `@change="debouncedAutoSave({ url_validation_timeout: urlValidationTimeout })"`
- `revalidationCooldownHours`: `@change="debouncedAutoSave({ revalidation_cooldown_hours: revalidationCooldownHours })"`
- `ecosystemsMaxRequestsPerSecond`: `@change="debouncedAutoSave({ ecosystems_max_requests_per_second: ecosystemsMaxRequestsPerSecond })"`
- `retryMaxAttempts`: `@change="debouncedAutoSave({ retry_max_attempts: retryMaxAttempts })"`
- `retryBaseCooldownSeconds`: `@change="debouncedAutoSave({ retry_base_cooldown_seconds: retryBaseCooldownSeconds })"`

- [ ] **Step 4: Wire `<select>` handler**

For the log level `<select>`:

```html
<select v-model="logLevel" @change="debouncedAutoSave({ log_level: logLevel })" class="select-input">
```

- [ ] **Step 5: Wire password input handlers (`@blur` instead of `@change`)**

For each `<input type="password">`, replace the bare `v-model` binding with a conditional blur handler that only fires when the field is non-empty. The bindings:

- `githubTokenInput`:
  ```html
  <input type="password" :value="githubTokenInput" @input="githubTokenInput = ($event.target as HTMLInputElement).value" @blur="onGithubTokenBlur" placeholder="ghp_..." class="pw-input">
  ```
- `librariesioKeyInput`:
  ```html
  <input type="password" :value="librariesioKeyInput" @input="librariesioKeyInput = ($event.target as HTMLInputElement).value" @blur="onLibrariesIoKeyBlur" placeholder="libraries.io API key" class="pw-input">
  ```
- `ecosystemsKeyInput`:
  ```html
  <input type="password" :value="ecosystemsKeyInput" @input="ecosystemsKeyInput = ($event.target as HTMLInputElement).value" @blur="onEcosystemsKeyBlur" placeholder="ecosyste.ms API key (optional)" class="pw-input">
  ```

Then add these three helpers in the script section, right below the `debouncedAutoSave` declaration:

```ts
async function onGithubTokenBlur() {
  const value = githubTokenInput.value.trim()
  if (!value) return
  await autoSave({ github_token: value })
}

async function onLibrariesIoKeyBlur() {
  const value = librariesioKeyInput.value.trim()
  if (!value) return
  await autoSave({ librariesio_api_key: value })
}

async function onEcosystemsKeyBlur() {
  const value = ecosystemsKeyInput.value.trim()
  if (!value) return
  await autoSave({ ecosystems_api_key: value })
}
```

- [ ] **Step 6: Update clear-token functions to use the toast**

In `clearToken`, `clearLibrariesIoKey`, `clearEcosystemsKey`, replace every `showMessage(...)` call with `showToast(...)` keeping the same text and `isError` flag. The functions remain otherwise unchanged. After this step, no `showMessage` references should remain in the file.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/Settings.vue
git commit -m "feat(settings): auto-save on change/blur, remove Save button"
```

---

### Task 3: Remove the Save button and related dead code

**Files:**
- Modify: `frontend/src/views/Settings.vue`

- [ ] **Step 1: Remove the Save button from the template**

Delete this line:

```html
<button class="save-btn" :disabled="saving" @click="saveSettings">Save</button>
```

- [ ] **Step 2: Remove the unused `saving` ref and the now-unused `save-btn` styles**

Remove this declaration from the script section:

```ts
const saving = ref(false)
```

Remove these CSS blocks at the end of the `<style scoped>` section:

```css
.save-btn {
  margin-top: 1rem;
  padding: 0.75rem 1.5rem;
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--border-radius);
  font-size: 1rem;
  cursor: pointer;
}

.save-btn:hover {
  background: var(--color-primary-hover);
}

.save-btn:disabled {
  background: var(--color-primary-disabled);
  cursor: not-allowed;
}
```

- [ ] **Step 3: Verify no remaining references to `saveSettings`, `saving`, `save-btn`, `showMessage`, or `message`**

Run:

```bash
grep -nE "saveSettings|showMessage|\bsaving\b|save-btn|\bmessage\b" frontend/src/views/Settings.vue
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/Settings.vue
git commit -m "refactor(settings): remove Save button and dead code"
```

---

### Task 4: Update the web-ui spec

**Files:**
- Modify: `specs/domains/web-ui.md` (lines 164-165)

- [ ] **Step 1: Replace lines 164-165**

The current text is:

```
- Settings are saved via `PATCH /api/v1/settings` on button click
- Success/error feedback is shown after save attempt
```

Replace with:

```
- Settings are auto-saved to `PATCH /api/v1/settings` on field change (toggle/select/number) or on blur for password inputs; changes are debounced at 500ms
- Success and error feedback is shown via a single toast in the bottom-right corner of the viewport (3s for success, 5s for error)
```

- [ ] **Step 2: Commit**

```bash
git add specs/domains/web-ui.md
git commit -m "docs(specs): describe Settings auto-save and toast behavior"
```

---

### Task 5: Type-check and manual verification

**Files:**
- Verify: `frontend/src/views/Settings.vue`, `specs/domains/web-ui.md`

- [ ] **Step 1: Run type-check + production build**

Run:

```bash
npm run build --prefix frontend
```

Expected: build succeeds with no TypeScript errors. (This command runs `vue-tsc -b && vite build`.)

- [ ] **Step 2: Manual smoke verification (developer runs locally)**

Start the dev server and navigate to `/settings`:

```bash
npm run dev --prefix frontend
```

Then verify, in order:

1. The `Save` button is not present.
2. Toggling `Validate URLs from local database` triggers a toast "Settings saved" within ~500ms, and the toggle persists after a hard refresh of `/settings`.
3. Changing `Validation timeout (seconds)` from 5 → 6 fires a single PATCH (verify in browser DevTools Network tab — only one PATCH after the debounce settles) and shows the toast.
4. Rapidly changing `Validation timeout` 5 → 6 → 7 → 8 within ~500ms collapses into a single PATCH with the final value 8.
5. Changing the `Log level` dropdown fires a PATCH and shows the toast.
6. Entering a GitHub token (any non-empty string) and tabbing out fires a PATCH, shows the toast, and clears the input.
7. Tabbing out of an empty GitHub token field does **not** fire a PATCH.
8. Clicking `Clear token` after a token is set fires a PATCH with `github_token: null` and shows the toast "Token cleared".
9. Scrolling the page so a card is partially off-screen and triggering any save: the toast appears in the bottom-right corner of the **viewport**, not relative to the scroll position.
10. Stopping the backend (or otherwise causing a 5xx) and changing a toggle: the toast appears with text `Failed to save: <reason>` and stays ~5s.

- [ ] **Step 3: Final commit if any fix-ups were needed**

If any code change was required during verification, commit it with a focused message; otherwise no commit.

---

## Self-Review

**1. Spec coverage:**
- Remove Save button → Task 3.
- Auto-save on change for non-password fields → Task 2 Steps 2-4.
- Auto-save on blur for password fields → Task 2 Step 5.
- 500ms debounce → Task 2 Step 1 + Tasks 1-2 wiring.
- Toast in bottom-right, fixed position → Task 1 Steps 3-4.
- Unified toast for all feedback (including clear actions) → Task 2 Step 6.
- Spec update → Task 4.

**2. Placeholder scan:** No TBD/TODO/"implement later" markers. All code blocks contain real code.

**3. Type consistency:** `autoSave(partial: Partial<SettingsUpdate>)` is defined once and used throughout. Field names match `frontend/src/types/api.ts` exactly. Clear-button handlers preserve the same `updateSettings({ github_token: null })` etc. shape.