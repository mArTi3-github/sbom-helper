<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
const routes = [
  { path: '/', nameKey: 'nav.purlResolver' },
  { path: '/sbom-updater', nameKey: 'nav.sbomUpdater' },
  { path: '/db-admin', nameKey: 'nav.dbAdmin' },
  { path: '/settings', nameKey: 'nav.settings' },
  { path: '/images-list-converter', nameKey: 'nav.imagesListConverter' },
]
</script>

<template>
  <nav class="nav-bar">
    <router-link
      v-for="route in routes"
      :key="route.path"
      :to="route.path"
      class="nav-link"
      active-class="nav-link--active"
    >
      {{ t(route.nameKey) }}
    </router-link>
  </nav>
</template>

<style scoped>
.nav-bar {
  display: flex;
  gap: 1rem;
  padding: 1rem 2rem;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
  flex-wrap: wrap;
}
.nav-link {
  color: #2563eb;
  text-decoration: none;
  font-size: 0.9rem;
}
.nav-link:hover {
  text-decoration: underline;
}
.nav-link--active {
  color: inherit;
  font-weight: 600;
  text-decoration: none;
}
</style>
