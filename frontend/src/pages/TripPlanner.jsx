import { useState } from 'react'
import {
  MapPin, Calendar, Plane, Hotel, CloudSun,
  Search, ChevronRight, Info, Clock,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { planTrip } from '../api/trips'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import Select from '../components/ui/Select'
import Badge from '../components/ui/Badge'
import Spinner from '../components/ui/Spinner'

const travelPurposes = [
  { value: 'client_meeting', label: 'Client Meeting' },
  { value: 'conference',     label: 'Conference / Event' },
  { value: 'training',       label: 'Training / Workshop' },
  { value: 'site_visit',     label: 'Site Visit' },
  { value: 'sales',          label: 'Sales Trip' },
  { value: 'other',          label: 'Other' },
]

const travelModes = [
  { value: 'flight', label: 'Flight' },
  { value: 'train',  label: 'Train' },
  { value: 'bus',    label: 'Bus' },
  { value: 'car',    label: 'Car / Self-drive' },
  { value: 'any',    label: 'Any (AI decides)' },
]

const travelerOptions = Array.from({ length: 10 }, (_, i) => {
  const count = i + 1
  return {
    value: String(count),
    label: `${count} ${count === 1 ? 'Traveler' : 'Travelers'}`,
  }
})

const initialForm = {
  from_city:    '',
  to_city:      '',
  travel_date:  '',
  return_date:  '',
  num_travelers: '1',
  purpose:      '',
  travel_mode:  'any',
  notes:        '',
}

export default function TripPlanner() {
  const [form, setForm] = useState(initialForm)
  const [loading,  setLoading]  = useState(false)
  const [results,  setResults]  = useState(null)
  const [errors,   setErrors]   = useState({})
  const today = new Date().toISOString().split('T')[0]
  const panelClass = 'rounded-xl border border-[#d2dae4] bg-white shadow-[0_12px_24px_rgba(27,38,59,0.08)]'

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }))

  const handleSwapCities = () => {
    setForm((p) => ({ ...p, from_city: p.to_city, to_city: p.from_city }))
  }

  const handleTravelDateChange = (value) => {
    setForm((p) => ({
      ...p,
      travel_date: value,
      return_date: p.return_date && value && p.return_date < value ? '' : p.return_date,
    }))
  }

  const handleReset = () => {
    setForm(initialForm)
    setErrors({})
    setResults(null)
  }

  const validate = () => {
    const e = {}
    if (!form.from_city.trim())  e.from_city  = 'Origin city required'
    if (!form.to_city.trim())    e.to_city    = 'Destination required'
    if (!form.travel_date)       e.travel_date = 'Travel date required'
    if (!form.purpose)           e.purpose    = 'Select trip purpose'
    return e
  }

  const handlePlan = async (e) => {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setErrors({})
    setLoading(true)
    setResults(null)

    try {
      const data = await planTrip({
        ...form,
        num_travelers: parseInt(form.num_travelers) || 1,
      })
      setResults(data)
      toast.success('Trip plan generated successfully!')
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to generate trip plan')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-7xl space-y-4 rounded-3xl border border-[#cdd6e0] bg-[radial-gradient(circle_at_top_left,#f6f9fc_0%,transparent_38%),linear-gradient(180deg,#edf1f5_0%,#E0E1DD_100%)] px-3 pb-6 pt-4 sm:space-y-6 sm:px-5 md:px-6 md:pb-8">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12 lg:gap-6">
        {/* ── Form panel ──────────────────────────── */}
        <div className="lg:col-span-6 xl:col-span-5">
          <form onSubmit={handlePlan} className={`${panelClass} space-y-6 p-5 sm:p-7`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-1">
                <h3 className="font-heading text-lg font-semibold text-[#1B263B]">Trip Details</h3>
                <p className="text-sm text-[#778DA9]">Add your route and preferences to generate the best plan.</p>
              </div>
              <button
                type="button"
                onClick={handleSwapCities}
                className="rounded-md border border-[#d2e4ef] bg-[#eef8fd] px-2.5 py-1 text-xs font-medium text-[#1B263B] transition-colors hover:bg-[#e3f3fb]"
              >
                Swap Cities
              </button>
            </div>

            <div className="grid grid-cols-1 gap-6">
              <Input
                label="From City"
                placeholder="e.g. Mumbai, India"
                value={form.from_city}
                onChange={(e) => set('from_city', e.target.value)}
                error={errors.from_city}
                leftIcon={<MapPin size={16} />}
                size="lg"
                required
              />

              <Input
                label="To City"
                placeholder="e.g. Singapore"
                value={form.to_city}
                onChange={(e) => set('to_city', e.target.value)}
                error={errors.to_city}
                leftIcon={<MapPin size={16} />}
                size="lg"
                required
              />
            </div>

            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              <Input
                label="Departure Date"
                type="date"
                min={today}
                value={form.travel_date}
                onChange={(e) => handleTravelDateChange(e.target.value)}
                error={errors.travel_date}
                leftIcon={<Calendar size={16} />}
                size="lg"
                required
              />
              <Input
                label="Return Date"
                type="date"
                min={form.travel_date || today}
                value={form.return_date}
                onChange={(e) => set('return_date', e.target.value)}
                leftIcon={<Calendar size={16} />}
                size="lg"
                hint="Optional"
              />
            </div>

            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              <Select
                label="Travelers"
                options={travelerOptions}
                value={form.num_travelers}
                onChange={(e) => set('num_travelers', e.target.value)}
                size="lg"
              />
              <Select
                label="Travel Mode"
                options={travelModes}
                value={form.travel_mode}
                onChange={(e) => set('travel_mode', e.target.value)}
                size="lg"
              />
            </div>

            <Select
              label="Purpose"
              options={travelPurposes}
              placeholder="Select trip purpose"
              value={form.purpose}
              onChange={(e) => set('purpose', e.target.value)}
              error={errors.purpose}
              size="lg"
              required
            />

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-gray-700">Additional Notes</label>
              <textarea
                rows={5}
                placeholder="Any preferences, budget range, or special requirements..."
                value={form.notes}
                onChange={(e) => set('notes', e.target.value)}
                className="w-full resize-none rounded-lg border border-gray-200 px-4 py-3 text-[15px] leading-6 text-gray-900 placeholder:text-gray-400 transition-all hover:border-gray-300 focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/20"
              />
            </div>

            <div className="flex flex-col gap-3 sm:flex-row">
              <Button
                type="button"
                variant="ghost"
                size="lg"
                className="w-full justify-center border border-gray-200 text-gray-600 hover:bg-gray-50 sm:w-auto"
                onClick={handleReset}
              >
                Reset
              </Button>
              <Button
                type="submit"
                variant="secondary"
                size="lg"
                loading={loading}
                leftIcon={<Search size={16} />}
                className="w-full justify-center border border-[#4CC9F0] bg-[#4CC9F0] text-[#1B263B] hover:bg-[#35bee9] sm:flex-1"
              >
                {loading ? 'Planning your trip…' : 'Generate Trip Plan'}
              </Button>
            </div>
          </form>
        </div>

        {/* ── Results panel ───────────────────────── */}
        <div className="space-y-4 lg:col-span-6 xl:col-span-7">
          {loading && (
            <div className={`${panelClass} flex flex-col items-center gap-4 p-6 sm:p-12`}>
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#4CC9F0]">
                <Spinner size="md" color="dark" />
              </div>
              <div className="text-center">
                <p className="font-semibold text-[#1B263B] font-heading">Generating your trip plan…</p>
                <p className="mt-1 text-sm text-[#778DA9]">Finding the best routes, stays, and weather outlook.</p>
              </div>
              <div className="mt-2 flex flex-wrap justify-center gap-2">
                {['Checking flights', 'Searching hotels', 'Fetching weather', 'Analyzing routes'].map((s) => (
                  <span key={s} className="animate-pulse-slow rounded-full border border-[#d2dae4] bg-[#f8fbff] px-3 py-1.5 text-xs text-[#44566f]">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {!loading && !results && (
            <div className={`${panelClass} p-6 text-center sm:p-12`}>
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-[#d2e4ef] bg-[#eef8fd]">
                <Plane size={28} className="text-[#1B263B]" />
              </div>
              <h3 className="font-heading text-lg font-semibold text-[#1B263B]">Ready when you are</h3>
              <p className="mx-auto mt-1 max-w-sm text-sm text-[#778DA9]">
                Fill out the form to generate a complete trip plan with live travel options.
              </p>
            </div>
          )}

          {results && <TripResults results={results} />}
        </div>
      </div>
    </div>
  )
}

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
        <div className="rounded-xl border border-[#2b3d59] bg-[linear-gradient(135deg,#1B263B_0%,#22314a_100%)] p-5 text-[#E0E1DD] shadow-[0_10px_20px_rgba(15,23,42,0.25)]">
          <div className="flex items-start gap-3">
            <Info size={16} className="mt-0.5 shrink-0 text-[#4CC9F0]" />
            <div>
              <h4 className="mb-1 font-heading font-semibold text-white">Trip Summary</h4>
              <p className="text-sm leading-relaxed text-[#d2d9e4]">{summaryText}</p>
            </div>
          </div>
        </div>
      )}

      {/* Flights */}
      {flights.length > 0 && (
        <ResultSection icon={<Plane size={16} />} title="Flight Options" color="blue">
          {flights.slice(0, 4).map((f, i) => (
            <FlightCard key={i} flight={f} />
          ))}
        </ResultSection>
      )}

      {/* Train / Bus / Cab */}
      {modes.train && (
        <ResultSection icon={<ChevronRight size={16} />} title="Train Options" color="green">
          <ModeCard mode={modes.train} type="train" />
        </ResultSection>
      )}
      {modes.bus && (
        <ResultSection icon={<ChevronRight size={16} />} title="Bus Options" color="green">
          <ModeCard mode={modes.bus} type="bus" />
        </ResultSection>
      )}
      {modes.cab && (
        <ResultSection icon={<ChevronRight size={16} />} title="Cab / Self-Drive" color="green">
          <ModeCard mode={modes.cab} type="cab" />
        </ResultSection>
      )}

      {/* Hotels */}
      {hotels.length > 0 && (
        <ResultSection icon={<Hotel size={16} />} title="Hotel Options" color="sky">
          {hotels.slice(0, 4).map((h, i) => (
            <HotelCard key={i} hotel={h} />
          ))}
        </ResultSection>
      )}

      {/* PG / serviced */}
      {pgOptions.length > 0 && (
        <ResultSection icon={<Hotel size={16} />} title="PG / Serviced Apartments" color="sky">
          {pgOptions.slice(0, 4).map((pg, i) => (
            <HotelCard key={i} hotel={pg} />
          ))}
        </ResultSection>
      )}

      {/* Weather */}
      {weather && (
        <ResultSection icon={<CloudSun size={16} />} title="Weather Forecast" color="orange">
          <WeatherCard weather={weather} />
        </ResultSection>
      )}
    </div>
  )
}

function ModeCard({ mode, type }) {
  const platforms = mode.platforms || mode.booking_platforms || []
  const duration = mode.estimated_duration || mode.estimated_travel_time
  const fare = mode.estimated_fare
  const highlights = mode.popular_trains || []

  return (
    <div className="space-y-3 px-4 py-4 sm:px-5">
      {duration && (
        <p className="text-sm text-[#44566f]">
          Estimated duration: <span className="font-medium text-[#1B263B]">{duration}</span>
        </p>
      )}
      {fare && (
        <p className="text-sm text-[#44566f]">
          Estimated fare: <span className="font-medium text-[#1B263B]">{fare}</span>
        </p>
      )}
      {mode.station_from && mode.station_to && (
        <p className="text-sm text-[#44566f]">
          Route: <span className="font-medium text-[#1B263B]">{mode.station_from} → {mode.station_to}</span>
        </p>
      )}
      {highlights.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {highlights.slice(0, 5).map((item, i) => (
            <Badge key={`${item}-${i}`} variant="gray" size="xs">{item}</Badge>
          ))}
        </div>
      )}
      {platforms.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {platforms.slice(0, 4).map((p, i) => (
            <a
              key={`${p.name || type}-${i}`}
              href={p.url || '#'}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center rounded-md border border-[#d2dae4] bg-[#f8fbff] px-2 py-1 text-xs text-[#44566f] hover:border-[#4CC9F0] hover:text-[#1B263B]"
            >
              {p.name || `${type} option`}
            </a>
          ))}
        </div>
      )}
      {mode.note && <p className="text-xs text-[#778DA9]">{mode.note}</p>}
    </div>
  )
}

function ResultSection({ icon, title, color, children }) {
  const colorMap = {
    blue:   'bg-[#eef8fd] text-[#1B263B] border-[#d2e4ef]',
    sky:    'bg-[#eef8fd] text-[#1B263B] border-[#d2e4ef]',
    orange: 'bg-[#fff5e6] text-[#8a5a05] border-[#f5deb5]',
    green:  'bg-[#edf7ef] text-[#1e4d33] border-[#cde7d4]',
  }
  return (
    <div className="overflow-hidden rounded-xl border border-[#d2dae4] bg-white shadow-[0_10px_20px_rgba(27,38,59,0.07)]">
      <div className="flex items-center gap-2.5 border-b border-[#e3e8ef] px-4 py-3.5 sm:px-5">
        <span className={`inline-flex items-center justify-center w-6 h-6 rounded-md ${colorMap[color]} border`}>
          {icon}
        </span>
        <h4 className="text-sm font-heading font-semibold text-[#1B263B]">{title}</h4>
      </div>
      <div className="divide-y divide-[#edf1f5]">{children}</div>
    </div>
  )
}

function FlightCard({ flight: f }) {
  const fromLabel = f.origin || f.from || f.departure_city || 'Origin'
  const toLabel = f.destination || f.to || f.arrival_city || 'Destination'
  const departTime = f.departure_time || formatTime(f.departure)
  const arriveTime = f.arrival_time || formatTime(f.arrival)
  const price = f.price ?? f.total_price ?? f.total ?? f.fare
  const stopCount = f.stops !== undefined && f.stops !== null ? Number(f.stops) : null

  return (
    <div className="flex flex-col items-start gap-3 px-4 py-4 sm:flex-row sm:items-center sm:gap-4 sm:px-5">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-[#d2e4ef] bg-[#eef8fd]">
        <Plane size={15} className="text-[#1B263B]" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold text-[#1B263B]">
            {fromLabel} → {toLabel}
          </span>
          {f.airline && <span className="text-xs text-[#778DA9]">{f.airline}</span>}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-[#44566f]">
          {departTime && <span className="flex items-center gap-1"><Clock size={11} />{departTime}</span>}
          {arriveTime && <span>→ {arriveTime}</span>}
          {f.duration && <span>{f.duration}</span>}
          {stopCount !== null && !Number.isNaN(stopCount) && (
            <Badge variant={stopCount === 0 ? 'green' : 'orange'} size="xs">
              {stopCount === 0 ? 'Direct' : `${stopCount} stop${stopCount > 1 ? 's' : ''}`}
            </Badge>
          )}
        </div>
      </div>
      {price && (
        <div className="shrink-0 text-left sm:text-right">
          <span className="font-bold text-[#1B263B]">
            {typeof price === 'number'
              ? `₹${price.toLocaleString('en-IN')}`
              : price}
          </span>
          <p className="text-[10px] text-[#778DA9]">per person</p>
        </div>
      )}
    </div>
  )
}

function HotelCard({ hotel: h }) {
  const price = h.price_per_night ?? h.monthly_rent ?? h.price
  return (
    <div className="flex flex-col items-start gap-3 px-4 py-4 sm:flex-row sm:items-start sm:gap-4 sm:px-5">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-[#d2e4ef] bg-[#eef8fd]">
        <Hotel size={15} className="text-[#1B263B]" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-[#1B263B]">{h.name || h.hotel_name}</p>
        <div className="flex flex-wrap items-center gap-2 mt-1">
          {h.stars && (
            <span className="text-xs text-warning-500">{'★'.repeat(h.stars)}</span>
          )}
          {h.rating && (
            <Badge variant="green" size="xs">{h.rating} / 10</Badge>
          )}
          {(h.location || h.address) && (
            <span className="flex items-center gap-0.5 text-xs text-[#778DA9]">
              <MapPin size={10} />{h.location || h.address}
            </span>
          )}
        </div>
      </div>
      {price && (
        <div className="shrink-0 text-left sm:text-right">
          <span className="font-bold text-[#1B263B]">
            {typeof price === 'number'
              ? `₹${price.toLocaleString('en-IN')}`
              : price}
          </span>
          <p className="text-[10px] text-[#778DA9]">{h.monthly_rent ? '/month' : '/night'}</p>
        </div>
      )}
    </div>
  )
}

function WeatherCard({ weather: w }) {
  const temp = w.temperature ?? w.temp
  const desc = w.description || w.condition

  return (
    <div className="flex flex-col items-start gap-4 px-4 py-4 sm:flex-row sm:items-center sm:px-5">
      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-[#f5deb5] bg-[#fff5e6] text-2xl">
        {w.icon || '🌤️'}
      </div>
      <div>
        {temp !== undefined && (
          <div className="text-2xl font-bold text-[#1B263B] font-heading">{temp}°C</div>
        )}
        {desc && <p className="text-sm capitalize text-[#44566f]">{desc}</p>}
        {w.humidity && <p className="mt-0.5 text-xs text-[#778DA9]">Humidity: {w.humidity}%</p>}
      </div>
      {w.forecast && w.forecast.length > 0 && (
        <div className="mt-1 flex w-full flex-wrap gap-3 sm:ml-auto sm:mt-0 sm:w-auto sm:flex-nowrap">
          {w.forecast.slice(0, 4).map((d, i) => (
            <div key={i} className="text-center text-xs">
              <div className="text-[#778DA9]">{d.day || d.date}</div>
              <div className="text-lg my-0.5">{d.icon || '⛅'}</div>
              <div className="font-medium text-[#44566f]">{d.temp || d.temperature}°</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function normalizeWeather(weather) {
  if (!weather) return null
  if (weather.current || weather.forecast) {
    const current = weather.current || {}
    return {
      ...current,
      forecast: weather.forecast || current.forecast || [],
    }
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
