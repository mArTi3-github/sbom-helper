<template>
  <div class="db-admin">
    <h1>{{ t('dbAdmin.title') }}</h1>
    <p class="subtitle">{{ t('dbAdmin.subtitle') }}</p>

    <DbFilterPanel />
    <DbDataTable />
    <DbImportModal />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import DbFilterPanel from '../components/db/DbFilterPanel.vue'
import DbDataTable from '../components/db/DbDataTable.vue'
import DbImportModal from '../components/db/DbImportModal.vue'
const { t } = useI18n()
</script>

<style scoped>
.db-admin { max-width: 1400px; margin: 0 auto; padding: 2rem 1rem; flex: 1; }
h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
.subtitle { color: var(--color-muted); margin-bottom: 1.5rem; }
</style>
