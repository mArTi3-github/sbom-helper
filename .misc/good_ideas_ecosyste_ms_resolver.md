## Резолвер на основе ecosyste.ms (live-запрос)

**Проблема:** CSV-импорт из ecosyste.ms загружает данные один раз. Для пакетов, которых нет в локальной БД, нужен live-запрос.

**Решение:** Реализовать резолвер, который обращается к API ecosyste.ms для получения расширенных метаданных о пакете.

**Формат API:**
```
GET https://packages.ecosyste.ms/api/v1/packages/lookup?purl={purl}
```

**API возвращает набор URL-кандидатов:**
- `repository_url` — основной URL репозитория
- `registry_url` — URL реестра пакетов
- `homepage` — домашняя страница проекта

**Логика выбора URL (приоритет):**
```python
def select_repository_url(metadata: dict) -> str | None:
    candidates = [
        metadata.get('repository_url', ''),
        metadata.get('registry_url', ''),
        metadata.get('homepage', ''),
    ]

    for url in candidates:
        if not url or 'repos.ecosyste.ms' in url:
            continue
        if 'github.com' in url:
            return url

    for url in candidates:
        if url and 'repos.ecosyste.ms' not in url:
            return url

    return None
```

**Отличие от CSV-импорта:**
- CSV-импорт = единоразовая загрузка из дампа
- Live API = запрос в реальном времени при обогащении
- Live API полезен для пакетов, которых нет в локальной БД

**Что реализовать:**
- Новый класс резолвера, реализующий протокол `Resolver`
- Live HTTP-запрос к API ecosyste.ms (API key не требуется)
- Логика выбора URL-кандидатов (приоритет GitHub)
- Обработка таймаутов (рекомендуется 60 секунд)
- Кэширование результатов в БД для избежания повторных запросов

**Статус:** Запланировано


