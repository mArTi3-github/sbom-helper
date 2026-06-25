import { describe, it, expect } from 'vitest'
import { usePagination } from './usePagination'

describe('usePagination', () => {
  it('initial state has page 1, pageSize 50, total 0, totalPages 1', () => {
    const { page, pageSize, total, totalPages } = usePagination()
    expect(page.value).toBe(1)
    expect(pageSize.value).toBe(50)
    expect(total.value).toBe(0)
    expect(totalPages.value).toBe(1)
  })

  it('computes totalPages from total and pageSize', () => {
    const { total, totalPages } = usePagination()
    total.value = 250
    expect(totalPages.value).toBe(5)
  })

  it('totalPages is at least 1 when total is 0', () => {
    const { totalPages } = usePagination()
    expect(totalPages.value).toBe(1)
  })

  it('goToPage navigates to a valid page', () => {
    const { page, total, goToPage } = usePagination()
    total.value = 200
    goToPage(3)
    expect(page.value).toBe(3)
  })

  it('goToPage ignores pages below 1', () => {
    const { page, total, goToPage } = usePagination()
    total.value = 200
    page.value = 2
    goToPage(-1)
    expect(page.value).toBe(2)
  })

  it('goToPage ignores pages beyond totalPages', () => {
    const { page, total, goToPage } = usePagination()
    total.value = 200
    page.value = 2
    goToPage(999)
    expect(page.value).toBe(2)
  })

  it('changePageSize updates size and resets to page 1', () => {
    const { page, pageSize, changePageSize } = usePagination()
    page.value = 3
    changePageSize(100)
    expect(pageSize.value).toBe(100)
    expect(page.value).toBe(1)
  })

  it('reset returns to page 1', () => {
    const { page, reset } = usePagination()
    page.value = 5
    reset()
    expect(page.value).toBe(1)
  })
})