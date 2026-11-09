<template>
  <div class="card backup-help-card">
    <details class="backup-help" data-role="db-backup-help">
      <summary>{{ t('dbAdmin.backupHelp.title') }}</summary>
      <div class="backup-help-content">
        <p>{{ t('dbAdmin.backupHelp.intro') }}</p>

        <p>{{ t('dbAdmin.backupHelp.backup') }}</p>
        <pre><code>./scripts/db_backup.sh</code></pre>

        <p>{{ t('dbAdmin.backupHelp.restore') }}</p>
        <pre><code>./scripts/db_restore.sh backups/sbom_purls_YYYYMMDD-HHMMSS.csv.gz</code></pre>

        <p>{{ t('dbAdmin.backupHelp.replace') }}</p>
        <pre><code>./scripts/db_restore.sh backups/sbom_purls_YYYYMMDD-HHMMSS.csv.gz --mode replace --yes</code></pre>

        <p class="backup-help-note">{{ t('dbAdmin.backupHelp.note') }}</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<style scoped>
.backup-help-card {
  margin-top: 1.5rem;
}

.backup-help summary {
  cursor: pointer;
  color: var(--color-primary);
  font-size: 0.95rem;
  font-weight: 600;
}

.backup-help-content {
  margin-top: 0.75rem;
  font-size: 0.85rem;
  color: var(--color-muted);
}

.backup-help-content p {
  margin: 0.5rem 0;
}

.backup-help-content pre {
  background: var(--color-table-header-bg);
  padding: 0.75rem;
  border-radius: var(--border-radius);
  overflow-x: auto;
  font-size: 0.82rem;
  margin-top: 0.25rem;
}

.backup-help-note {
  font-style: italic;
}
</style>
