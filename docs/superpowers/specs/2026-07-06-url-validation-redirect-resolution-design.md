# URL Validation: Remove HTTP HEAD Status-Code Checks, Preserve Redirect Resolution

## Problem

`validate_url()` в `url_validator.py:379` мгновенно отвергает любой URL,
не начинающийся с `http://` или `https://`:

```python
if not url.startswith(("http://", "https://")):
    return UrlValidationOutput(UrlValidationResult.INVALID)
```

Это блокирует валидные VCS URL, возвращаемые резолверами (purl2repo, ecosyste.ms):
- `git://github.com/user/repo.git`
- `svn://svn.example.com/repo`
- `ssh://git@github.com/user/repo.git`

VCS-прозвонщики (`_git_probe`, `_svn_probe`, `_hg_probe`) используют нативные CLI
инструменты (`git ls-remote`, `svn ls`, `hg identify`) и поддерживают любые схемы
URL. Только HTTP HEAD (`_head_request`) требует HTTP(S).

## Решение

Реструктурировать `validate_url()` в три шага:

1. **Pre-check (всегда):** синтаксис + SSRF guard (`_is_private_url`)
2. **Redirect resolution (только HTTP/HTTPS):** лёгкий HEAD для `final_url` +
   детекция невалидного токена (401/403)
3. **VCS probe (всегда):** `_check_vcs(final_url, timeout, github_token)` — без изменений

### Step 1: Pre-check

Перед любым сетевым вызовом:

- `urlsplit(url).hostname` непустой → иначе `INVALID`
- `_is_private_url(url)` = False → иначе `INVALID`

Заменяет старый `url.startswith(("http://", "https://"))`.

### Step 2: Redirect resolution (только HTTP/HTTPS)

Новый helper `_resolve_redirects(url, timeout, github_token=None) → tuple[str, UrlValidationResult | None]`:

- HEAD с `follow_redirects=True`, использует `github_token` для авторизации
  (повышение rate limits)
- Проверяет `_is_private_url` на финальном redirect target
- **Проверяет статус-код HEAD: 401 или 403 c токеном → TOKEN_INVALID**
- **Игнорирует все остальные статус-коды** (404, 405, 500 не влияют на результат)
- Не взаимодействует с rate-limit трекером
- В случае `httpx.RequestError` → возвращает исходный URL, `None` (graceful
  degradation)

Почему TOKEN_INVALID остаётся в HEAD:
- Все проверяемые репозитории **публичные**
- Единственная цель токена в HEAD — повышенные rate limits
- Если токен сломан, нужно узнать об этом и перестать его использовать,
  иначе rate limits будут ниже без видимой причины
- `_git_probe` не участвует в детекции токена — для публичных репозиториев
  `git ls-remote` работает без аутентификации

Для не-HTTP/HTTPS схем (`git://`, `ssh://`, `svn://`): шаг пропускается,
используется исходный URL.

### Step 3: VCS probe (всегда)

`_check_vcs(final_url, timeout, github_token)` — без изменений. `github_token`
передаётся в `_git_probe` для oauth2:token rewrite URL к GitHub, что повышает
rate limits для `git ls-remote` (с ~60/ч до ~5000/ч). Токен не используется для
доступа к приватным репозиториям — все проверяемые репозитории публичные.

### Что удаляется

| Компонент | Причина |
|---|---|
| `if not url.startswith(...)` gate | Блокировал валидные VCS URL |
| Status-code checks из HEAD: 404→INVALID, 403→INVALID, >=400→INVALID | HEAD статусы не отражают VCS-доступность |
| 401/403 без токена → INVALID | Релевантно только с токеном для TOKEN_INVALID |
| `_RateLimitTracker`, `_is_rate_limited`, `_rate_limit_tracker` | HTTP-based rate limits ортогональны VCS-протоколу |
| `rate_limit_cooldown` параметр | Больше не используется |

### Что остаётся

| Компонент | Причина |
|---|---|
| `_head_request()` | Используется `validate_github_token()` и может быть упрощена |
| `_git_probe`, `_svn_probe`, `_hg_probe`, `_fossil_probe*` | Без изменений (oauth2 rewrite сохранён для rate limits) |
| `_check_vcs()` | Без изменений — получает `github_token`, передаёт в `_git_probe` |
| `_is_private_url()` | Используется в pre-check, `_resolve_redirects`, `_fossil_probe*` |
| `ensure_connectivity()` | Без изменений |
| `validate_url_with_retry()` | Retry-логика TOKEN_INVALID сохранена (сигнал приходит из HEAD в `validate_url`) |
| `UrlValidationResult.TOKEN_INVALID` | В enum — по-прежнему возвращается при невалидном токене |
| `UrlValidationResult.RATE_LIMITED` | Оставлен в enum — не возвращается, но удаление из enum = breaking change |

