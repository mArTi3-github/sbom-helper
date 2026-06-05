## Резолвер на основе libraries.io

**Проблема:** purl2repo не находит репозитории для некоторых экосистем. Нужен дополнительный источник данных.

**Решение:** Реализовать резолвер, который обращается к API libraries.io для поиска URL репозиториев.

**Формат API:**
```
GET https://libraries.io/api/{Platform}/{packageName}?api_key={key}
```

**Маппинг экосистем:**
| Префикс PURL | Платформа libraries.io |
|---|---|
| `pkg:nuget/` | NuGet |
| `pkg:npm/` | NPM |
| `pkg:pypi/` | PyPI |
| `pkg:gem/` | RubyGems |
| `pkg:golang/` | Go |
| `pkg:maven/` | Maven |
| `pkg:cargo/` | Cargo |

**Логика маппинга PURL → platform:**
```python
ECOSYSTEM_MAP = {
    'nuget': 'NuGet',
    'npm': 'NPM',
    'pypi': 'PyPI',
    'gem': 'RubyGems',
    'golang': 'Go',
    'maven': 'Maven',
    'cargo': 'Cargo',
}

def purl_type_to_librariesio(purl_type: str) -> str | None:
    return ECOSYSTEM_MAP.get(purl_type)
```

**Что реализовать:**
- Новый класс резолвера, реализующий протокол `Resolver`
- Поле `librariesio_api_key` в настройках
- Маппинг PURL type → libraries.io platform name
- Ограничение частоты запросов (1 секунда между запросами)
- Поведение fallback: сначала purl2repo, затем libraries.io

**Rate limit:** 60 запросов/мин (с API key)

