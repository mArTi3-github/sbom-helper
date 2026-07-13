<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()

const sections = [
  { route: '/purl-resolver', ns: 'purlResolver' },
  { route: '/sbom-updater', ns: 'sbomUpdater' },
  { route: '/images-list-converter', ns: 'imagesListConverter' },
  { route: '/db-admin', ns: 'dbAdmin' },
  { route: '/settings', ns: 'settings' },
]
</script>

<template>
  <div class="home-page">
    <section class="hero">
      <h1 class="hero-title">{{ t('common.appTitle') }}</h1>
      <p class="hero-subtitle">{{ t('home.subtitle') }}</p>
      <div class="hero-divider" />
    </section>

    <section class="tiles-grid">
      <router-link
        v-for="section in sections"
        :key="section.route"
        :to="section.route"
        class="tile"
      >
        <h2 class="tile-title">{{ t(`${section.ns}.title`) }}</h2>
        <p class="tile-desc">{{ t(`${section.ns}.subtitle`) }}</p>
      </router-link>
    </section>
  </div>
</template>

<style scoped>
.home-page {
  max-width: 960px;
  margin: 0 auto;
}

.hero {
  text-align: center;
  padding: 3rem 1rem 2rem;
}

.hero-title {
  font-size: 2.5rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin-bottom: 0.75rem;
}

.hero-subtitle {
  font-size: 1.05rem;
  color: var(--color-muted);
  max-width: 600px;
  margin: 0 auto;
  line-height: 1.6;
}

.hero-divider {
  width: 60px;
  height: 3px;
  background: var(--color-primary);
  border-radius: 2px;
  margin: 1.5rem auto 0;
}

.tiles-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 1.25rem;
  justify-content: center;
  padding: 0 1rem 3rem;
}

.tile {
  display: flex;
  flex-direction: column;
  flex: 1 1 260px;
  max-width: 360px;
  background: var(--color-card-bg);
  border: 1px solid var(--color-card-border);
  border-radius: var(--border-radius-lg);
  padding: 1.5rem;
  text-decoration: none;
  color: inherit;
  transition: background 0.2s, border-color 0.2s, box-shadow 0.2s;
}

.tile:hover {
  background: rgba(255, 255, 255, 0.03);
  border-color: var(--color-primary);
  box-shadow: 0 0 0 1px var(--color-primary);
  text-decoration: none;
}

.tile-title {
  font-size: 1.1rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: var(--color-body-text);
}

.tile-desc {
  font-size: 0.85rem;
  color: var(--color-muted);
  line-height: 1.5;
}

@media (max-width: 540px) {
  .hero-title {
    font-size: 1.75rem;
  }

  .hero {
    padding: 2rem 1rem 1.5rem;
  }
}
</style>
