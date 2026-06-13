<script setup lang="ts">
import AppNav from './components/AppNav.vue'
</script>

<template>
  <div class="app-layout">
    <AppNav />
    <main class="container">
      <router-view />
    </main>
    <footer class="app-footer">Powered by sbom-helper</footer>
  </div>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.container {
  max-width: 960px;
  margin: 0 auto;
  padding: 2rem 1rem;
  flex: 1;
  width: 100%;
}
.app-footer {
  text-align: center;
  padding: 1rem;
  color: #999;
  font-size: 0.8rem;
}
</style>
