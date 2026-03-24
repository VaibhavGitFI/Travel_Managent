import { useState } from 'react'
import {
  Hotel, MapPin, Calendar, Search, Star, Wifi, Coffee, Car, Dumbbell,
  Users, Moon, Brain, Zap, Building2, Clock, ChevronDown, ChevronUp,
  Sparkles, ShieldCheck, ExternalLink, SlidersHorizontal,
} from 'lucide-react'
import toast from 'react-hot-toast'
import axios from '../api/client'
import Spinner from '../components/ui/Spinner'
import { cn } from '../lib/cn'

const AMENITY_ICONS = {
  wifi: Wifi, breakfast: Coffee, parking: Car, gym: Dumbbell,
  'free wifi': Wifi, 'free parking': Car, pool: Sparkles, spa: Sparkles,
}

const inputBase = 'w-full rounded-lg border border-gray-200 bg-white px-3.5 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 transition-all hover:border-gray-300 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/15'
const inputWithIcon = 'pl-10'
const labelClass = 'mb-1 block text-[11px] font-semibold uppercase tracking-wide text-gray-500'
const errorClass = 'mt-1 text-xs text-red-600'

const INITIAL = { city: '', check_in: '', check_out: '', guests: '1' }

export default function Accommodation() {
  const [form, setForm] = useState(INITIAL)
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(null)
  const [pgResults, setPgResults] = useState(null)
  const [errors, setErrors] = useState({})
  const today = new Date().toISOString().split('T')[0]

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }))

  const days = form.check_in && form.check_out
    ? Math.max(0, Math.floor((new Date(form.check_out) - new Date(form.check_in)) / 86400000))
    : 0
  const isLongStay = days >= 5

  const reset = () => { setForm(INITIAL); setErrors({}); setResults(null); setPgResults(null) }

  const handleSearch = async (e) => {
    e.preventDefault()
    const errs = {}
    if (!form.city.trim()) errs.city = 'Required'
    if (!form.check_in) errs.check_in = 'Required'
    if (!form.check_out) errs.check_out = 'Required'
    if (form.check_in && form.check_out && form.check_out <= form.check_in) errs.check_out = 'Must be after check-in'
    if (Object.keys(errs).length) { setErrors(errs); return }

    setErrors({}); setLoading(true); setResults(null); setPgResults(null)

    try {
      const [hotelRes, pgRes] = await Promise.allSettled([
        axios.get('/accommodation/search', { params: form }),
        isLongStay ? axios.post('/accommodation/pg-options', { city: form.city, duration_days: days || 1 }) : Promise.resolve(null),
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

  const rawHotels = Array.isArray(results?.hotels) ? results.hotels : []
  const rawPgs = Array.isArray(pgResults?.pg_options) ? pgResults.pg_options : []

  // Filters
  const [sortBy, setSortBy] = useState('recommended')
  const [maxPrice, setMaxPrice] = useState('')
  const [minRating, setMinRating] = useState('')

  const applyFilters = (list, isPg = false) => {
    let filtered = [...list]
    // Price filter
    if (maxPrice) {
      const cap = parseInt(maxPrice)
      if (isPg) {
        filtered = filtered.filter(h => !h.monthly_rent || h.monthly_rent <= cap)
      } else {
        filtered = filtered.filter(h => !h.price_per_night || h.price_per_night <= cap)
      }
    }
    // Rating filter
    if (minRating) {
      filtered = filtered.filter(h => (h.rating || 0) >= parseFloat(minRating))
    }
    // Sort
    if (sortBy === 'price_low') {
      filtered.sort((a, b) => (a.price_per_night || a.monthly_rent || 0) - (b.price_per_night || b.monthly_rent || 0))
    } else if (sortBy === 'price_high') {
      filtered.sort((a, b) => (b.price_per_night || b.monthly_rent || 0) - (a.price_per_night || a.monthly_rent || 0))
    } else if (sortBy === 'rating') {
      filtered.sort((a, b) => (b.rating || 0) - (a.rating || 0))
    }
    return filtered
  }

  const hotelList = applyFilters(rawHotels)
  const pgList = applyFilters(rawPgs, true)
  const hasResults = rawHotels.length > 0 || rawPgs.length > 0

  return (
    <div className="mx-auto w-full max-w-7xl space-y-5">
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

      {/* Search Form — compact */}
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
          {/* Row 1: City */}
          <Field label="Destination" error={errors.city}>
            <div className="relative">
              <MapPin size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-violet-500" />
              <input className={cn(inputBase, inputWithIcon)} placeholder="Enter city or area"
                value={form.city} onChange={(e) => set('city', e.target.value)} />
            </div>
          </Field>

          {/* Row 2: Dates + Guests — all in one row on desktop */}
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

          {/* Long stay badge — only when relevant */}
          {isLongStay && (
            <div className="flex items-center gap-2 rounded-lg border border-violet-200 bg-violet-50 px-3 py-2">
              <Building2 size={13} className="text-violet-600" />
              <span className="text-xs font-medium text-violet-700">
                Long stay detected — PG and serviced apartment options will be included
              </span>
            </div>
          )}

          {/* Submit */}
          <button type="submit" disabled={loading}
            className="flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-violet-600 to-purple-500 text-sm font-semibold text-white shadow-sm transition-all hover:shadow-md hover:brightness-105 disabled:opacity-60 disabled:cursor-not-allowed">
            {loading ? (
              <><Spinner size="xs" color="white" /> Searching...</>
            ) : (
              <><Search size={14} /> {isLongStay ? 'Search Hotels & PG' : 'Search Hotels'}</>
            )}
          </button>
        </div>
      </form>

      {/* Results */}
      <div className="space-y-4">
        {loading && <LoadingState isLongStay={isLongStay} />}

        {!loading && !results && !pgResults && <EmptyState />}

        {/* Filter Bar */}
        {!loading && hasResults && (
          <div className="rounded-xl border border-gray-200 bg-white shadow-card p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold text-gray-500 mr-1">Filters:</span>

              {/* Sort */}
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}
                className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-violet-500/15 focus:border-violet-500 appearance-none">
                <option value="recommended">Recommended</option>
                <option value="price_low">Price: Low to High</option>
                <option value="price_high">Price: High to Low</option>
                <option value="rating">Highest Rated</option>
              </select>

              {/* Max Budget */}
              <div className="relative">
                <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[10px] text-gray-400">₹</span>
                <input type="number" placeholder="Max budget" value={maxPrice}
                  onChange={(e) => setMaxPrice(e.target.value)}
                  className="w-28 rounded-lg border border-gray-200 bg-white py-1.5 pl-6 pr-2 text-xs text-gray-700 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-violet-500/15 focus:border-violet-500" />
              </div>

              {/* Min Rating */}
              <select value={minRating} onChange={(e) => setMinRating(e.target.value)}
                className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-violet-500/15 focus:border-violet-500 appearance-none">
                <option value="">Any Rating</option>
                <option value="4.5">4.5+ Excellent</option>
                <option value="4">4.0+ Very Good</option>
                <option value="3.5">3.5+ Good</option>
                <option value="3">3.0+ Average</option>
              </select>

              {/* Results count */}
              <span className="ml-auto text-[11px] text-gray-400">
                {hotelList.length + pgList.length} of {rawHotels.length + rawPgs.length} results
              </span>

              {/* Clear */}
              {(maxPrice || minRating || sortBy !== 'recommended') && (
                <button onClick={() => { setSortBy('recommended'); setMaxPrice(''); setMinRating('') }}
                  className="rounded-lg border border-gray-200 px-2.5 py-1.5 text-[10px] font-medium text-gray-500 hover:bg-gray-50">
                  Clear
                </button>
              )}
            </div>
          </div>
        )}

        {!loading && (results || pgResults) && (
          <div className="space-y-5 animate-fade-in">
            {/* Long stay (5+ nights): PG first, then hotels */}
            {isLongStay && pgList.length > 0 && (
              <ResultSection icon={Building2} title="Recommended for Long Stay" count={pgList.length} accent="emerald" badge="Best Value">
                <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">
                  {pgList.map((pg, i) => <PGCard key={i} pg={pg} />)}
                </div>
              </ResultSection>
            )}

            {/* Hotels */}
            {hotelList.length > 0 && (
              <ResultSection icon={Hotel} title={isLongStay ? 'Hotels (Alternative)' : 'Hotels'} count={hotelList.length} accent="violet">
                <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">
                  {hotelList.map((hotel, i) => <HotelCard key={i} hotel={hotel} nights={days} />)}
                </div>
              </ResultSection>
            )}

            {/* Short stay: PG at bottom if any */}
            {!isLongStay && pgList.length > 0 && (
              <ResultSection icon={Building2} title="PG / Serviced Apartments" count={pgList.length} accent="emerald" badge="Long Stay">
                <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">
                  {pgList.map((pg, i) => <PGCard key={i} pg={pg} />)}
                </div>
              </ResultSection>
            )}

            {/* No results after filter */}
            {hotelList.length === 0 && pgList.length === 0 && hasResults && (
              <div className="rounded-xl border border-gray-200 bg-white p-8 text-center shadow-card">
                <Hotel size={24} className="mx-auto mb-2 text-gray-300" />
                <p className="text-sm font-medium text-gray-700">No matches for your filters</p>
                <p className="mt-1 text-xs text-gray-500">Try adjusting budget or rating filters.</p>
                <button onClick={() => { setSortBy('recommended'); setMaxPrice(''); setMinRating('') }}
                  className="mt-3 rounded-lg border border-gray-200 px-4 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50">
                  Clear Filters
                </button>
              </div>
            )}

            {/* No results at all */}
            {hotelList.length === 0 && pgList.length === 0 && !hasResults && (
              <div className="rounded-xl border border-gray-200 bg-white p-8 text-center shadow-card">
                <Hotel size={24} className="mx-auto mb-2 text-gray-300" />
                <p className="text-sm font-medium text-gray-700">No results found</p>
                <p className="mt-1 text-xs text-gray-500">Try a different city or date range.</p>
              </div>
            )}

            {/* Source indicator */}
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
    </div>
  )
}

// ── Field wrapper ───────────────────────────────────────────
function Field({ label, error, children }) {
  return (
    <div>
      <label className={labelClass}>{label}</label>
      {children}
      {error && <p className={errorClass}>{error}</p>}
    </div>
  )
}

// ── Loading State ───────────────────────────────────────────
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
          {['Hotels', 'Ratings', 'Prices', isLongStay && 'PG Options'].filter(Boolean).map((s, i) => (
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

// ── Empty State ─────────────────────────────────────────────
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
            { icon: ShieldCheck, label: 'Verified' },
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

// ── Result Section ──────────────────────────────────────────
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

// ── Hotel Card ──────────────────────────────────────────────
function HotelCard({ hotel: h, nights }) {
  const total = h.price_per_night && nights ? h.price_per_night * nights : null
  const stars = h.stars ? Math.min(h.stars, 5) : 0
  const reviewCount = h.user_ratings_total || 0

  return (
    <article className="group overflow-hidden rounded-xl border border-gray-200 bg-white transition-all hover:border-gray-300 hover:shadow-lg">
      {/* Photo */}
      {h.photo_url ? (
        <div className="relative h-40 w-full overflow-hidden bg-gray-100">
          <img src={h.photo_url} alt={h.name} loading="lazy"
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105" />
          {stars > 0 && (
            <div className="absolute top-2 left-2 flex items-center gap-0.5 rounded-md bg-black/60 px-2 py-1 backdrop-blur-sm">
              {Array.from({ length: stars }).map((_, i) => (
                <Star key={i} size={10} className="fill-amber-400 text-amber-400" />
              ))}
            </div>
          )}
          {h.rating && (
            <div className="absolute top-2 right-2 rounded-md bg-emerald-600 px-2 py-1 text-xs font-bold text-white">
              {h.rating}
            </div>
          )}
        </div>
      ) : (
        <div className="flex h-28 w-full items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100">
          <Hotel size={28} className="text-gray-300" />
        </div>
      )}

      <div className="p-4">
        {/* Name */}
        <h4 className="text-sm font-semibold text-gray-900 group-hover:text-violet-700 transition-colors line-clamp-1">
          {h.name || h.hotel_name}
        </h4>

        {/* Location */}
        {(h.location || h.area || h.address) && (
          <p className="mt-1 flex items-center gap-1 text-xs text-gray-500 line-clamp-1">
            <MapPin size={10} className="shrink-0 text-gray-400" /> {h.location || h.area || h.address}
          </p>
        )}

        {/* Rating + Reviews */}
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

        {/* Amenities */}
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

        {/* Price */}
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
                    p.type === 'direct'
                      ? 'bg-violet-600 text-white hover:bg-violet-700'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
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
        </div>
        {h.price_source === 'ai_estimated' && (
          <p className="mt-1.5 text-[9px] text-gray-400">Estimated price. Check platforms for live rates.</p>
        )}
      </div>
    </article>
  )
}

// ── PG Card ─────────────────────────────────────────────────
function PGCard({ pg }) {
  return (
    <article className="group overflow-hidden rounded-xl border border-gray-200 bg-white transition-all hover:border-gray-300 hover:shadow-lg">
      {/* Photo / Brand header */}
      {pg.photo_url ? (
        <div className="relative h-36 w-full overflow-hidden bg-gray-100">
          <img src={pg.photo_url} alt={pg.name} loading="lazy"
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
            onError={(e) => { e.target.style.display = 'none'; e.target.parentElement.classList.add('brand-fallback') }} />
          <div className="absolute top-2 left-2 rounded-md bg-emerald-600 px-2 py-1 text-[10px] font-bold text-white uppercase">
            {pg.type || 'PG'}
          </div>
          {pg.rating && (
            <div className="absolute top-2 right-2 rounded-md bg-black/60 px-2 py-1 text-xs font-bold text-white backdrop-blur-sm">
              {pg.rating}
            </div>
          )}
        </div>
      ) : (
        <div className="relative flex h-28 w-full items-center justify-center bg-gradient-to-br from-emerald-500 to-teal-600">
          <div className="text-center">
            <Building2 size={24} className="mx-auto text-white/60" />
            <p className="mt-1 text-[10px] font-bold text-white/80 uppercase tracking-wider">{pg.type || 'PG'}</p>
          </div>
        </div>
      )}

      <div className="p-4">
        <h4 className="text-sm font-semibold text-gray-900 group-hover:text-emerald-700 transition-colors line-clamp-1">
          {pg.name}
        </h4>
        {(pg.location || pg.area) && (
          <p className="mt-1 flex items-center gap-1 text-xs text-gray-500 line-clamp-1">
            <MapPin size={10} className="shrink-0 text-gray-400" /> {pg.location || pg.area}
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
            {pg.amenities.slice(0, 4).map((a) => (
              <span key={a} className="rounded bg-gray-50 border border-gray-100 px-1.5 py-0.5 text-[9px] font-medium text-gray-500">{a}</span>
            ))}
          </div>
        )}

        <div className="mt-3 border-t border-gray-100 pt-3">
          {pg.monthly_rent && (
            <div><span className="text-lg font-bold text-gray-900">₹{typeof pg.monthly_rent === 'number' ? pg.monthly_rent.toLocaleString('en-IN') : pg.monthly_rent}</span>
            <span className="text-[10px] text-gray-400 ml-1">/month</span></div>
          )}
          {pg.price_per_night && !pg.monthly_rent && (
            <div><span className="text-lg font-bold text-gray-900">₹{typeof pg.price_per_night === 'number' ? pg.price_per_night.toLocaleString('en-IN') : pg.price_per_night}</span>
            <span className="text-[10px] text-gray-400 ml-1">/night</span></div>
          )}
        </div>

        {/* Booking Platforms */}
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
        {pg.price_source === 'ai_estimated' && (
          <p className="mt-1.5 text-[9px] text-gray-400">Estimated rent. Contact for exact pricing.</p>
        )}
      </div>
    </article>
  )
}
