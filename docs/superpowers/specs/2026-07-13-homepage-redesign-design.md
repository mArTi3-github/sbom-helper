# Homepage Redesign — Design Spec

**Date:** 2026-07-13
**Status:** Draft
**Author:** Kilo (AI)

## Summary

Replace the current landing page (PURL Resolver at `/`) with a proper homepage featuring a hero section and a grid of navigation tiles for all 5 application sections. Move PURL Resolver to its own route `/purl-resolver`.

## Motivation

The current landing page jumps directly into PURL resolution without giving the user an overview of the application's capabilities. A dedicated homepage with section tiles helps new users discover all available tools and provides a clear starting point.

## Design

### Hero Section

- **Title:** «sbom-helper» (`t('common.appTitle')`)
- **Subtitle:** "SBOM enrichment toolkit — resolve Package URLs, enrich CycloneDX SBOMs, manage your resolved PURL database." (localized via new i18n key `home.subtitle`)
- **Decoration:** thin horizontal accent line below the title in `--color-primary`
- **Layout:** centered, with generous vertical spacing

### Tiles Grid

A responsive grid of `<router-link>` cards, one per application section:

| Section | i18n namespace | Route |
|---|---|---|
| PURL Resolver | `purlResolver` | `/purl-resolver` |
| SBOM Updater | `sbomUpdater` | `/sbom-updater` |
| Images List Converter | `imagesListConverter` | `/images-list-converter` |
| Database Admin | `dbAdmin` | `/db-admin` |
| Settings | `settings` | `/settings` |

Each tile displays:
- **Title** (`t('{ns}.title')`) — e.g. "PURL Resolver"
- **Subtitle** (`t('{ns}.subtitle')`) — e.g. "Resolve a Package URL to its source code repository"
- Whole card is a clickable `<router-link>`

**Breakpoints:**
- ≥960px: 3 columns (2nd row centered: 2 tiles centered)
- ≥640px: 2 columns
- <640px: 1 column

**Hover effect:** subtle background lightening + left border highlight in `--color-primary`

### Navigation Changes

- `AppNav.vue`: PURL Resolver link target changes from `/` to `/purl-resolver`
- `common.goHome` i18n: "Go to PURL Resolver" → "Go to Home" (EN), "На главную (PURL Resolver)" → "На главную" (RU)

### Router Changes

| Path | Current | New |
|---|---|---|
| `/` | `PurlResolver.vue` | `HomePage.vue` (new) |
| `/purl-resolver` | — (not found / 404) | `PurlResolver.vue` |
| `/settings` | `Settings.vue` | unchanged |
| `/images-list-converter` | `ImagesListConverter.vue` | unchanged |
| `/sbom-updater` | `SbomUpdater.vue` | unchanged |
| `/db-admin` | `DatabaseAdmin.vue` | unchanged |
| `/:pathMatch(.*)*` | `NotFound.vue` | unchanged |

### i18n Additions

**en.json:**
```json
{
  "home": {
    "subtitle": "SBOM enrichment toolkit — resolve Package URLs, enrich CycloneDX SBOMs, manage your resolved PURL database."
  },
  "common": {
    "goHome": "Go to Home"
  }
}
```

**ru.json:**
```json
{
  "home": {
    "subtitle": "Инструменты для обогащения SBOM — определяйте репозитории по Package URL, обогащайте CycloneDX SBOM, управляйте базой resolved PURL"
  },
  "common": {
    "goHome": "На главную"
  }
}
```

### Error / Empty / Loading States

Not applicable — all content is static and synchronous.

### Testing

- New test file `views/HomePage.test.ts`:
  - renders the hero title and subtitle
  - renders all 5 navigation tiles with correct labels
  - each tile links to the correct route

### Out of Scope

- Icons/illustrations on tiles (deferred)
- Animated backgrounds or particle effects
- Live statistics or dynamic content on homepage
- Changes to section page content

## Implementation Steps

1. Add `home.subtitle` to both locale files
2. Update `common.goHome` in both locale files
3. Create `views/HomePage.vue` with hero + tile grid
4. Update `router/index.ts`: `/` → HomePage, add `/purl-resolver` → PurlResolver
5. Update `AppNav.vue`: PURL Resolver link → `/purl-resolver`
6. Create `views/HomePage.test.ts`
7. Verify with `npm run typecheck` and `npm run test`
