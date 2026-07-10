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
