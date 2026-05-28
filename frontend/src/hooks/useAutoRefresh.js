import { useEffect, useRef } from 'react'
import useStore from '../store/useStore'

/**
 * Auto-refresh data when a socket `data_changed` event marks the key as stale.
 * @param {string} key - One of: requests, meetings, expenses, approvals, analytics
 * @param {() => void} fetchFn - Function to call to refresh data
 */
export default function useAutoRefresh(key, fetchFn) {
  const isStale = useStore((s) => s.staleData[key])
  const clearStale = useStore((s) => s.clearStale)
  const fetchRef = useRef(fetchFn)
  fetchRef.current = fetchFn

  useEffect(() => {
    if (!isStale) return
    clearStale(key)
    fetchRef.current()
  }, [isStale, key, clearStale])
}
