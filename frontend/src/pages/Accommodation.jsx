import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Hotel, MapPin, Calendar, Search, Star, Wifi, Coffee, Car, Dumbbell,
  Users, Moon, Brain, Zap, Building2, Clock, ChevronDown, ChevronUp,
  Sparkles, ShieldCheck, ExternalLink, SlidersHorizontal,
  UtensilsCrossed, Wind, Shield, Tv, ChefHat, FlameKindling,
  X, GitCompare, CheckSquare, Square, FileText, Plus, Minus,
} from 'lucide-react'
import toast from 'react-hot-toast'
import axios from '../api/client'
import Spinner from '../components/ui/Spinner'
import CityAutocomplete from '../components/ui/CityAutocomplete'
import { cn } from '../lib/cn'

// ── Amenity icon map (expanded) ────────────────────────────────
const AMENITY_ICONS = {
  wifi: Wifi, 'free wifi': Wifi, 'wi-fi': Wifi,
  breakfast: Coffee, 'free breakfast': Coffee,
  parking: Car, 'free parking': Car,
  gym: Dumbbell, fitness: Dumbbell,
  pool: Sparkles, 'swimming pool': Sparkles, spa: Sparkles,
  restaurant: UtensilsCrossed, 'room service': UtensilsCrossed,
  'air conditioning': Wind, ac: Wind, 'air-conditioned': Wind,
  security: Shield, 'cctv': Shield,
  tv: Tv, television: Tv,
  kitchen: ChefHat, 'kitchenette': ChefHat, meals: ChefHat,
  laundry: Zap, 'power backup': Zap, 'hot water': FlameKindling,
}

// ── Policy budget tiers (per night) ────────────────────────────
const POLICY_TIERS = [
  { max: 3000,  label: 'Within Budget',  cls: 'bg-emerald-600 text-white' },
  { max: 8000,  label: 'Moderate',       cls: 'bg-blue-600 text-white'    },
  { max: 15000, label: 'Premium',        cls: 'bg-amber-500 text-white'   },
  { max: Infinity, label: 'Exceeds Limit', cls: 'bg-red-600 text-white'   },
]
function policyBadge(pricePerNight) {
  if (!pricePerNight) return null
  return POLICY_TIERS.find(t => pricePerNight <= t.max)
}

// ── Amenity filter chips ────────────────────────────────────────
const AMENITY_CHIPS = ['WiFi', 'Breakfast', 'Parking', 'Gym', 'Pool']

const inputBase = 'w-full rounded-lg border border-gray-200 bg-white px-3.5 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 transition-all hover:border-gray-300 focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/15'
const inputWithIcon = 'pl-10'
const labelClass = 'mb-1 block text-[11px] font-semibold uppercase tracking-wide text-gray-500'
const errorClass = 'mt-1 text-xs text-red-600'

const INITIAL = { city: '', check_in: '', check_out: '', guests: '1', client_address: '' }

