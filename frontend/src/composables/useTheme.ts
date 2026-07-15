import { ref, watch } from 'vue'

const theme = ref<'dark' | 'light'>(
  localStorage.getItem('theme') === 'light' ? 'light' : 'dark'
)

watch(theme, (val) => {
  document.documentElement.classList.toggle('light-theme', val === 'light')
  localStorage.setItem('theme', val)
}, { immediate: true })

export function useTheme() {
  return { theme }
}

/** @internal — reset theme state for test isolation */
export function resetThemeState() {
  theme.value = 'dark'
}
