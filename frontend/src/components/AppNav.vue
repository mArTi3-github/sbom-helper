<script setup lang="ts">
const routes = [
  { path: '/', name: 'PURL Resolver' },
  { path: '/sbom-updater', name: 'SBOM Updater' },
  { path: '/db-admin', name: 'Database Admin' },
  { path: '/settings', name: 'Settings' },
  { path: '/images-list-converter', name: 'Images List Converter' },
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
      {{ route.name }}
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
