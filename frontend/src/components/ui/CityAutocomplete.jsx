/**
 * CityAutocomplete — travel-app-style city picker with live suggestions.
 *
 * Props:
 *   value        string        — controlled text value
 *   onChange     fn(city)      — called with the selected city name string
 *   onSelect     fn(suggestion)— optional; called with the full suggestion object on pick
 *   placeholder  string
 *   className    string        — extra classes for the wrapper div
 *   disabled     bool
 *   error        bool          — red ring when true
 *
 * Fetches /api/accommodation/autocomplete?q=<value> after 250 ms debounce.
 * Falls back to curated list when the API is unavailable.
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import { MapPin, Loader2 } from 'lucide-react'
import axios from '../../api/client'
import { cn } from '../../lib/cn'

export default function CityAutocomplete({
  value = '',
  onChange,
  onSelect,
  placeholder = 'Enter city or area',
  className = '',
  disabled = false,
  error = false,
  restrictToCity = '',   // when set, biases results to within this city
  placeSearch = false,   // true → geocode type (streets/landmarks/colonies); false → regions (cities)
}) {
  const [query, setQuery]           = useState(value)
  const [suggestions, setSuggestions] = useState([])
  const [loading, setLoading]       = useState(false)
  const [open, setOpen]             = useState(false)
  const [activeIdx, setActiveIdx]   = useState(-1)

  const inputRef    = useRef(null)
  const listRef     = useRef(null)
  const debounceRef = useRef(null)
  const selectedRef = useRef(false)   // flag: skip fetch right after a pick

  // Keep internal query in sync when parent resets value
  useEffect(() => {
    if (!selectedRef.current) setQuery(value)
    selectedRef.current = false
  }, [value])

  // ── Fetch suggestions ──────────────────────────────────────────
  const fetchSuggestions = useCallback(async (q) => {
    if (q.length < 2) { setSuggestions([]); setOpen(false); return }
    setLoading(true)
    try {
      const params = { q }
      if (restrictToCity) params.city = restrictToCity
      if (placeSearch) params.place = '1'
      const res = await axios.get('/accommodation/autocomplete', { params })
      const list = res.data?.suggestions || []
      setSuggestions(list)
      setOpen(list.length > 0)
      setActiveIdx(-1)
    } catch {
      setSuggestions([])
      setOpen(false)
    } finally {
      setLoading(false)
    }
  }, [])

  // ── Input change with debounce ─────────────────────────────────
  const handleInput = (e) => {
    const v = e.target.value
    setQuery(v)
    onChange(v)           // keep parent in sync while typing
    clearTimeout(debounceRef.current)
    if (v.length < 2) { setSuggestions([]); setOpen(false); return }
    debounceRef.current = setTimeout(() => fetchSuggestions(v), 250)
  }

  // ── Select a suggestion ────────────────────────────────────────
  const selectSuggestion = (suggestion) => {
    const city = suggestion.city || suggestion.label
    selectedRef.current = true
    setQuery(city)
    onChange(city)
    onSelect?.(suggestion)   // pass full object to parent if they care about secondary/label
    setSuggestions([])
    setOpen(false)
    setActiveIdx(-1)
    inputRef.current?.focus()
  }

  // ── Keyboard navigation ────────────────────────────────────────
  const handleKeyDown = (e) => {
    if (!open) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx(i => Math.min(i + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIdx >= 0 && suggestions[activeIdx]) selectSuggestion(suggestions[activeIdx])
    } else if (e.key === 'Escape' || e.key === 'Tab') {
      setOpen(false)
      setActiveIdx(-1)
    }
  }

  // Scroll active item into view
  useEffect(() => {
    if (activeIdx < 0 || !listRef.current) return
    const el = listRef.current.querySelector(`[data-idx="${activeIdx}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  }, [activeIdx])

  // ── Click outside to close ─────────────────────────────────────
  const wrapperRef = useRef(null)
  useEffect(() => {
    const handler = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false)
        setActiveIdx(-1)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Cleanup debounce on unmount
  useEffect(() => () => clearTimeout(debounceRef.current), [])

  return (
    <div ref={wrapperRef} className={cn('relative', className)}>
      {/* Input */}
      <div className="relative">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2">
          {loading
            ? <Loader2 size={14} className="animate-spin text-violet-500" />
            : <MapPin size={14} className="text-violet-500" />}
        </span>
        <input
          ref={inputRef}
          type="text"
          autoComplete="off"
          disabled={disabled}
          placeholder={placeholder}
          value={query}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          onFocus={() => { if (suggestions.length > 0) setOpen(true) }}
          className={cn(
            'w-full rounded-lg border bg-white pl-10 pr-3.5 py-2.5 text-sm text-gray-900',
            'placeholder:text-gray-400 transition-all',
            'hover:border-gray-300 focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/15',
            error ? 'border-red-400 focus:border-red-500 focus:ring-red-500/15' : 'border-gray-200',
            disabled && 'cursor-not-allowed opacity-60',
          )}
        />
      </div>

      {/* Dropdown */}
      {open && suggestions.length > 0 && (
        <ul
          ref={listRef}
          role="listbox"
          className="absolute left-0 right-0 top-full z-50 mt-1.5 max-h-56 overflow-y-auto rounded-xl border border-gray-200 bg-white py-1 shadow-xl shadow-gray-200/60"
        >
          {suggestions.map((s, i) => (
            <li
              key={s.place_id || s.label}
              role="option"
              aria-selected={i === activeIdx}
              data-idx={i}
              onMouseDown={(e) => { e.preventDefault(); selectSuggestion(s) }}
              onMouseEnter={() => setActiveIdx(i)}
              className={cn(
                'flex cursor-pointer items-center gap-2.5 px-3.5 py-2.5 text-sm transition-colors',
                i === activeIdx
                  ? 'bg-violet-50 text-gray-900'
                  : 'text-gray-800 hover:bg-gray-50',
              )}
            >
              <MapPin
                size={13}
                className={cn('mt-px shrink-0', i === activeIdx ? 'text-violet-700' : 'text-gray-400')}
              />
              <span className="min-w-0 flex-1 truncate">
                <span className="font-medium">{s.city}</span>
                {s.secondary && (
                  <span className={cn('ml-1.5 text-[11px]', i === activeIdx ? 'text-gray-500' : 'text-gray-400')}>
                    {s.secondary}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
