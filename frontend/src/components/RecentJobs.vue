<template>
  <div class="recent-jobs">
    <div class="recent-jobs-title">{{ t('recentJobs.title') }}</div>
    <div v-if="jobs.length === 0" class="empty-state">{{ t('recentJobs.empty') }}</div>
    <div v-for="job in jobs" :key="job.job_id"
      :class="['job-row', { 'job-active': job.job_id === activeId }]"
      @click="$emit('select', job.job_id)">
      <span :class="['job-status-icon', 'status-' + job.status]">
        <template v-if="job.status === 'queued'">⏳</template>
        <template v-else-if="job.status === 'running'">🔄</template>
        <template v-else-if="job.status === 'completed'">✅</template>
        <template v-else-if="job.status === 'failed'">❌</template>
        <template v-else-if="job.status === 'cancelled'">🚫</template>
      </span>
      <span class="job-filename">{{ job.input_filename || job.job_id }}</span>
      <span class="job-time">{{ formatTime(job.created_at) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { JobRecord } from '../types/api'

const props = defineProps<{
  jobs: JobRecord[]
  activeId: string | null
}>()

const emit = defineEmits<{
  select: [jobId: string]
}>()

const { t } = useI18n()

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString()
}
</script>

<style scoped>
.recent-jobs {
  border: 1px solid var(--color-card-border);
  border-radius: var(--border-radius-lg);
  background: var(--color-card-bg);
  box-shadow: var(--color-card-shadow);
}

.recent-jobs-title {
  font-size: 0.75rem;
  text-transform: uppercase;
  color: var(--color-muted-light);
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--color-card-border);
}

.empty-state {
  padding: 1rem;
  color: var(--color-muted);
  font-size: 0.9rem;
  text-align: center;
}

.job-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1rem;
  cursor: pointer;
  border-bottom: 1px solid var(--color-row-border);
  transition: background-color 0.15s ease;
}

.job-row:last-child {
  border-bottom: none;
}

.job-row:hover {
  background: var(--color-table-header-bg);
}

.job-row.job-active {
  background: var(--color-primary);
  color: #fff;
}

.job-row.job-active .job-time {
  color: rgba(255, 255, 255, 0.75);
}

.job-status-icon {
  flex-shrink: 0;
  font-size: 1rem;
  line-height: 1;
}

.job-filename {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.9rem;
}

.job-time {
  flex-shrink: 0;
  font-size: 0.8rem;
  color: var(--color-muted-light);
}
</style>
