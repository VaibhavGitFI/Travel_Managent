import { useState, useEffect, useCallback, useRef } from 'react'

/**
 * Manages page/search/loading/fetch for paginated API endpoints.
 * @param {(params: {page, per_page, search}) => Promise<{items, total, page, per_page, total_pages}>} fetchFn
 * @param {object} options
 * @param {number} options.perPage - Items per page (default 20)
 */
export default function usePagination(fetchFn, { perPage = 20 } = {}) {
  const [items, setItems] = useState([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  const debounceRef = useRef(null)
  const fetchRef = useRef(fetchFn)
  fetchRef.current = fetchFn

  const fetch = useCallback(async (p, s) => {
    setLoading(true)
    try {
      const data = await fetchRef.current({ page: p, per_page: perPage, search: s })
      setItems(data.items || data.requests || data.expenses || data.meetings || [])
      setTotal(data.total || 0)
      setTotalPages(data.total_pages || 1)
      setPage(data.page || p)
    } catch {
      // Keep existing items on error
    } finally {
      setLoading(false)
    }
  }, [perPage])

  // Initial load
  useEffect(() => {
    fetch(1, '')
  }, [fetch])

  const goToPage = useCallback((p) => {
    const target = Math.max(1, Math.min(p, totalPages))
    fetch(target, search)
  }, [fetch, search, totalPages])

  const handleSearch = useCallback((value) => {
    setSearch(value)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setPage(1)
      fetch(1, value)
    }, 400)
  }, [fetch])

  const refresh = useCallback(() => {
    fetch(page, search)
  }, [fetch, page, search])

  useEffect(() => {
    return () => clearTimeout(debounceRef.current)
  }, [])

  return {
    items,
    page,
    totalPages,
    total,
    search,
    loading,
    goToPage,
    setSearch: handleSearch,
    refresh,
  }
}
