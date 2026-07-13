<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
const routes = [
  { path: '/sbom-updater', nameKey: 'nav.sbomUpdater' },
  { path: '/images-list-converter', nameKey: 'nav.imagesListConverter' },
  { path: '/db-admin', nameKey: 'nav.dbAdmin' },
]
</script>

<template>
  <nav class="nav-bar">
    <router-link to="/" class="nav-logo-link">
      <img src="/logo_64x64.png" alt="" class="nav-icon" />
    </router-link>
    <div class="nav-links">
      <router-link
        to="/purl-resolver"
        class="nav-link"
        active-class="nav-link--active"
      >
        {{ t('nav.purlResolver') }}
      </router-link>
      <router-link
        v-for="route in routes"
        :key="route.path"
        :to="route.path"
        class="nav-link"
        active-class="nav-link--active"
      >
        {{ t(route.nameKey) }}
      </router-link>
    </div>
    <router-link
      to="/settings"
      class="nav-link nav-link--settings"
      active-class="nav-link--active"
    >
      {{ t('nav.settings') }}
    </router-link>
  </nav>
</template>

<style scoped>
.nav-bar {
  display: flex;
  align-items: center;
  padding: 0 2rem 0 0.75rem;
  height: 48px;
  background: var(--color-body-bg);
  border-bottom: 1px solid var(--color-card-border);
  position: relative;
}

.nav-bar::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--color-primary), var(--color-accent));
}

.nav-links {
  display: flex;
  gap: 0.25rem;
}

.nav-link {
  color: #7c7491;
  text-decoration: none;
  font-size: 0.875rem;
  padding: 0.5rem 0.75rem;
  border-radius: var(--border-radius);
  transition: color 0.15s, background 0.15s;
}

.nav-link:hover {
  color: var(--color-body-text);
  background: rgba(255, 255, 255, 0.04);
}

.nav-link--active {
  color: var(--color-body-text);
  font-weight: 600;
  background: rgba(255, 255, 255, 0.06);
}

.nav-link--settings {
  margin-left: auto;
}

.nav-logo-link {
  display: flex;
  align-items: center;
  line-height: 0;
}

.nav-icon {
  width: 32px;
  height: 32px;
  margin-right: 0.25rem;
  flex-shrink: 0;
  opacity: 0.75;
  transition: opacity 0.15s;
}

.nav-logo-link:hover .nav-icon {
  opacity: 1;
}
</style>
