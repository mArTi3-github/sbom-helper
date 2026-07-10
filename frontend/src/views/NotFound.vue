<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
</script>

<template>
  <div class="card" style="text-align: center;">
    <h2>404</h2>
    <p>{{ t('common.pageNotFound') }}</p>
    <router-link to="/" style="color: #2563eb;">{{ t('common.goHome') }}</router-link>
  </div>
</template>