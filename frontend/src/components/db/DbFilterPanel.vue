<template>
  <div class="card filter-panel">
    <div class="filter-row">
      <div class="filter-group">
        <label for="search">{{ t('dbAdmin.searchByPurl') }}</label>
        <input id="search" v-model="store.search" type="text" :placeholder="t('dbAdmin.searchPlaceholder')" @keyup.enter="store.applyFilters()">
      </div>
      <div class="filter-group">
        <label for="resolver">{{ t('dbAdmin.resolver') }}</label>
        <select id="resolver" v-model="store.resolver">
          <option value="">{{ t('dbAdmin.any') }}</option>
          <option v-for="r in store.resolvers" :key="r" :value="r">{{ r }}</option>
        </select>
      </div>
      <div class="filter-group">
        <label for="date-from">{{ t('dbAdmin.dateFrom') }}</label>
        <input id="date-from" v-model="store.dateFrom" type="date">
      </div>
      <div class="filter-group">
        <label for="date-to">{{ t('dbAdmin.dateTo') }}</label>
        <input id="date-to" v-model="store.dateTo" type="date">
      </div>
      <div class="filter-actions">
        <button class="btn btn-primary" @click="store.applyFilters()" :disabled="store.loading">
          <span v-if="store.loading" class="spinner"></span>
          <span v-else>{{ t('dbAdmin.apply') }}</span>
        </button>
        <button class="btn btn-secondary" @click="store.resetFilters()">{{ t('dbAdmin.reset') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDbAdminStore } from '../../stores/useDbAdminStore'
const { t } = useI18n()
const store = useDbAdminStore()
onMounted(() => { store.fetchResolvers() })
</script>

<style scoped>
.filter-panel { margin-bottom: 1rem; }
.filter-row { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: flex-end; }
.filter-group { display: flex; flex-direction: column; gap: 0.25rem; }
.filter-group label { font-size: 0.8rem; color: var(--color-muted-light); text-transform: uppercase; }
.filter-group input, .filter-group select { padding: 0.5rem; border: 1px solid var(--color-input-border); border-radius: var(--border-radius); font-size: 0.9rem; min-width: 140px; }
.filter-group input:focus, .filter-group select:focus { outline: none; border-color: var(--color-primary); }
.filter-actions { display: flex; gap: 0.5rem; align-items: flex-end; padding-bottom: 1px; }
</style>
