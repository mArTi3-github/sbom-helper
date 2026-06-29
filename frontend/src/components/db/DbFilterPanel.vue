<template>
  <div class="card filter-panel">
    <div class="filter-row">
      <div class="filter-group">
        <label for="search">Search by PURL</label>
        <input id="search" v-model="store.search" type="text" placeholder="e.g. requests" @keyup.enter="store.applyFilters()">
      </div>
      <div class="filter-group">
        <label for="resolver">Resolver</label>
        <select id="resolver" v-model="store.resolver">
          <option value="">Any</option>
          <option value="purl2repo">purl2repo</option>
        </select>
      </div>
      <div class="filter-group">
        <label for="confidence">Confidence</label>
        <select id="confidence" v-model="store.confidence">
          <option value="">Any</option>
          <option value="high">high</option>
          <option value="medium">medium</option>
          <option value="low">low</option>
        </select>
      </div>
      <div class="filter-group">
        <label for="date-from">Date From</label>
        <input id="date-from" v-model="store.dateFrom" type="date">
      </div>
      <div class="filter-group">
        <label for="date-to">Date To</label>
        <input id="date-to" v-model="store.dateTo" type="date">
      </div>
      <div class="filter-actions">
        <button class="btn btn-primary" @click="store.applyFilters()" :disabled="store.loading">
          <span v-if="store.loading" class="spinner"></span>
          <span v-else>Apply</span>
        </button>
        <button class="btn btn-secondary" @click="store.resetFilters()">Reset</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useDbAdminStore } from '../../stores/useDbAdminStore'
const store = useDbAdminStore()
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
