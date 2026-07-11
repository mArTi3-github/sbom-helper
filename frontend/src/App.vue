<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppNav from './components/AppNav.vue'
const { t } = useI18n()
</script>

<template>
  <div class="app-layout">
    <AppNav />
    <main class="container">
      <router-view />
    </main>
    <footer class="app-footer">
      {{ t('common.poweredBy') }}
      <img src="/favicon.png" alt="" class="footer-icon"  style="opacity: 0.75" />
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
  color: var(--color-muted-lighter);
  font-size: 0.8rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
}
.footer-icon {
  width: 20px;
  height: 20px;
}
</style>
