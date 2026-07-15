<script setup lang="ts">
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTheme } from '../composables/useTheme'
import AppNav from './components/AppNav.vue'
const { t, locale } = useI18n()
useTheme()

watch(locale, (lang) => {
  document.documentElement.lang = lang
}, { immediate: true })
</script>

<template>
  <div class="app-layout">
    <AppNav />
    <main class="container">
      <router-view />
    </main>
    <footer class="app-footer">
      {{ t('common.githubPrefix') }}<a href="https://github.com/mArTi3-github/sbom-helper" target="_blank" rel="noopener noreferrer">sbom-helper</a>
    </footer>
  </div>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.container {
  margin: 0 auto;
  padding: 2rem 1rem;
  flex: 1;
  width: 100%;
}
.app-footer {
  text-align: center;
  padding: 1rem;
  font-size: 0.8rem;
  color: var(--color-muted-lighter);
}
.app-footer a {
  color: var(--color-primary);
  text-decoration: none;
}
.app-footer a:hover {
  color: var(--color-primary-hover);
  text-decoration: underline;
}
</style>