export default function Accommodation() {
  const navigate = useNavigate()
  const [form, setForm] = useState(INITIAL)
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(null)
  const [pgResults, setPgResults] = useState(null)
  const [errors, setErrors] = useState({})
  const [forcePg, setForcePg] = useState(false)
  const [showMeetingInput, setShowMeetingInput] = useState(false)
  const [compareList, setCompareList] = useState([])
  const [compareOpen, setCompareOpen] = useState(false)
  const [meetingSuggestion, setMeetingSuggestion] = useState(null)
  // { valid, distance_km, area_name, city_name } — null while unchecked, 'checking' while in-flight
  const [areaVerification, setAreaVerification] = useState(null)
  const today = new Date().toISOString().split('T')[0]

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }))

  // Called when user selects a meeting-location suggestion from the dropdown.
  // Fires one backend geocode check (place_id → coords vs. destination city coords)
  // instead of any keyword/string comparison — works for any city/area worldwide.
  const handleMeetingSelect = async (suggestion) => {
    setMeetingSuggestion(suggestion)
    setAreaVerification(null)
    const placeId = suggestion?.place_id
    const dest = form.city?.trim()
    if (!placeId || !dest) return
    setAreaVerification('checking')
    try {
      const res = await axios.get('/accommodation/verify-area', {
        params: { place_id: placeId, destination: dest },
      })
      setAreaVerification(res.data)
    } catch {
      setAreaVerification({ valid: true })   // fail-open: never block on network error
    }
  }

  // Derived: show mismatch warning only when verification returned valid=false
  const locationMismatch = areaVerification && areaVerification !== 'checking' && !areaVerification.valid
    ? areaVerification
    : null

  const days = form.check_in && form.check_out
    ? Math.max(0, Math.floor((new Date(form.check_out) - new Date(form.check_in)) / 86400000))
    : 0
  const isLongStay = days >= 5

  const reset = () => {
    setForm(INITIAL); setErrors({}); setResults(null); setPgResults(null)
    setForcePg(false); setShowMeetingInput(false); setCompareList([])
    setMeetingSuggestion(null); setAreaVerification(null)
    setSortBy('recommended'); setMaxPrice(''); setMinRating(''); setAmenityFilter([])
  }

  const handleSearch = async (e) => {
    e.preventDefault()
    const errs = {}
    if (!form.city.trim()) errs.city = 'Required'
    if (!form.check_in) errs.check_in = 'Required'
    if (!form.check_out) errs.check_out = 'Required'
    if (form.check_in && form.check_out && form.check_out <= form.check_in) errs.check_out = 'Must be after check-in'
    if (Object.keys(errs).length) { setErrors(errs); return }

    setErrors({}); setLoading(true); setResults(null); setPgResults(null); setCompareList([])

    const shouldFetchPg = isLongStay || forcePg
    try {
      const searchParams = {
        ...form,
        client_place_id: meetingSuggestion?.place_id || '',
      }
      const [hotelRes, pgRes] = await Promise.allSettled([
        axios.get('/accommodation/search', { params: searchParams }),
        shouldFetchPg
          ? axios.post('/accommodation/pg-options', {
              city: form.city,
              duration_days: days || 1,
              client_place_id: meetingSuggestion?.place_id || '',
            })
          : Promise.resolve(null),
      ])
      if (hotelRes.status === 'fulfilled') setResults(hotelRes.value.data)
      if (pgRes.status === 'fulfilled' && pgRes.value?.data) setPgResults(pgRes.value.data)
      if (hotelRes.status !== 'fulfilled' && pgRes.status !== 'fulfilled') {
        toast.error('Search failed. Please try again.')
        return
      }
      toast.success('Accommodation options loaded')
    } catch (err) {
      toast.error(err.response?.data?.error || 'Search failed')
    } finally { setLoading(false) }
  }

  const toggleCompare = (item) => {
    setCompareList((prev) => {
      const exists = prev.find(c => c.name === item.name)
      if (exists) return prev.filter(c => c.name !== item.name)
      if (prev.length >= 3) { toast.error('Max 3 items for comparison'); return prev }
      return [...prev, item]
    })
  }

  const rawHotels = Array.isArray(results?.hotels) ? results.hotels : []
  const rawPgs = Array.isArray(pgResults?.pg_options) ? pgResults.pg_options : []

  // Filters
  const [sortBy, setSortBy] = useState('recommended')
  const [maxPrice, setMaxPrice] = useState('')
  const [minRating, setMinRating] = useState('')
  const [amenityFilter, setAmenityFilter] = useState([])

  const toggleAmenityChip = (chip) => {
    setAmenityFilter(prev =>
      prev.includes(chip) ? prev.filter(c => c !== chip) : [...prev, chip]
    )
  }

  const applyFilters = (list, isPg = false) => {
    let filtered = [...list]
    if (maxPrice) {
      const cap = parseInt(maxPrice)
      if (isPg) filtered = filtered.filter(h => !h.monthly_rent || h.monthly_rent <= cap)
      else filtered = filtered.filter(h => !h.price_per_night || h.price_per_night <= cap)
    }
    if (minRating) filtered = filtered.filter(h => (h.rating || 0) >= parseFloat(minRating))
    if (amenityFilter.length > 0) {
      filtered = filtered.filter(h =>
        amenityFilter.every(chip =>
          (h.amenities || []).some(a => a.toLowerCase().includes(chip.toLowerCase()))
        )
      )
    }
    if (sortBy === 'price_low') filtered.sort((a, b) => (a.price_per_night || a.monthly_rent || 0) - (b.price_per_night || b.monthly_rent || 0))
    else if (sortBy === 'price_high') filtered.sort((a, b) => (b.price_per_night || b.monthly_rent || 0) - (a.price_per_night || a.monthly_rent || 0))
    else if (sortBy === 'rating') filtered.sort((a, b) => (b.rating || 0) - (a.rating || 0))
    return filtered
  }

  const hotelList = applyFilters(rawHotels)
  const pgList = applyFilters(rawPgs, true)
  const hasResults = rawHotels.length > 0 || rawPgs.length > 0
  const clearFilters = () => { setSortBy('recommended'); setMaxPrice(''); setMinRating(''); setAmenityFilter([]) }
  const hasActiveFilters = maxPrice || minRating || sortBy !== 'recommended' || amenityFilter.length > 0

  return (
    <div className="mx-auto w-full max-w-7xl space-y-5 pb-24">
      {/* Page Header */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-purple-600">
            <Hotel size={14} className="text-white" />
          </div>
          <h1 className="font-heading text-xl font-bold text-gray-900">Accommodation</h1>
          <span className="rounded-full bg-violet-50 border border-violet-200 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-violet-600">
            AI Search
          </span>
        </div>
        <p className="text-sm text-gray-500">Find hotels, PGs, and serviced apartments with AI-powered recommendations.</p>
      </div>

      {/* Search Form */}
      <form onSubmit={handleSearch} className="rounded-xl border border-gray-200 bg-white shadow-card overflow-hidden">
        <div className="border-b border-gray-100 bg-gray-50/50 px-5 py-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900">Search Stays</h3>
            <button type="button" onClick={reset}
              className="rounded-lg border border-gray-200 bg-white px-2.5 py-1 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50">
              Reset
            </button>
          </div>
        </div>

        <div className="space-y-3 p-4">
          {/* Destination */}
          <Field label="Destination" error={errors.city}>
            <CityAutocomplete
              value={form.city}
              onChange={(v) => set('city', v)}
              placeholder="Enter city or area"
              error={!!errors.city}
            />
          </Field>

          {/* Dates + Guests */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Field label="Check-in" error={errors.check_in}>
              <input type="date" className={inputBase} min={today}
                value={form.check_in} onChange={(e) => set('check_in', e.target.value)} />
            </Field>
            <Field label="Check-out" error={errors.check_out}>
              <input type="date" className={inputBase} min={form.check_in || today}
                value={form.check_out} onChange={(e) => set('check_out', e.target.value)} />
            </Field>
            <Field label="Guests">
              <div className="relative">
                <Users size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input type="number" min="1" max="10" className={cn(inputBase, inputWithIcon)}
                  placeholder="1" value={form.guests} onChange={(e) => set('guests', e.target.value)} />
              </div>
            </Field>
            <Field label="Nights">
              <input className={cn(inputBase, 'cursor-default bg-gray-50 text-center')} readOnly
                value={days > 0 ? `${days}` : '—'} />
            </Field>
          </div>

          {/* Near Meeting toggle */}
          <div>
            <button type="button"
              onClick={() => setShowMeetingInput(v => !v)}
              className="flex items-center gap-1.5 text-[11px] font-medium text-violet-600 hover:text-violet-700 transition-colors">
              {showMeetingInput ? <Minus size={11} /> : <Plus size={11} />}
              Near a meeting location?
            </button>
            {showMeetingInput && (
              <div className="mt-2 space-y-2">
                <CityAutocomplete
                  value={form.client_address}
                  onChange={(v) => { set('client_address', v); if (!v) { setMeetingSuggestion(null); setAreaVerification(null) } }}
                  onSelect={handleMeetingSelect}
                  placeholder={form.city ? `Area or landmark in ${form.city}` : 'Client address or landmark'}
                  restrictToCity={form.city}
                  placeSearch
                />
                {/* Coordinate-based location check — no keyword matching */}
                {areaVerification === 'checking' && (
                  <p className="text-[11px] text-gray-400 pl-1">Verifying location…</p>
                )}
                {locationMismatch && (
                  <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
                    <span className="mt-px text-amber-500">⚠</span>
                    <p className="text-[11px] text-gray-700 leading-snug">
                      <span className="font-semibold text-amber-700">{form.client_address}</span> is{' '}
                      <span className="font-semibold text-amber-700">{locationMismatch.distance_km} km</span> from{' '}
                      <span className="font-semibold">{form.city}</span> — this looks like a different city.
                      Please enter an area or landmark within <span className="font-semibold">{form.city}</span>.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Long stay badge + PG toggle */}
          <div className="flex flex-wrap items-center gap-2">
            {isLongStay && (
              <div className="flex items-center gap-2 rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 flex-1">
                <Building2 size={13} className="text-violet-600" />
                <span className="text-xs font-medium text-violet-700">
                  Long stay detected — PG options auto-included
                </span>
              </div>
            )}
            {!isLongStay && (
              <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 bg-gray-50/50 px-3 py-2">
                <input type="checkbox" checked={forcePg} onChange={e => setForcePg(e.target.checked)}
                  className="h-3.5 w-3.5 rounded border-gray-300 text-violet-600 focus:ring-violet-500" />
                <Building2 size={12} className="text-gray-500" />
                <span className="text-xs font-medium text-gray-600">Include serviced apartments / PG options</span>
              </label>
            )}
          </div>

          {/* Submit */}
          <button type="submit" disabled={loading}
            className="flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-violet-600 to-purple-500 text-sm font-semibold text-white shadow-sm transition-all hover:shadow-md hover:brightness-105 disabled:opacity-60 disabled:cursor-not-allowed">
            {loading ? (
              <><Spinner size="xs" color="white" /> Searching...</>
            ) : (
              <><Search size={14} /> {isLongStay || forcePg ? 'Search Hotels & Apartments' : 'Search Hotels'}</>
            )}
          </button>
        </div>
      </form>

      {/* Results */}
      <div className="space-y-4">
        {loading && <LoadingState isLongStay={isLongStay || forcePg} />}
        {!loading && !results && !pgResults && <EmptyState />}

        {/* AI Recommendation */}
        {!loading && results?.recommendation && (
          <div className="flex gap-3 rounded-xl border border-violet-200 bg-violet-50 px-4 py-3.5 shadow-card">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-violet-100 border border-violet-200">
              <Brain size={14} className="text-violet-600" />
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wide text-violet-700 mb-1">AI Recommendation</p>
              <p className="text-sm text-gray-700 leading-relaxed">{results.recommendation}</p>
            </div>
          </div>
        )}

        {/* Filter Bar */}
        {!loading && hasResults && (
          <div className="rounded-xl border border-gray-200 bg-white shadow-card p-3 space-y-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold text-gray-500 mr-1">Sort & Filter:</span>

              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}
                className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-violet-500/15 focus:border-violet-500 appearance-none">
                <option value="recommended">Recommended</option>
                <option value="price_low">Price: Low to High</option>
                <option value="price_high">Price: High to Low</option>
                <option value="rating">Highest Rated</option>
              </select>

              <div className="relative">
                <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[10px] text-gray-400">₹</span>
                <input type="number" placeholder="Max budget" value={maxPrice}
                  onChange={(e) => setMaxPrice(e.target.value)}
                  className="w-28 rounded-lg border border-gray-200 bg-white py-1.5 pl-6 pr-2 text-xs text-gray-700 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-violet-500/15 focus:border-violet-500" />
              </div>

              <select value={minRating} onChange={(e) => setMinRating(e.target.value)}
                className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-violet-500/15 focus:border-violet-500 appearance-none">
                <option value="">Any Rating</option>
                <option value="4.5">4.5+ Excellent</option>
                <option value="4">4.0+ Very Good</option>
                <option value="3.5">3.5+ Good</option>
                <option value="3">3.0+ Average</option>
              </select>

              <span className="ml-auto text-[11px] text-gray-400">
                {hotelList.length + pgList.length} of {rawHotels.length + rawPgs.length} results
              </span>

              {hasActiveFilters && (
                <button onClick={clearFilters}
                  className="rounded-lg border border-gray-200 px-2.5 py-1.5 text-[10px] font-medium text-gray-500 hover:bg-gray-50">
                  Clear
                </button>
              )}
            </div>

            {/* Amenity chips */}
            <div className="flex flex-wrap gap-1.5">
              {AMENITY_CHIPS.map((chip) => {
                const active = amenityFilter.includes(chip)
                const Icon = AMENITY_ICONS[chip.toLowerCase()] || null
                return (
                  <button key={chip} type="button"
                    onClick={() => toggleAmenityChip(chip)}
                    className={cn(
                      'flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-semibold transition-all',
                      active
                        ? 'bg-violet-100 border-violet-300 text-violet-700'
                        : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300'
                    )}>
                    {Icon && <Icon size={9} />} {chip}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {!loading && (results || pgResults) && (
          <div className="space-y-5 animate-fade-in">
            {/* Long stay / forced PG: PG first */}
            {(isLongStay || forcePg) && pgList.length > 0 && (
              <ResultSection icon={Building2} title="Serviced Apartments & PG" count={pgList.length} accent="emerald" badge="Best Value">
                <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">
                  {pgList.map((pg, i) => (
                    <PGCard key={i} pg={pg} form={form}
                      compareList={compareList} onCompare={toggleCompare}
                      navigate={navigate} />
                  ))}
                </div>
              </ResultSection>
            )}

            {/* Hotels */}
            {hotelList.length > 0 && (
              <ResultSection icon={Hotel}
                title={isLongStay || forcePg ? 'Hotels (Alternative)' : 'Hotels'}
                count={hotelList.length} accent="violet">
                <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">
                  {hotelList.map((hotel, i) => (
                    <HotelCard key={i} hotel={hotel} nights={days} form={form}
                      compareList={compareList} onCompare={toggleCompare}
                      navigate={navigate} />
                  ))}
                </div>
              </ResultSection>
            )}

            {/* Short stay: PG at bottom if not forced */}
            {!isLongStay && !forcePg && pgList.length > 0 && (
              <ResultSection icon={Building2} title="PG / Serviced Apartments" count={pgList.length} accent="emerald" badge="Long Stay">
                <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">
                  {pgList.map((pg, i) => (
                    <PGCard key={i} pg={pg} form={form}
                      compareList={compareList} onCompare={toggleCompare}
                      navigate={navigate} />
                  ))}
                </div>
              </ResultSection>
            )}

            {hotelList.length === 0 && pgList.length === 0 && hasResults && (
              <div className="rounded-xl border border-gray-200 bg-white p-8 text-center shadow-card">
                <Hotel size={24} className="mx-auto mb-2 text-gray-300" />
                <p className="text-sm font-medium text-gray-700">No matches for your filters</p>
                <p className="mt-1 text-xs text-gray-500">Try adjusting budget, rating, or amenity filters.</p>
                <button onClick={clearFilters}
                  className="mt-3 rounded-lg border border-gray-200 px-4 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50">
                  Clear Filters
                </button>
              </div>
            )}

            {hotelList.length === 0 && pgList.length === 0 && !hasResults && (
              <div className="rounded-xl border border-gray-200 bg-white p-8 text-center shadow-card">
                <Hotel size={24} className="mx-auto mb-2 text-gray-300" />
                <p className="text-sm font-medium text-gray-700">No results found</p>
                <p className="mt-1 text-xs text-gray-500">Try a different city or date range.</p>
              </div>
            )}

            {results?.source && (
              <div className="flex items-center justify-center gap-2">
                <span className={cn('h-1.5 w-1.5 rounded-full', results.source === 'fallback' ? 'bg-amber-400' : 'bg-green-400')} />
                <span className="text-[11px] text-gray-400">
                  {results.source === 'fallback' ? 'Demo data — add Amadeus API key for live results' : 'Live data from Amadeus'}
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Compare floating bar ───────────────────────────────── */}
      {compareList.length >= 2 && (
        <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-gray-200 bg-white shadow-2xl">
          <div className="mx-auto flex max-w-7xl items-center gap-3 px-5 py-3">
            <GitCompare size={15} className="shrink-0 text-violet-600" />
            <div className="flex flex-1 flex-wrap gap-2">
              {compareList.map((item) => (
                <span key={item.name}
                  className="flex items-center gap-1.5 rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-[11px] font-semibold text-violet-700">
                  {item.name}
                  <button onClick={() => toggleCompare(item)} className="text-violet-400 hover:text-violet-700">
                    <X size={10} />
                  </button>
                </span>
              ))}
            </div>
            <button onClick={() => setCompareOpen(true)}
              className="flex shrink-0 items-center gap-1.5 rounded-xl bg-gradient-to-r from-violet-600 to-purple-500 px-4 py-2 text-xs font-semibold text-white hover:brightness-105 transition-all">
              <GitCompare size={13} /> Compare ({compareList.length})
            </button>
            <button onClick={() => setCompareList([])} className="shrink-0 text-gray-400 hover:text-gray-600">
              <X size={16} />
            </button>
          </div>
        </div>
      )}

      {/* ── Compare Drawer ─────────────────────────────────────── */}
      {compareOpen && (
        <CompareDrawer items={compareList} onClose={() => setCompareOpen(false)} nights={days} />
      )}
    </div>
  )
}

// ── Field wrapper ───────────────────────────────────────────────
function Field({ label, error, children }) {
  return (
    <div>
      <label className={labelClass}>{label}</label>
      {children}
      {error && <p className={errorClass}>{error}</p>}
    </div>
  )
}

// ── Loading State ───────────────────────────────────────────────
function LoadingState({ isLongStay }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-8 shadow-card sm:p-12">
      <div className="flex flex-col items-center text-center">
        <div className="relative">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-purple-600 shadow-lg shadow-violet-500/25">
            <Brain size={28} className="text-white animate-pulse" />
          </div>
        </div>
        <h3 className="mt-5 font-heading text-lg font-bold text-gray-900">Finding the best stays</h3>
        <p className="mt-1 text-sm text-gray-500">Searching across multiple providers...</p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {['Hotels', 'Ratings', 'Prices', isLongStay && 'Apartments'].filter(Boolean).map((s, i) => (
            <span key={s} className="rounded-full bg-gray-50 border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600"
              style={{ animation: `pulse 2s ease-in-out ${i * 0.3}s infinite` }}>
              {s}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Empty State ─────────────────────────────────────────────────
function EmptyState() {
  return (
    <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50/50 p-8 sm:p-14">
      <div className="flex flex-col items-center text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-gray-100 to-gray-200">
          <Hotel size={28} className="text-gray-400" />
        </div>
        <h3 className="mt-4 font-heading text-lg font-semibold text-gray-700">Search for accommodation</h3>
        <p className="mt-1 max-w-sm text-sm text-gray-500">
          Enter a destination and dates to discover hotels, PGs, and serviced apartments.
        </p>
        <div className="mt-6 grid grid-cols-3 gap-3">
          {[
            { icon: Hotel, label: 'Hotels' },
            { icon: Building2, label: 'PG Stays' },
            { icon: ShieldCheck, label: 'Policy Aware' },
          ].map((f) => (
            <div key={f.label} className="flex flex-col items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-4 py-3">
              <f.icon size={18} className="text-gray-400" />
              <span className="text-[11px] font-medium text-gray-500">{f.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Result Section ──────────────────────────────────────────────
function ResultSection({ icon: Icon, title, count, accent, badge, children }) {
  const [expanded, setExpanded] = useState(true)
  const accents = {
    violet:  { icon: 'bg-violet-50 text-violet-600 border-violet-100',   badge: 'bg-violet-100 text-violet-700' },
    emerald: { icon: 'bg-emerald-50 text-emerald-600 border-emerald-100', badge: 'bg-emerald-100 text-emerald-700' },
  }
  const a = accents[accent] || accents.violet
  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-card">
      <button type="button" onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-3 border-b border-gray-100 px-5 py-3.5 text-left transition-colors hover:bg-gray-50/50">
        <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border ${a.icon}`}>
          <Icon size={15} />
        </div>
        <h4 className="flex-1 text-sm font-semibold text-gray-900">{title}</h4>
        {badge && <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${a.badge}`}>{badge}</span>}
        {count > 0 && <span className="text-xs text-gray-400">{count} found</span>}
        {expanded ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
      </button>
      {expanded && children}
    </div>
  )
}

// ── Hotel Card ──────────────────────────────────────────────────
function HotelCard({ hotel: h, nights, form, compareList, onCompare, navigate }) {
  // Try each photo URL in sequence — only show placeholder when all fail
  const photoUrls = (h.photo_urls?.length ? h.photo_urls : (h.photo_url ? [h.photo_url] : []))
  const [photoIdx, setPhotoIdx] = useState(0)
  const currentPhoto = photoUrls[photoIdx] || null
  const allFailed = !currentPhoto

  const total = h.price_per_night && nights ? h.price_per_night * nights : null
  const stars = h.stars ? Math.min(h.stars, 5) : 0
  const reviewCount = h.user_ratings_total || 0
  const policy = policyBadge(h.price_per_night)
  const isCompared = compareList.some(c => c.name === h.name)

  const handleImgError = () => {
    if (photoIdx < photoUrls.length - 1) {
      setPhotoIdx(i => i + 1)   // try next reference
    } else {
      setPhotoIdx(photoUrls.length)  // exhaust list → show placeholder
    }
  }

  return (
    <article className={cn(
      'group overflow-hidden rounded-xl border bg-white transition-all hover:shadow-lg',
      isCompared ? 'border-violet-400 ring-2 ring-violet-500/30' : 'border-gray-200 hover:border-gray-300'
    )}>
      {/* Photo */}
      <div className="relative h-40 w-full overflow-hidden bg-gradient-to-br from-violet-50 to-indigo-100">
        {!allFailed ? (
          <img
            key={currentPhoto}
            src={currentPhoto}
            alt={h.name}
            loading="lazy"
            onError={handleImgError}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/60 backdrop-blur-sm">
              <Hotel size={22} className="text-violet-400" />
            </div>
            <p className="max-w-[140px] text-center text-[10px] font-medium leading-tight text-violet-400 line-clamp-2">
              {h.name}
            </p>
          </div>
        )}

        {/* Stars overlay */}
        {stars > 0 && (
          <div className="absolute top-2 left-2 flex items-center gap-0.5 rounded-md bg-black/60 px-2 py-1 backdrop-blur-sm">
            {Array.from({ length: stars }).map((_, i) => (
              <Star key={i} size={10} className="fill-amber-400 text-amber-400" />
            ))}
          </div>
        )}

        {/* Policy badge */}
        {policy && (
          <div className={`absolute bottom-2 left-2 rounded-md px-2 py-0.5 text-[9px] font-bold ${policy.cls}`}>
            {policy.label}
          </div>
        )}

        {/* Rating */}
        {h.rating && (
          <div className="absolute top-2 right-10 rounded-md bg-emerald-600 px-2 py-1 text-xs font-bold text-white">
            {h.rating}
          </div>
        )}

        {/* Compare checkbox */}
        <button type="button" onClick={() => onCompare({ ...h, _type: 'hotel' })}
          className={cn(
            'absolute top-2 right-2 flex h-6 w-6 items-center justify-center rounded-md transition-colors',
            isCompared ? 'bg-violet-600 text-white' : 'bg-black/40 text-white hover:bg-violet-600'
          )}
          title={isCompared ? 'Remove from compare' : 'Add to compare'}>
          {isCompared ? <CheckSquare size={12} /> : <Square size={12} />}
        </button>
      </div>

      <div className="p-4">
        <h4 className="text-sm font-semibold text-gray-900 group-hover:text-violet-700 transition-colors line-clamp-1">
          {h.name || h.hotel_name}
        </h4>

        {(h.location || h.area || h.address) && (
          <p className="mt-1 flex items-center gap-1 text-xs text-gray-500 line-clamp-1">
            <MapPin size={10} className="shrink-0 text-gray-400" /> {h.location || h.area || h.address}
          </p>
        )}

        {/* Distance from meeting location — shown only when meeting pin is set */}
        {h.distance_from_meeting && (
          <p className="mt-1 flex items-center gap-1 text-[10px] font-medium text-violet-600">
            <MapPin size={9} className="shrink-0 text-violet-400" />
            {h.distance_from_meeting}
          </p>
        )}

        <div className="mt-2 flex items-center gap-2">
          {h.rating && (
            <span className="rounded bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 text-[10px] font-bold text-emerald-700">
              {h.rating} / 5
            </span>
          )}
          {reviewCount > 0 && (
            <span className="text-[10px] text-gray-400">{reviewCount.toLocaleString()} reviews</span>
          )}
        </div>

        {h.amenities?.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {h.amenities.slice(0, 4).map((a) => {
              const Icon = AMENITY_ICONS[a.toLowerCase()] || null
              return (
                <span key={a} className="flex items-center gap-0.5 rounded bg-gray-50 border border-gray-100 px-1.5 py-0.5 text-[9px] font-medium text-gray-500">
                  {Icon && <Icon size={9} />} {a}
                </span>
              )
            })}
          </div>
        )}

        <div className="mt-3 flex items-end justify-between border-t border-gray-100 pt-3">
          <div>
            {h.price_per_night && (
              <span className="text-lg font-bold text-gray-900">
                ₹{typeof h.price_per_night === 'number' ? h.price_per_night.toLocaleString('en-IN') : h.price_per_night}
              </span>
            )}
            <span className="text-[10px] text-gray-400 ml-1">/night</span>
          </div>
          {total && (
            <div className="text-right">
              <p className="text-xs font-semibold text-gray-700">₹{total.toLocaleString('en-IN')} total</p>
              <p className="text-[9px] text-gray-400">{nights} night{nights !== 1 ? 's' : ''}</p>
            </div>
          )}
        </div>

        {/* Booking Platforms */}
        <div className="mt-3 space-y-2">
          {h.booking_platforms && h.booking_platforms.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {h.booking_platforms.map((p, i) => (
                <a key={i} href={p.url} target="_blank" rel="noreferrer"
                  className={cn(
                    'flex h-7 items-center gap-1 rounded-md px-2.5 text-[10px] font-semibold transition-colors',
                    p.type === 'direct' ? 'bg-violet-600 text-white hover:bg-violet-700' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  )}>
                  {p.name} <ExternalLink size={8} />
                </a>
              ))}
              <a href={h.maps_url || '#'} target="_blank" rel="noreferrer"
                className="flex h-7 items-center gap-1 rounded-md border border-gray-200 px-2.5 text-[10px] font-medium text-gray-500 hover:bg-gray-50">
                <MapPin size={9} /> Map
              </a>
            </div>
          ) : (
            <div className="flex gap-1.5">
              <a href={h.google_search_url || '#'} target="_blank" rel="noreferrer"
                className="flex h-8 flex-1 items-center justify-center gap-1.5 rounded-lg bg-violet-600 text-[11px] font-semibold text-white hover:bg-violet-700">
                Check Prices <ExternalLink size={10} />
              </a>
              <a href={h.maps_url || '#'} target="_blank" rel="noreferrer"
                className="flex h-8 items-center justify-center gap-1.5 rounded-lg border border-gray-200 px-3 text-[11px] font-medium text-gray-700 hover:bg-gray-50">
                <MapPin size={10} /> Map
              </a>
            </div>
          )}

          {/* Request This Stay */}
          <button type="button"
            onClick={() => navigate('/requests', {
              state: {
                prefill: {
                  to_city: form.city,
                  travel_date: form.check_in,
                  return_date: form.check_out,
                  accommodation_name: h.name,
                  accommodation_price: h.price_per_night,
                }
              }
            })}
            className="flex h-8 w-full items-center justify-center gap-1.5 rounded-lg border border-violet-200 text-[11px] font-semibold text-violet-600 hover:bg-violet-50 transition-colors">
            <FileText size={11} /> Request This Stay
          </button>
        </div>

        {h.price_source === 'ai_estimated' && (
          <p className="mt-1.5 text-[9px] text-gray-400">Estimated price. Check platforms for live rates.</p>
        )}
      </div>
    </article>
  )
}

// ── PG Card ─────────────────────────────────────────────────────
function PGCard({ pg, form, compareList, onCompare, navigate }) {
  const photoUrls = (pg.photo_urls?.length ? pg.photo_urls : (pg.photo_url ? [pg.photo_url] : []))
  const [photoIdx, setPhotoIdx] = useState(0)
  const currentPhoto = photoUrls[photoIdx] || null
  const allFailed = !currentPhoto

  const dailyEquiv = pg.monthly_rent ? Math.round(pg.monthly_rent / 30) : null
  const policy = policyBadge(dailyEquiv)
  const isCompared = compareList.some(c => c.name === pg.name)

  const handleImgError = () => {
    if (photoIdx < photoUrls.length - 1) {
      setPhotoIdx(i => i + 1)
    } else {
      setPhotoIdx(photoUrls.length)
    }
  }

  return (
    <article className={cn(
      'group overflow-hidden rounded-xl border bg-white transition-all hover:shadow-lg',
      isCompared ? 'border-emerald-400 ring-2 ring-emerald-500/30' : 'border-gray-200 hover:border-gray-300'
    )}>
      {/* Photo / Brand header */}
      <div className="relative h-36 w-full overflow-hidden bg-gradient-to-br from-emerald-500 to-teal-600">
        {!allFailed ? (
          <img
            key={currentPhoto}
            src={currentPhoto}
            alt={pg.name}
            loading="lazy"
            onError={handleImgError}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/20 backdrop-blur-sm">
              <Building2 size={22} className="text-white/80" />
            </div>
            <p className="max-w-[140px] text-center text-[10px] font-medium leading-tight text-white/70 line-clamp-2">
              {pg.name}
            </p>
          </div>
        )}

        <div className="absolute top-2 left-2 rounded-md bg-emerald-600 px-2 py-1 text-[10px] font-bold text-white uppercase">
          {pg.type || 'PG'}
        </div>

        {/* Policy badge */}
        {policy && (
          <div className={`absolute bottom-2 left-2 rounded-md px-2 py-0.5 text-[9px] font-bold ${policy.cls}`}>
            {policy.label}
          </div>
        )}

        {pg.rating && (
          <div className="absolute top-2 right-10 rounded-md bg-black/60 px-2 py-1 text-xs font-bold text-white backdrop-blur-sm">
            {pg.rating}
          </div>
        )}

        {/* Compare checkbox */}
        <button type="button" onClick={() => onCompare({ ...pg, _type: 'pg' })}
          className={cn(
            'absolute top-2 right-2 flex h-6 w-6 items-center justify-center rounded-md transition-colors',
            isCompared ? 'bg-emerald-600 text-white' : 'bg-black/40 text-white hover:bg-emerald-600'
          )}
          title={isCompared ? 'Remove from compare' : 'Add to compare'}>
          {isCompared ? <CheckSquare size={12} /> : <Square size={12} />}
        </button>
      </div>

      <div className="p-4">
        <h4 className="text-sm font-semibold text-gray-900 group-hover:text-emerald-700 transition-colors line-clamp-1">
          {pg.name}
        </h4>
        {(pg.location || pg.area) && (
          <p className="mt-1 flex items-center gap-1 text-xs text-gray-500 line-clamp-1">
            <MapPin size={10} className="shrink-0 text-gray-400" /> {pg.location || pg.area}
          </p>
        )}

        {/* Distance from meeting location — shown only when meeting pin is set */}
        {pg.distance_from_meeting && (
          <p className="mt-1 flex items-center gap-1 text-[10px] font-medium text-emerald-600">
            <MapPin size={9} className="shrink-0 text-emerald-400" />
            {pg.distance_from_meeting}
          </p>
        )}

        {pg.rating && (
          <div className="mt-2 flex items-center gap-2">
            <span className="rounded bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 text-[10px] font-bold text-emerald-700">{pg.rating} / 5</span>
            {pg.user_ratings_total > 0 && <span className="text-[10px] text-gray-400">{pg.user_ratings_total} reviews</span>}
          </div>
        )}

        {pg.amenities?.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {pg.amenities.slice(0, 4).map((a) => {
              const Icon = AMENITY_ICONS[a.toLowerCase()] || null
              return (
                <span key={a} className="flex items-center gap-0.5 rounded bg-gray-50 border border-gray-100 px-1.5 py-0.5 text-[9px] font-medium text-gray-500">
                  {Icon && <Icon size={9} />} {a}
                </span>
              )
            })}
          </div>
        )}

        <div className="mt-3 border-t border-gray-100 pt-3">
          {pg.monthly_rent && (
            <div>
              <span className="text-lg font-bold text-gray-900">
                ₹{typeof pg.monthly_rent === 'number' ? pg.monthly_rent.toLocaleString('en-IN') : pg.monthly_rent}
              </span>
              <span className="text-[10px] text-gray-400 ml-1">/month</span>
              {dailyEquiv && <span className="ml-2 text-[10px] text-gray-400">≈ ₹{dailyEquiv.toLocaleString('en-IN')}/night</span>}
            </div>
          )}
          {pg.price_per_night && !pg.monthly_rent && (
            <div>
              <span className="text-lg font-bold text-gray-900">₹{typeof pg.price_per_night === 'number' ? pg.price_per_night.toLocaleString('en-IN') : pg.price_per_night}</span>
              <span className="text-[10px] text-gray-400 ml-1">/night</span>
            </div>
          )}
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {pg.booking_platforms && pg.booking_platforms.length > 0 ? (
            pg.booking_platforms.map((p, i) => (
              <a key={i} href={p.url} target="_blank" rel="noreferrer"
                className={cn(
                  'flex h-7 items-center gap-1 rounded-md px-2.5 text-[10px] font-semibold transition-colors',
                  p.type === 'direct' ? 'bg-emerald-600 text-white hover:bg-emerald-700' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                )}>
                {p.name} <ExternalLink size={8} />
              </a>
            ))
          ) : (
            <a href={`https://www.google.com/search?q=${encodeURIComponent(pg.name + ' ' + (pg.location || '') + ' rent booking')}`}
              target="_blank" rel="noreferrer"
              className="flex h-7 items-center gap-1 rounded-md bg-emerald-600 px-2.5 text-[10px] font-semibold text-white hover:bg-emerald-700">
              Enquire <ExternalLink size={8} />
            </a>
          )}
          {pg.maps_url && (
            <a href={pg.maps_url} target="_blank" rel="noreferrer"
              className="flex h-7 items-center gap-1 rounded-md border border-gray-200 px-2.5 text-[10px] font-medium text-gray-500 hover:bg-gray-50">
              <MapPin size={9} /> Map
            </a>
          )}
        </div>

        {/* Request This Stay */}
        <button type="button"
          onClick={() => navigate('/requests', {
            state: {
              prefill: {
                to_city: form.city,
                travel_date: form.check_in,
                return_date: form.check_out,
                accommodation_name: pg.name,
                accommodation_price: pg.monthly_rent || pg.price_per_night,
              }
            }
          })}
          className="mt-2 flex h-8 w-full items-center justify-center gap-1.5 rounded-lg border border-emerald-200 text-[11px] font-semibold text-emerald-600 hover:bg-emerald-50 transition-colors">
          <FileText size={11} /> Request This Stay
        </button>

        {pg.price_source === 'ai_estimated' && (
          <p className="mt-1.5 text-[9px] text-gray-400">Estimated rent. Contact for exact pricing.</p>
        )}
      </div>
    </article>
  )
}

// ── Compare Drawer ───────────────────────────────────────────────
const COMPARE_ROWS = [
  { label: 'Type',     get: (i) => i._type === 'pg' ? (i.type || 'PG') : `${i.stars || '?'}★ Hotel` },
  { label: 'Rating',   get: (i) => i.rating ? `${i.rating} / 5` : '—' },
  { label: 'Location', get: (i) => i.location || i.area || i.address || '—' },
  { label: 'Price',    get: (i) => i.price_per_night
      ? `₹${Number(i.price_per_night).toLocaleString('en-IN')}/night`
      : i.monthly_rent
        ? `₹${Number(i.monthly_rent).toLocaleString('en-IN')}/month`
        : '—' },
  { label: 'Policy',   get: (i) => {
      const price = i.price_per_night || (i.monthly_rent ? Math.round(i.monthly_rent / 30) : null)
      return policyBadge(price)?.label || '—'
    }
  },
  { label: 'Amenities', get: (i) => (i.amenities || []).slice(0, 5).join(', ') || '—' },
]

function CompareDrawer({ items, onClose, nights }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-4xl max-h-[85vh] overflow-y-auto rounded-2xl border border-gray-200 bg-white shadow-2xl">
        {/* Header */}
        <div className="sticky top-0 flex items-center justify-between border-b border-gray-100 bg-white px-5 py-4 z-10">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-100">
              <GitCompare size={14} className="text-violet-600" />
            </div>
            <h3 className="text-sm font-semibold text-gray-900">Compare Options</h3>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Name row */}
        <div className={`grid gap-4 border-b border-gray-100 bg-gray-50/50 px-5 py-4`}
          style={{ gridTemplateColumns: `160px repeat(${items.length}, 1fr)` }}>
          <div />
          {items.map((item, i) => (
            <div key={i} className="text-center">
              <div className={cn(
                'mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-xl',
                item._type === 'pg' ? 'bg-emerald-100' : 'bg-violet-100'
              )}>
                {item._type === 'pg' ? <Building2 size={18} className="text-emerald-600" /> : <Hotel size={18} className="text-violet-600" />}
              </div>
              <p className="text-xs font-bold text-gray-900 line-clamp-2">{item.name}</p>
            </div>
          ))}
        </div>

        {/* Comparison rows */}
        <div className="divide-y divide-gray-100 px-5">
          {COMPARE_ROWS.map(({ label, get }) => (
            <div key={label} className="grid items-start gap-4 py-3.5"
              style={{ gridTemplateColumns: `160px repeat(${items.length}, 1fr)` }}>
              <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 pt-0.5">{label}</span>
              {items.map((item, i) => {
                const val = get(item)
                const isPolicy = label === 'Policy'
                const pBadge = isPolicy ? policyBadge(item.price_per_night || (item.monthly_rent ? Math.round(item.monthly_rent / 30) : null)) : null
                return (
                  <div key={i} className="text-center">
                    {isPolicy && pBadge ? (
                      <span className={`inline-block rounded-full px-2.5 py-0.5 text-[10px] font-bold ${pBadge.cls}`}>
                        {pBadge.label}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-700">{val}</span>
                    )}
                  </div>
                )
              })}
            </div>
          ))}
        </div>

        {/* Footer CTA */}
        <div className="border-t border-gray-100 bg-gray-50/50 px-5 py-3 flex justify-end gap-2">
          <button onClick={onClose}
            className="rounded-lg border border-gray-200 px-4 py-2 text-xs font-medium text-gray-600 hover:bg-gray-100 transition-colors">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
