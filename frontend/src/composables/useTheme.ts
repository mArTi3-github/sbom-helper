import { ref } from 'vue'

const theme = ref<'dark' | 'light'>(
  localStorage.getItem('theme') === 'light' ? 'light' : 'dark'
)

export function useTheme() {
  return { theme }
}
