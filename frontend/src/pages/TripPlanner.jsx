import { useState } from 'react'
import {
  MapPin, Calendar, Plane, Hotel, CloudSun, Train, Bus, Car,
  Search, ChevronRight, Info, Clock, Sparkles, Lightbulb,
  ArrowRightLeft, Users, Briefcase, StickyNote, Star,
  Wind, Droplets, ThermometerSun, ExternalLink, Brain, ArrowRight,
  Zap, ChevronDown, ChevronUp,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { planTrip, getTripRecommendations } from '../api/trips'
import Badge from '../components/ui/Badge'
import Spinner from '../components/ui/Spinner'
import { cn } from '../lib/cn'

// ── Config ──────────────────────────────────────────────────
const PURPOSES = [
  { value: 'client_meeting', label: 'Client Meeting' },
  { value: 'conference',     label: 'Conference / Event' },
  { value: 'training',       label: 'Training / Workshop' },
  { value: 'site_visit',     label: 'Site Visit' },
  { value: 'sales',          label: 'Sales Trip' },
  { value: 'other',          label: 'Other' },
]

const MODES = [
  { value: 'any',    label: 'Any (AI decides)', icon: Sparkles },
  { value: 'flight', label: 'Flight',           icon: Plane },
  { value: 'train',  label: 'Train',            icon: Train },
  { value: 'bus',    label: 'Bus',              icon: Bus },
  { value: 'car',    label: 'Car / Self-drive', icon: Car },
]

const INITIAL = {
  from_city: '', to_city: '', travel_date: '', return_date: '',
  num_travelers: '1', purpose: '', travel_mode: 'any', notes: '',
}

// ── Shared input styles ─────────────────────────────────────
const inputBase = 'w-full rounded-lg border border-gray-200 bg-white px-3.5 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 transition-all hover:border-gray-300 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/15'
const inputWithIcon = 'pl-10'
const labelClass = 'mb-1.5 block text-xs font-semibold uppercase tracking-wide text-gray-500'
const errorClass = 'mt-1 text-xs text-red-600'

export default function TripPlanner() {
  const [form, setForm] = useState(INITIAL)
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(null)
  const [errors, setErrors] = useState({})
  const [recs, setRecs] = useState(null)
  const [recsLoading, setRecsLoading] = useState(false)
  const today = new Date().toISOString().split('T')[0]

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }))

  const swapCities = () => setForm((p) => ({ ...p, from_city: p.to_city, to_city: p.from_city }))

  const handleTravelDate = (v) => {
    setForm((p) => ({ ...p, travel_date: v, return_date: p.return_date && v && p.return_date < v ? '' : p.return_date }))
  }

  const reset = () => { setForm(INITIAL); setErrors({}); setResults(null); setRecs(null) }

  const fetchRecs = async () => {
    if (!form.to_city.trim()) { toast.error('Enter a destination first'); return }
    setRecsLoading(true)
    try {
      let days = 3
      if (form.travel_date && form.return_date) {
        const diff = Math.round((new Date(form.return_date) - new Date(form.travel_date)) / 86400000) + 1
        if (diff > 0) days = diff
      }
      setRecs(await getTripRecommendations(form.to_city, days))
    } catch { toast.error('Could not load recommendations') }
    finally { setRecsLoading(false) }
  }

  const validate = () => {
    const e = {}
    if (!form.from_city.trim()) e.from_city = 'Required'
    if (!form.to_city.trim()) e.to_city = 'Required'
    if (!form.travel_date) e.travel_date = 'Required'
    if (!form.purpose) e.purpose = 'Required'
    return e
  }

  const handlePlan = async (e) => {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setErrors({}); setLoading(true); setResults(null)
    try {
      const data = await planTrip({ ...form, num_travelers: parseInt(form.num_travelers) || 1 })
      setResults(data)
      toast.success('Trip plan generated!')
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to generate trip plan')
    } finally { setLoading(false) }
  }

  const durationDays = form.travel_date && form.return_date
    ? Math.max(Math.round((new Date(form.return_date) - new Date(form.travel_date)) / 86400000) + 1, 1)
    : null

  return (
    <div className="mx-auto w-full max-w-7xl space-y-5">
      {/* Page header */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-cyan-500">
            <Brain size={14} className="text-white" />
          </div>
          <h1 className="font-heading text-xl font-bold text-gray-900">AI Trip Planner</h1>
          <span className="rounded-full bg-blue-50 border border-blue-200 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-blue-600">
            AI Powered
          </span>
        </div>
        <p className="text-sm text-gray-500">Generate a complete trip plan with flights, hotels, weather and transport in seconds.</p>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* ── Left: Form ──────────────────────────────── */}
        <div className="lg:col-span-5 space-y-4">
          <form onSubmit={handlePlan} className="rounded-xl border border-gray-200 bg-white shadow-card overflow-hidden">
            {/* Form header */}
            <div className="border-b border-gray-100 bg-gray-50/50 px-5 py-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-900">Trip Details</h3>
                <button type="button" onClick={swapCities}
                  className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900">
                  <ArrowRightLeft size={12} /> Swap
                </button>
              </div>
            </div>

            <div className="space-y-5 p-5">
              {/* Cities */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="From" error={errors.from_city}>
                  <div className="relative">
                    <MapPin size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input className={cn(inputBase, inputWithIcon)} placeholder="Origin city"
                      value={form.from_city} onChange={(e) => set('from_city', e.target.value)} />
                  </div>
                </Field>
                <Field label="To" error={errors.to_city}>
                  <div className="relative">
                    <MapPin size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-blue-500" />
                    <input className={cn(inputBase, inputWithIcon)} placeholder="Destination"
                      value={form.to_city} onChange={(e) => set('to_city', e.target.value)} />
                  </div>
                </Field>
              </div>

              {/* Dates */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Departure" error={errors.travel_date}>
                  <div className="relative">
                    <Calendar size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input type="date" className={cn(inputBase, inputWithIcon)} min={today}
                      value={form.travel_date} onChange={(e) => handleTravelDate(e.target.value)} />
                  </div>
                </Field>
                <Field label="Return" hint="Optional">
                  <div className="relative">
                    <Calendar size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input type="date" className={cn(inputBase, inputWithIcon)} min={form.travel_date || today}
                      value={form.return_date} onChange={(e) => set('return_date', e.target.value)} />
                  </div>
                </Field>
              </div>

              {/* Duration badge */}
              {durationDays && (
                <div className="flex items-center gap-2 rounded-lg bg-blue-50 border border-blue-100 px-3 py-2">
                  <Clock size={13} className="text-blue-500" />
                  <span className="text-xs font-medium text-blue-700">
                    {durationDays} {durationDays === 1 ? 'day' : 'days'} trip
                    {durationDays >= 5 && ' — Long stay options will be included'}
                  </span>
                </div>
              )}

              {/* Travelers + Mode */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Travelers">
                  <div className="relative">
                    <Users size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <select className={cn(inputBase, inputWithIcon, 'appearance-none')}
                      value={form.num_travelers} onChange={(e) => set('num_travelers', e.target.value)}>
                      {Array.from({ length: 10 }, (_, i) => (
                        <option key={i + 1} value={String(i + 1)}>{i + 1} {i === 0 ? 'Traveler' : 'Travelers'}</option>
                      ))}
                    </select>
                  </div>
                </Field>
                <Field label="Travel Mode">
                  <div className="relative">
                    <Plane size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <select className={cn(inputBase, inputWithIcon, 'appearance-none')}
                      value={form.travel_mode} onChange={(e) => set('travel_mode', e.target.value)}>
                      {MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                    </select>
                  </div>
                </Field>
              </div>

              {/* Purpose */}
              <Field label="Purpose" error={errors.purpose}>
                <div className="relative">
                  <Briefcase size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                  <select className={cn(inputBase, inputWithIcon, 'appearance-none')}
                    value={form.purpose} onChange={(e) => set('purpose', e.target.value)}>
                    <option value="">Select trip purpose</option>
                    {PURPOSES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                  </select>
                </div>
              </Field>

              {/* Notes */}
              <Field label="Notes" hint="Optional">
                <div className="relative">
                  <StickyNote size={15} className="absolute left-3 top-3 text-gray-400" />
                  <textarea rows={3} className={cn(inputBase, inputWithIcon, 'resize-none')}
                    placeholder="Preferences, budget range, requirements..."
                    value={form.notes} onChange={(e) => set('notes', e.target.value)} />
                </div>
              </Field>

              {/* Actions */}
              <div className="flex flex-col gap-2.5 pt-1">
                <button type="submit" disabled={loading}
                  className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 text-sm font-semibold text-white shadow-sm transition-all hover:shadow-md hover:brightness-105 disabled:opacity-60 disabled:cursor-not-allowed">
                  {loading ? (
                    <><Spinner size="xs" color="white" /> Generating Plan...</>
                  ) : (
                    <><Zap size={15} /> Generate AI Trip Plan</>
                  )}
                </button>
                <div className="grid grid-cols-2 gap-2.5">
                  <button type="button" onClick={fetchRecs} disabled={recsLoading || !form.to_city.trim()}
                    className="flex h-10 items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed">
                    {recsLoading ? <Spinner size="xs" /> : <Lightbulb size={14} className="text-amber-500" />}
                    AI Tips
                  </button>
                  <button type="button" onClick={reset}
                    className="flex h-10 items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50">
                    Reset
                  </button>
                </div>
              </div>
            </div>
          </form>

          {/* AI Recommendations */}
          {recs?.success && <RecsPanel recs={recs} />}
        </div>

        {/* ── Right: Results ──────────────────────────── */}
        <div className="lg:col-span-7 space-y-4">
          {loading && <LoadingState />}
          {!loading && !results && <EmptyState />}
          {results && <TripResults results={results} />}
        </div>
      </div>
    </div>
  )
}

// ── Form Field wrapper ──────────────────────────────────────
function Field({ label, hint, error, children }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <label className={labelClass}>{label}</label>
        {hint && <span className="text-[10px] text-gray-400">{hint}</span>}
      </div>
      {children}
      {error && <p className={errorClass}>{error}</p>}
    </div>
  )
}

// ── Loading State ───────────────────────────────────────────
function LoadingState() {
  const steps = ['Searching flights', 'Finding hotels', 'Checking weather', 'Analyzing routes', 'Optimizing plan']
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-8 shadow-card sm:p-12">
      <div className="flex flex-col items-center text-center">
        <div className="relative">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-cyan-500 shadow-lg shadow-blue-500/25">
            <Brain size={28} className="text-white animate-pulse" />
          </div>
          <div className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-green-400 border-2 border-white animate-ping" />
        </div>
        <h3 className="mt-5 font-heading text-lg font-bold text-gray-900">AI is planning your trip</h3>
        <p className="mt-1 text-sm text-gray-500">Analyzing multiple sources for the best options...</p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {steps.map((s, i) => (
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
          <Plane size={28} className="text-gray-400" />
        </div>
        <h3 className="mt-4 font-heading text-lg font-semibold text-gray-700">Ready to plan your trip</h3>
        <p className="mt-1 max-w-sm text-sm text-gray-500">
          Fill in the details and our AI will find the best flights, hotels, weather forecasts, and transport options for you.
        </p>
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { icon: Plane, label: 'Flights' },
            { icon: Hotel, label: 'Hotels' },
            { icon: CloudSun, label: 'Weather' },
            { icon: Train, label: 'Transport' },
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

// ── AI Recommendations Panel ────────────────────────────────
function RecsPanel({ recs }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-card overflow-hidden">
      <div className="flex items-center gap-2 border-b border-gray-100 bg-amber-50/50 px-5 py-3">
        <Sparkles size={14} className="text-amber-500" />
        <h4 className="text-sm font-semibold text-gray-900">AI Recommendations for {recs.destination}</h4>
        {recs.ai_powered && (
          <span className="ml-auto rounded-full bg-amber-100 border border-amber-200 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-700">AI</span>
        )}
      </div>
      <div className="p-4 space-y-3">
        {recs.hotels && (
          <TipCard icon={Hotel} color="blue" title="Hotels" tip={recs.hotels.tip} />
        )}
        {recs.flights && (
          <TipCard icon={Plane} color="violet" title="Flights" tip={recs.flights.tip} />
        )}
        {recs.budget_tip && (
          <div className="rounded-lg bg-gray-50 border border-gray-100 px-3 py-2.5">
            <p className="text-xs text-gray-700"><span className="font-semibold">Budget:</span> {recs.budget_tip}</p>
          </div>
        )}
        {recs.ai_insight && (
          <div className="rounded-lg bg-blue-50 border border-blue-100 p-3">
            <p className="text-xs font-semibold text-blue-800 mb-1">AI Insight</p>
            <p className="text-xs text-blue-700 leading-relaxed whitespace-pre-line">{recs.ai_insight}</p>
          </div>
        )}
        {recs.past_trip_count > 0 && (
          <p className="text-[11px] text-gray-400">Based on {recs.past_trip_count} previous trip{recs.past_trip_count !== 1 ? 's' : ''}</p>
        )}
      </div>
    </div>
  )
}

function TipCard({ icon: Icon, color, title, tip }) {
  const colors = {
    blue:   'border-blue-100 bg-blue-50 text-blue-700',
    violet: 'border-violet-100 bg-violet-50 text-violet-700',
  }
  return (
    <div className={`rounded-lg border p-3 ${colors[color]}`}>
      <div className="flex items-center gap-1.5 mb-1">
        <Icon size={12} />
        <span className="text-xs font-semibold">{title}</span>
      </div>
      <p className="text-xs opacity-90">{tip}</p>
    </div>
  )
}

// ── Trip Results ────────────────────────────────────────────
function TripResults({ results }) {
  const r = results || {}
  const modes = r.travel_options || r.travel?.modes || {}
  const flights = modes.flights || modes.flight?.options || []
  const hotels = Array.isArray(r.hotels) ? r.hotels : (r.hotels?.hotels || [])
  const pgOptions = r.pg_options || r.hotels?.pg_options || []
  const weather = normalizeWeather(r.weather)
  const summaryText = getSummaryText(r)

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Summary */}
      {summaryText && (
        <div className="relative overflow-hidden rounded-xl bg-gradient-to-br from-brand-dark to-[#1a2744] p-5 shadow-card">
          <div className="absolute top-0 right-0 h-20 w-20 rounded-full bg-brand-cyan/10 blur-2xl" />
          <div className="relative flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-cyan/15">
              <Brain size={16} className="text-brand-cyan" />
            </div>
            <div>
              <h4 className="text-sm font-semibold text-white">AI Trip Summary</h4>
              <p className="mt-1 text-sm leading-relaxed text-gray-300">{summaryText}</p>
            </div>
          </div>
          {r.source && r.source !== 'fallback' && (
            <div className="mt-3 flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
              <span className="text-[10px] font-medium text-gray-400">Live data</span>
            </div>
          )}
        </div>
      )}

      {/* Flights */}
      {flights.length > 0 && (
        <ResultSection icon={Plane} title="Flight Options" count={flights.length} accent="blue">
          {flights.slice(0, 5).map((f, i) => <FlightCard key={i} flight={f} />)}
        </ResultSection>
      )}

      {/* Train / Bus / Cab */}
      {modes.train && (
        <ResultSection icon={Train} title="Train Options" accent="emerald">
          <ModeCard mode={modes.train} type="train" />
        </ResultSection>
      )}
      {modes.bus && (
        <ResultSection icon={Bus} title="Bus Options" accent="emerald">
          <ModeCard mode={modes.bus} type="bus" />
        </ResultSection>
      )}
      {modes.cab && (
        <ResultSection icon={Car} title="Cab / Self-Drive" accent="emerald">
          <ModeCard mode={modes.cab} type="cab" />
        </ResultSection>
      )}

      {/* Hotels */}
      {hotels.length > 0 && (
        <ResultSection icon={Hotel} title="Hotel Options" count={hotels.length} accent="violet">
          {hotels.slice(0, 5).map((h, i) => <HotelCard key={i} hotel={h} />)}
        </ResultSection>
      )}

      {/* PG / Serviced */}
      {pgOptions.length > 0 && (
        <ResultSection icon={Hotel} title="PG / Serviced Apartments" count={pgOptions.length} accent="violet">
          {pgOptions.slice(0, 4).map((pg, i) => <HotelCard key={i} hotel={pg} />)}
        </ResultSection>
      )}

      {/* Weather */}
      {weather && (
        <ResultSection icon={CloudSun} title="Weather Forecast" accent="amber">
          <WeatherCard weather={weather} />
        </ResultSection>
      )}
    </div>
  )
}

// ── Result Section wrapper ──────────────────────────────────
function ResultSection({ icon: Icon, title, count, accent, children }) {
  const [expanded, setExpanded] = useState(true)
  const accents = {
    blue:    { icon: 'bg-blue-50 text-blue-600 border-blue-100',     badge: 'bg-blue-100 text-blue-700' },
    emerald: { icon: 'bg-emerald-50 text-emerald-600 border-emerald-100', badge: 'bg-emerald-100 text-emerald-700' },
    violet:  { icon: 'bg-violet-50 text-violet-600 border-violet-100',   badge: 'bg-violet-100 text-violet-700' },
    amber:   { icon: 'bg-amber-50 text-amber-600 border-amber-100',     badge: 'bg-amber-100 text-amber-700' },
  }
  const a = accents[accent] || accents.blue

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-card">
      <button type="button" onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-3 border-b border-gray-100 px-5 py-3.5 text-left transition-colors hover:bg-gray-50/50">
        <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border ${a.icon}`}>
          <Icon size={15} />
        </div>
        <h4 className="flex-1 text-sm font-semibold text-gray-900">{title}</h4>
        {count > 0 && (
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${a.badge}`}>{count} found</span>
        )}
        {expanded ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
      </button>
      {expanded && <div className="divide-y divide-gray-100">{children}</div>}
    </div>
  )
}

// ── Flight Card — visual like booking sites ─────────────────
function FlightCard({ flight: f }) {
  const from = f.origin || f.from || f.departure_city || '—'
  const to = f.destination || f.to || f.arrival_city || '—'
  const depart = f.departure_time || formatTime(f.departure)
  const arrive = f.arrival_time || formatTime(f.arrival)
  const price = f.price ?? f.total_price ?? f.total ?? f.fare
  const stops = f.stops !== undefined && f.stops !== null ? Number(f.stops) : null
  const bookUrl = f.booking_url || f.airline_url || '#'

  return (
    <div className="group px-5 py-4 transition-colors hover:bg-blue-50/30">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
        {/* Airline */}
        <div className="flex items-center gap-3 sm:w-32 shrink-0">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 border border-blue-100">
            <Plane size={14} className="text-blue-600" />
          </div>
          <div>
            <p className="text-xs font-semibold text-gray-900">{f.airline || 'Airline'}</p>
            {f.flight_number && <p className="text-[10px] text-gray-400">{f.flight_number}</p>}
          </div>
        </div>

        {/* Time + Route visual */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <div className="text-center">
              <p className="text-base font-bold text-gray-900">{depart || '—'}</p>
              <p className="text-[10px] text-gray-400">{from}</p>
            </div>

            {/* Route line */}
            <div className="flex-1 flex items-center gap-1 px-2">
              <div className="h-1.5 w-1.5 rounded-full bg-blue-500" />
              <div className="flex-1 relative">
                <div className="h-[2px] bg-blue-200 w-full" />
                {f.duration && (
                  <span className="absolute -top-4 left-1/2 -translate-x-1/2 text-[9px] font-medium text-gray-400 whitespace-nowrap">
                    {f.duration}
                  </span>
                )}
                {stops !== null && !Number.isNaN(stops) && (
                  <span className={cn('absolute -bottom-3.5 left-1/2 -translate-x-1/2 rounded-full px-1.5 py-0 text-[8px] font-bold',
                    stops === 0 ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700')}>
                    {stops === 0 ? 'Direct' : `${stops} stop`}
                  </span>
                )}
              </div>
              <div className="h-1.5 w-1.5 rounded-full bg-blue-500" />
            </div>

            <div className="text-center">
              <p className="text-base font-bold text-gray-900">{arrive || '—'}</p>
              <p className="text-[10px] text-gray-400">{to}</p>
            </div>
          </div>
        </div>

        {/* Price + Book */}
        <div className="flex items-center gap-3 sm:flex-col sm:items-end shrink-0">
          {price && (
            <div className="sm:text-right">
              <span className="text-lg font-bold text-gray-900">
                {typeof price === 'number' ? `₹${price.toLocaleString('en-IN')}` : price}
              </span>
              <p className="text-[9px] text-gray-400">per person</p>
            </div>
          )}
          <a href={bookUrl} target="_blank" rel="noreferrer"
            className="flex h-7 items-center gap-1 rounded-md bg-blue-600 px-3 text-[10px] font-semibold text-white hover:bg-blue-700 opacity-0 group-hover:opacity-100 transition-opacity sm:opacity-100">
            Book <ExternalLink size={8} />
          </a>
        </div>
      </div>
    </div>
  )
}

// ── Hotel Card ──────────────────────────────────────────────
function HotelCard({ hotel: h }) {
  const price = h.price_per_night ?? h.monthly_rent ?? h.price
  const stars = h.stars ? Math.min(h.stars, 5) : 0

  return (
    <div className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-start sm:gap-4 transition-colors hover:bg-gray-50/50">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-violet-50 border border-violet-100">
        <Hotel size={16} className="text-violet-600" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-900">{h.name || h.hotel_name}</p>
        <div className="flex flex-wrap items-center gap-2 mt-1.5">
          {stars > 0 && (
            <div className="flex items-center gap-0.5">
              {Array.from({ length: stars }).map((_, i) => (
                <Star key={i} size={11} className="fill-amber-400 text-amber-400" />
              ))}
            </div>
          )}
          {h.rating && (
            <span className="rounded bg-green-50 border border-green-200 px-1.5 py-0.5 text-[10px] font-bold text-green-700">{h.rating}/10</span>
          )}
          {(h.location || h.address) && (
            <span className="flex items-center gap-1 text-xs text-gray-400">
              <MapPin size={10} /> {h.location || h.address}
            </span>
          )}
        </div>
        {h.amenities && h.amenities.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {h.amenities.slice(0, 5).map((a) => (
              <span key={a} className="rounded bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-600">{a}</span>
            ))}
          </div>
        )}
      </div>
      {price && (
        <div className="shrink-0 text-left sm:text-right">
          <span className="text-base font-bold text-gray-900">
            {typeof price === 'number' ? `₹${price.toLocaleString('en-IN')}` : price}
          </span>
          <p className="text-[10px] text-gray-400">{h.monthly_rent ? '/month' : '/night'}</p>
        </div>
      )}
    </div>
  )
}

// ── Mode Card (Train/Bus/Cab) ───────────────────────────────
function ModeCard({ mode, type }) {
  const platforms = mode.platforms || mode.booking_platforms || []
  const duration = mode.estimated_duration || mode.estimated_travel_time
  const fare = mode.estimated_fare
  const highlights = mode.popular_trains || []

  return (
    <div className="space-y-3 px-5 py-4">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {duration && (
          <div className="rounded-lg bg-gray-50 border border-gray-100 px-3 py-2">
            <p className="text-[10px] font-semibold uppercase text-gray-400">Duration</p>
            <p className="text-sm font-semibold text-gray-900">{duration}</p>
          </div>
        )}
        {fare && (
          <div className="rounded-lg bg-gray-50 border border-gray-100 px-3 py-2">
            <p className="text-[10px] font-semibold uppercase text-gray-400">Fare</p>
            <p className="text-sm font-semibold text-gray-900">{fare}</p>
          </div>
        )}
        {mode.station_from && mode.station_to && (
          <div className="rounded-lg bg-gray-50 border border-gray-100 px-3 py-2">
            <p className="text-[10px] font-semibold uppercase text-gray-400">Route</p>
            <p className="text-sm font-semibold text-gray-900">{mode.station_from} → {mode.station_to}</p>
          </div>
        )}
      </div>
      {highlights.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {highlights.slice(0, 5).map((item, i) => (
            <span key={`${item}-${i}`} className="rounded bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-600">{item}</span>
          ))}
        </div>
      )}
      {platforms.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {platforms.slice(0, 4).map((p, i) => (
            <a key={`${p.name || type}-${i}`} href={p.url || '#'} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:border-blue-300 hover:text-blue-700">
              {p.name || `${type} option`} <ExternalLink size={10} />
            </a>
          ))}
        </div>
      )}
      {mode.note && <p className="text-xs text-gray-400">{mode.note}</p>}
    </div>
  )
}

// ── Weather Card — visual dashboard ─────────────────────────
function WeatherCard({ weather: w }) {
  const temp = w.temperature ?? w.temp
  const desc = w.description || w.condition

  return (
    <div className="p-5">
      {/* Current weather — hero style */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center rounded-xl bg-gradient-to-br from-amber-50 to-orange-50 border border-amber-100 p-4">
        <div className="flex items-center gap-4">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-white shadow-sm text-4xl">
            {w.icon || '🌤️'}
          </div>
          <div>
            {temp !== undefined && (
              <div className="text-4xl font-bold text-gray-900">{temp}<span className="text-xl text-gray-400">°C</span></div>
            )}
            {desc && <p className="text-sm capitalize text-gray-600 mt-0.5">{desc}</p>}
          </div>
        </div>

        {/* Weather stats */}
        <div className="flex gap-3 sm:ml-auto">
          {[
            { icon: Droplets, label: 'Humidity', value: w.humidity ? `${w.humidity}%` : null, color: 'text-blue-500' },
            { icon: Wind, label: 'Wind', value: w.wind_speed ? `${w.wind_speed} km/h` : null, color: 'text-gray-500' },
            { icon: ThermometerSun, label: 'Feels Like', value: w.feels_like ? `${w.feels_like}°` : null, color: 'text-orange-500' },
          ].filter(s => s.value).map(s => (
            <div key={s.label} className="rounded-lg bg-white border border-amber-100 px-3 py-2 text-center min-w-[70px]">
              <s.icon size={14} className={cn('mx-auto mb-1', s.color)} />
              <p className="text-xs font-bold text-gray-900">{s.value}</p>
              <p className="text-[9px] text-gray-400">{s.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Multi-day forecast */}
      {w.forecast && w.forecast.length > 0 && (
        <div className="mt-4">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 mb-2">Forecast</p>
          <div className="grid grid-cols-4 gap-2">
            {w.forecast.slice(0, 4).map((d, i) => (
              <div key={i} className="rounded-xl bg-gray-50 border border-gray-100 p-3 text-center hover:bg-white hover:shadow-sm transition-all">
                <p className="text-[10px] font-semibold text-gray-500">{d.day || d.date}</p>
                <p className="my-1.5 text-2xl">{d.icon || '⛅'}</p>
                <p className="text-sm font-bold text-gray-900">{d.temp || d.temperature}°</p>
                {d.description && <p className="text-[9px] text-gray-400 mt-0.5 capitalize">{d.description}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Travel advisory based on weather */}
      {temp !== undefined && (
        <div className={cn('mt-3 rounded-lg border px-3 py-2 text-xs',
          temp > 35 ? 'border-red-200 bg-red-50 text-red-700' :
          temp < 10 ? 'border-blue-200 bg-blue-50 text-blue-700' :
          'border-green-200 bg-green-50 text-green-700'
        )}>
          {temp > 35 ? 'Hot weather expected. Carry sunscreen, stay hydrated, and prefer AC transport.' :
           temp < 10 ? 'Cold weather expected. Pack warm layers, gloves, and a jacket.' :
           'Pleasant weather for travel. Light clothing recommended.'}
        </div>
      )}
    </div>
  )
}

// ── Helpers ─────────────────────────────────────────────────
function normalizeWeather(weather) {
  if (!weather) return null
  if (weather.current || weather.forecast) {
    const current = weather.current || {}
    return { ...current, forecast: weather.forecast || current.forecast || [] }
  }
  return weather
}

function getSummaryText(result) {
  if (!result) return ''
  if (typeof result.summary === 'string' && result.summary.trim()) return result.summary
  const trip = result.trip_summary
  if (!trip) return ''
  return `${trip.purpose || 'Business trip'} to ${trip.destination || 'your destination'} for ${trip.duration || 'the planned duration'}.`
}

function formatTime(value) {
  if (!value) return ''
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return ''
  return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
