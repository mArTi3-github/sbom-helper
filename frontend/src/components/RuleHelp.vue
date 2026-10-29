<script setup lang="ts">
import { useId } from 'vue'

defineProps<{
  ruleId: string
  description: string
  before: string
  after: string
  beforeLabel: string
  afterLabel: string
  ruleTitle: string
  open: boolean
}>()

const emit = defineEmits<{
  toggle: []
  close: []
}>()

const buttonId = useId()
const panelId = useId()
</script>

<template>
  <div class="rule-help" @keydown.esc="emit('close')">
    <button
      type="button"
      class="rule-help-button"
      :id="buttonId"
      :aria-expanded="open"
      :aria-controls="panelId"
      :aria-label="ruleTitle"
      :data-help-for="ruleId"
      @click="emit('toggle')"
    >
      i
    </button>
    <div
      v-if="open"
      class="rule-help-panel"
      :id="panelId"
      role="region"
      :aria-labelledby="buttonId"
    >
      <p class="rule-help-description">{{ description }}</p>
      <div class="rule-examples">
        <div class="rule-example">
          <span class="rule-example-label">{{ beforeLabel }}</span>
          <pre><code>{{ before }}</code></pre>
        </div>
        <div class="rule-example">
          <span class="rule-example-label">{{ afterLabel }}</span>
          <pre><code>{{ after }}</code></pre>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rule-help {
  display: contents;
}

.rule-help-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1rem;
  height: 1rem;
  font-size: 0.6rem;
  font-family: inherit;
  border-radius: 50%;
  border: 1px solid var(--color-muted-light);
  color: var(--color-muted-light);
  background: none;
  line-height: 1;
  margin-left: auto;
  cursor: pointer;
  padding: 0;
}

.rule-help-button:hover {
  color: var(--color-body-text);
  border-color: var(--color-body-text);
}

.rule-help-button:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

.rule-help-panel {
  flex-basis: 100%;
  width: 100%;
  background: var(--color-card-bg);
  border: 1px solid var(--color-row-border);
  border-radius: var(--border-radius);
  padding: 0.75rem;
  margin-top: 0.5rem;
}

.rule-help-description {
  margin: 0 0 0.75rem;
}

.rule-examples {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.rule-example-label {
  display: block;
  font-size: 0.8rem;
  color: var(--color-muted);
  margin-bottom: 0.25rem;
}

.rule-example pre {
  margin: 0;
  white-space: pre;
  overflow-x: auto;
  font-size: 0.75rem;
}

@media (max-width: 640px) {
  .rule-examples {
    grid-template-columns: 1fr;
  }
}
</style>
