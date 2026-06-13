import { ref, computed } from 'vue'

export function usePagination() {
  const page = ref(1)
  const pageSize = ref(50)
  const total = ref(0)

  const totalPages = computed(() => Math.ceil(total.value / pageSize.value) || 1)

  function goToPage(p: number) {
    if (p < 1 || p > totalPages.value) return
    page.value = p
  }

  function changePageSize(size: number) {
    pageSize.value = size
    page.value = 1
  }

  function reset() {
    page.value = 1
  }

  return { page, pageSize, total, totalPages, goToPage, changePageSize, reset }
}