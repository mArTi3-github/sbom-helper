<template>
  <div class="db-admin">
    <h1>Database Admin</h1>
    <p class="subtitle">View, edit, filter, import, and export the resolved_purls table</p>

    <DbFilterPanel />
    <DbDataTable />
    <DbImportModal />
  </div>
</template>

<script setup lang="ts">
import DbFilterPanel from '../components/db/DbFilterPanel.vue'
import DbDataTable from '../components/db/DbDataTable.vue'
import DbImportModal from '../components/db/DbImportModal.vue'
</script>

<style scoped>
.db-admin { max-width: 1400px; margin: 0 auto; padding: 2rem 1rem; flex: 1; }
h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
.subtitle { color: var(--color-muted); margin-bottom: 1.5rem; }
</style>