### Новый `validate_url()` flow

```
validate_url(url, timeout, github_token=None)
  │
  ├── pre-check
  │   ├── hostname check → None → INVALID
  │   └── _is_private_url → True → INVALID
  │
  ├── http/https?
  │   ├── yes → HEAD(url, timeout, github_token)
  │   │   ├── 401/403 + token → TOKEN_INVALID
  │   │   ├── RequestError → url (graceful degradation)
  │   │   └── success → str(resp.url)  # final_url
  │   └── no  → url (original, no redirect resolution)
  │
  ├── _check_vcs(final_url, timeout, github_token)
  │   ├── True  → VALID
  │   ├── False → INVALID
  │   └── None  → NETWORK_ERROR
  │
  └── return UrlValidationOutput(result, final_url)
```

## Impact

- `git://`, `ssh://`, `svn://` URL проходят pre-check и достигают VCS probes
- Нет ложных INVALID от HEAD 404/403 на живых git-репозиториях
- HEAD сохраняет единственную проверку: 401/403 → TOKEN_INVALID (с token)
- Rate-limit cooldown удалён — VCS probes обрабатывают таймауты сами
- `rate_limit_cooldown` параметр удаляется из `AppSettings`, API, `validate_url()`, фронтенда
- `_git_probe` сохраняет oauth2:token rewrite (повышение rate limits для `git ls-remote` к GitHub)
- `_check_vcs` и probe-функции продолжают получать `github_token`

## Изменения в тестах

- `TestValidateUrlUsesCheckVcs`: обновить моки — `_head_request` заменён на
  `_resolve_redirects`; убрать проверки не-401/403 статус-кодов
- Тест HEAD 401/403 с токеном → TOKEN_INVALID (сохраняется существующий кейс)
- Тест HEAD 401/403 без токена → redirect resolution как обычно (не TOKEN_INVALID)
- Новые тесты для не-HTTP схем:
  - `git://github.com/user/repo.git` → VALID (с VCS mock True)
  - `ssh://git@github.com/user/repo.git` → VALID
  - `svn://svn.example.com/repo` → VALID
- Тест: `ssh://10.0.0.1/repo` → INVALID (private network)
- Удалить тесты rate-limit и не-401/403 статус-кодов из `validate_url`
- Удалить тесты `rate_limit_cooldown` из `test_url_validator.py` и `test_settings_store.py`

## Удаляемые настройки

`rate_limit_cooldown` удаляется из:

| Файл | Изменение |
|---|---|
| `settings_store.py:32` | Удалить поле `rate_limit_cooldown` из `AppSettings` |
| `routes/settings.py:50,84,150` | Удалить из `SettingsUpdate` и ответов GET/PATCH |
| `url_validator.py:377,397,430,435,448` | Удалить из сигнатур `validate_url`/`validate_url_with_retry` |
| `frontend/src/types/api.ts:44,66` | Удалить из `SettingsResponse` и `SettingsUpdate` |
| `frontend/src/stores/useSettingsStore.ts:20,48,72` | Удалить `rateLimitCooldown` ref |
| `frontend/src/views/Settings.vue:240-248` | Удалить UI-карточку "Rate-limit cooldown" |
| `frontend/src/views/Settings.test.ts:21` | Удалить тестовые данные |
| `tests/test_url_validator.py:107` | Удалить тест rate-limit |
| `tests/test_settings_store.py:39-41` | Удалить тест rate-limit |

Остальные настройки остаются актуальными:
- `validate_db_urls` — включает/выключает валидацию
- `revalidation_cooldown_hours` — `UrlValidationCache` в `validation_service.py`
- `connectivity_url`/`connectivity_timeout` — `ensure_connectivity()`
- `github_token` — передаётся в HEAD для rate limits + в `_git_probe` для rate limits

## Обновление спецификации проекта

В `specs/domains/purl-resolution.md`:

- Заменить инвариант "Non-http/https URLs are invalid immediately" на:
  "URLs are validated by syntax (non-empty hostname) and SSRF guard
  (non-private IP) before VCS probes. HTTP/HTTPS URLs additionally undergo
  redirect resolution to capture the final URL and detect invalid tokens
  (401/403). Non-HTTP/HTTPS URLs skip redirect resolution and go directly
  to VCS probes."
- Изменить сигнатуру `validate_url()`: `rate_limit_cooldown` удалён.
- Удалить описание `_RateLimitTracker` и `_rate_limit_tracker`.
- Удалить `rate_limit_cooldown` из таблицы JSON Settings.