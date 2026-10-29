# Settings Page Auto-Save

**Date:** 2026-06-25
**Status:** Approved
**Scope:** Frontend only (`frontend/src/views/Settings.vue`) + spec update (`specs/domains/web-ui.md`)

## Goal

Remove the `Save` button from the Settings page. Settings changes are applied
immediately and silently persisted to the backend without requiring a separate
"save" action. Success and error feedback is shown via a single toast in the
bottom-right corner of the viewport.

## Behaviour

### Per-field save triggers

| Field type | Trigger | Notes |
|---|---|---|
| Toggle (checkbox) | `@change` | One click → one PATCH |
| `<select>` (log level) | `@change` | One selection → one PATCH |
| `<input type="number">` | `@change` after 500ms debounce | Prevents request spam while user types or uses arrow keys |
| `<input type="password">` (API keys) | `@blur` | Only if non-empty; debounced alongside number fields |
| `Clear token / Clear key` buttons | `@click` | Behaviour unchanged: direct PATCH with `null` value |

### Debounce

- All changes go through a single debounced auto-save path with **500ms** delay.
- The debounce window collapses consecutive changes (e.g. user dragging a
  number input, or typing into a password field) into one PATCH.
- Toggles and selects fire `@change` once per interaction — they still pass
  through the debouncer, which is a no-op for a single tick.
- Each new change resets the debounce timer (latest value wins).

### Toast notifications

- A single toast component is rendered **once at the top level** of the
  Settings page (still inside the page component, but positioned with
  `position: fixed` so it stays visible regardless of scroll position).
- The toast appears in the **bottom-right corner** of the viewport
  (`position: fixed; bottom: 1rem; right: 1rem; z-index: 1000`).
- States:
  - **Success:** green background, text `"Settings saved"`, auto-hide after 3s.
  - **Error:** red background, text `"Failed to save: <reason>"` (or
    `"Failed to save settings"` if no detailed message is available),
    auto-hide after 5s.
- A new toast replaces any currently visible one (the previous timer is
  cleared). No toast queue is implemented — the most recent event wins.
- Clear actions (`clearToken`, `clearLibrariesIoKey`, `clearEcosystemsKey`)
  reuse the same toast component for consistency.

### What is removed

- The `Save` button (`.save-btn` element and all related styles).
- The inline `.msg` block at the bottom of the page (success/failure text).
- The `saveSettings()` function (its body is replaced by `autoSave()`).
- The `saving` ref (no longer needed; loading state is implicit in the
  in-flight request, and the toast indicates completion).
- The `message` ref and `showMessage()` helper (replaced by the toast
  component's internal state).
- All legacy "Clear" inline messages: `showMessage('Token cleared', ...)`,
  `showMessage('Libraries.io key cleared', ...)`, `showMessage('ecosyste.ms
  key cleared', ...)`, and the three `Failed to clear ...` variants are
  consolidated through the same toast.

## Implementation

### `frontend/src/views/Settings.vue`

- Replace the existing `saveSettings()` function with a single
  `autoSave(partial: Partial<SettingsUpdate>)` helper that:
  1. Calls `updateSettings(partial)`.
  2. On success → toast `Settings saved`.
  3. On error → toast `Failed to save: <message>`.
- Bind each form input to a `@change` (or `@blur` for password inputs) that
  calls `autoSave()` with a single-field body.
- Wrap auto-save calls in a 500ms `setTimeout`-based debouncer. A small
  in-module helper `debounce(fn, 500)` is sufficient — no external library.
- The toast lives in the same component for now (positioned with
  `position: fixed`). It can be extracted into a shared component later if
  other pages need it.
- The `message` and `showMessage` indirection is gone; the toast component
  manages its own visible state internally.

### PATCH body

`updateSettings()` already accepts a partial body (all fields optional in
`SettingsUpdate`). We send only the field that changed. This matches the
existing backend contract (`src/purl_resolver/routes/settings.py`).

## Spec update

`specs/domains/web-ui.md`, line 164:

- **Before:** `Settings are saved via PATCH /api/v1/settings on button click`
- **After:** `Settings changes are auto-saved to PATCH /api/v1/settings on
  field change (or on blur for password fields). Success and error feedback
  is shown via a single toast in the bottom-right corner of the viewport.`

Update `specs/INDEX.md` only if the new wording changes how the spec is
referenced — it does not, so no change there.

## Out of scope

- Visual "dirty / saving / saved" indicators on individual fields.
- Undo or change-rejection support.
- Backend or API contract changes.
- Toast extraction into a global component (deferred until a second page
  needs it).