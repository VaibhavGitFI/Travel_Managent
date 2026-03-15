import { useState } from 'react'
import { Hotel, MapPin, Calendar, Search, Star, Wifi, Coffee, Car, Dumbbell, Users, Moon } from 'lucide-react'
import toast from 'react-hot-toast'
import axios from '../api/client'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import Badge from '../components/ui/Badge'
import Spinner from '../components/ui/Spinner'

const amenityIcons = { wifi: Wifi, breakfast: Coffee, parking: Car, gym: Dumbbell }

const initialForm = {
  city: '',
  check_in: '',
  check_out: '',
  guests: '1',
  type: 'hotel',
}

export default function Accommodation() {
  const [form, setForm] = useState(initialForm)
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(null)
  const [pgResults, setPgResults] = useState(null)
  const [errors, setErrors] = useState({})

  const today = new Date().toISOString().split('T')[0]
  const panelClass = 'rounded-xl border border-[#d2dae4] bg-white shadow-[0_12px_24px_rgba(27,38,59,0.08)]'
  const formInputClass =
    '!h-12 !rounded-2xl !border-[#d7e1ec] !bg-[#f4f7fb] !text-[15px] !text-[#1B263B] placeholder:!text-[#8594a8] focus:!border-[#4CC9F0] focus:!ring-2 focus:!ring-[#4CC9F0]/20'

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }))

  const calcDays = () => {
    if (!form.check_in || !form.check_out) return 0
    const diff = new Date(form.check_out) - new Date(form.check_in)
    return Math.max(0, Math.floor(diff / 86400000))
  }

  const days = calcDays()
  const isLongStay = days >= 5

  const handleReset = () => {
    setForm(initialForm)
    setErrors({})
    setResults(null)
    setPgResults(null)
  }

  const handleSearch = async (e) => {
    e.preventDefault()
    const errs = {}
    if (!form.city.trim()) errs.city = 'City required'
    if (!form.check_in) errs.check_in = 'Check-in required'
    if (!form.check_out) errs.check_out = 'Check-out required'
    if (form.check_in && form.check_out && form.check_out <= form.check_in) {
      errs.check_out = 'Check-out must be after check-in'
    }

    if (Object.keys(errs).length) {
      setErrors(errs)
      return
    }

    setErrors({})
    setLoading(true)
    setResults(null)
    setPgResults(null)

    const shouldFetchPg = isLongStay

    try {
      const [hotelRes, pgRes] = await Promise.allSettled([
        axios.get('/accommodation/search', { params: form }),
        shouldFetchPg
          ? axios.post('/accommodation/pg-options', { city: form.city, duration_days: days || 1 })
          : Promise.resolve(null),
      ])

      const hotelSuccess = hotelRes.status === 'fulfilled'
      const pgSuccess = pgRes.status === 'fulfilled' && pgRes.value?.data

      if (hotelSuccess) setResults(hotelRes.value.data)
      if (pgSuccess) setPgResults(pgRes.value.data)

      if (!hotelSuccess && !pgSuccess) {
        toast.error('Search failed. Please try again.')
        return
      }

      toast.success('Accommodation options loaded')
    } catch (err) {
      toast.error(err.response?.data?.error || 'Search failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const hotelList = Array.isArray(results?.hotels) ? results.hotels : []
  const pgList = Array.isArray(pgResults?.pg_options) ? pgResults.pg_options : []
  const showHotels = hotelList.length > 0
  const showPg = pgList.length > 0

  return (
    <div className="mx-auto w-full max-w-7xl space-y-4 rounded-3xl border border-[#cdd6e0] bg-[radial-gradient(circle_at_top_left,#f6f9fc_0%,transparent_38%),linear-gradient(180deg,#edf1f5_0%,#E0E1DD_100%)] px-3 pb-5 pt-3 sm:space-y-5 sm:px-5 md:px-6 md:pb-6">
      <form onSubmit={handleSearch} className={`${panelClass} p-4 sm:p-4`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="space-y-0.5">
            <h2 className="font-heading text-lg font-semibold text-[#1B263B]">Find Accommodation</h2>
            <p className="text-xs text-[#778DA9]">Quick search by city, dates, and guests.</p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="border border-gray-200 text-gray-600 hover:bg-gray-50"
            onClick={handleReset}
          >
            Reset
          </Button>
        </div>

        <div className="mt-4 space-y-3">
          <Input
            aria-label="Destination City"
            placeholder="Enter city or hotel name"
            value={form.city}
            onChange={(e) => set('city', e.target.value)}
            error={errors.city}
            leftIcon={<MapPin size={18} />}
            size="lg"
            inputClassName={formInputClass}
            required
          />

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input
              aria-label="Check-in Date"
              type="date"
              min={today}
              value={form.check_in}
              onChange={(e) => set('check_in', e.target.value)}
              error={errors.check_in}
              leftIcon={<Calendar size={18} />}
              size="lg"
              inputClassName={formInputClass}
              required
            />
            <Input
              aria-label="Check-out Date"
              type="date"
              min={form.check_in || today}
              value={form.check_out}
              onChange={(e) => set('check_out', e.target.value)}
              error={errors.check_out}
              leftIcon={<Calendar size={18} />}
              size="lg"
              inputClassName={formInputClass}
              required
            />
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input
              aria-label="Guests"
              type="number"
              min="1"
              max="10"
              placeholder="Guests"
              value={form.guests}
              onChange={(e) => set('guests', e.target.value)}
              leftIcon={<Users size={18} />}
              size="lg"
              inputClassName={formInputClass}
            />
            <Input
              aria-label="Nights"
              value={days > 0 ? `${days} night${days !== 1 ? 's' : ''}` : ''}
              placeholder="Nights"
              readOnly
              leftIcon={<Moon size={18} />}
              size="lg"
              inputClassName={`${formInputClass} !cursor-default`}
            />
          </div>

          <Button
            type="submit"
            variant="secondary"
            size="lg"
            loading={loading}
            leftIcon={<Search size={18} />}
            className="h-12 w-full justify-center rounded-2xl border border-[#4CC9F0] bg-[#4CC9F0] text-[#1B263B] hover:bg-[#35bee9]"
          >
            {loading ? (isLongStay ? 'Searching PG…' : 'Searching…') : (isLongStay ? 'Search PG' : 'Search')}
          </Button>
        </div>

        <div className="mt-3 rounded-lg border border-[#dfe6ef] bg-[#f8fbff] px-3 py-2 text-xs text-[#44566f]">
          {days > 0 ? (
            <>
              Stay duration: <span className="font-medium text-[#1B263B]">{days} night{days !== 1 ? 's' : ''}</span>
              {isLongStay && (
                <span className="ml-2 font-medium text-[#1B263B]">Long-stay options enabled.</span>
              )}
            </>
          ) : (
            'Pick check-in and check-out to calculate stay duration.'
          )}
        </div>
      </form>

      <div className="space-y-4">
          {loading && (
            <div className={`${panelClass} flex flex-col items-center gap-4 p-8 sm:p-12`}>
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#4CC9F0]">
                <Spinner size="md" color="dark" />
              </div>
              <div className="text-center">
                <p className="font-heading text-base font-semibold text-[#1B263B]">Searching accommodation…</p>
                <p className="mt-1 text-sm text-[#778DA9]">Getting the best stay options for your dates.</p>
              </div>
            </div>
          )}

          {!loading && !results && !pgResults && (
            <div className={`${panelClass} p-8 text-center sm:p-12`}>
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-[#d2e4ef] bg-[#eef8fd]">
                <Hotel size={28} className="text-[#1B263B]" />
              </div>
              <h3 className="font-heading text-lg font-semibold text-[#1B263B]">Search for accommodation</h3>
              <p className="mx-auto mt-1 max-w-sm text-sm text-[#778DA9]">
                Enter destination and dates to explore available stays.
              </p>
            </div>
          )}

          {!loading && (results || pgResults) && (
            <div className="space-y-5 animate-fade-in">
              {showHotels && (
                <section className="space-y-3">
                  <h3 className="font-heading text-base font-semibold text-[#1B263B]">
                    Hotels ({hotelList.length})
                  </h3>
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-2">
                    {hotelList.map((hotel, idx) => (
                      <HotelCard key={idx} hotel={hotel} nights={days} />
                    ))}
                  </div>
                </section>
              )}

              {showPg && (
                <section className="space-y-3">
                  <div className="flex items-center gap-2">
                    <h3 className="font-heading text-base font-semibold text-[#1B263B]">
                      PG / Serviced Apartments
                    </h3>
                    <Badge variant="accent" size="xs">Long Stay</Badge>
                  </div>
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-2">
                    {pgList.map((pg, idx) => (
                      <PGCard key={idx} pg={pg} />
                    ))}
                  </div>
                </section>
              )}

              {!showHotels && !showPg && (
                <div className={`${panelClass} p-6 text-sm text-[#44566f]`}>
                  No matching accommodation found for the selected filters. Try another city or date range.
                </div>
              )}
            </div>
          )}
      </div>
    </div>
  )
}

function HotelCard({ hotel: h, nights }) {
  const total = h.price_per_night && nights ? h.price_per_night * nights : null

  return (
    <article className="rounded-xl border border-[#d2dae4] bg-white p-5 shadow-[0_10px_20px_rgba(27,38,59,0.07)] transition-shadow hover:shadow-[0_14px_26px_rgba(27,38,59,0.1)]">
      <div className="mb-3 flex items-start justify-between">
        <div className="min-w-0 flex-1 pr-2">
          <h4 className="font-semibold text-[#1B263B]">{h.name || h.hotel_name}</h4>
          {h.location && (
            <p className="mt-0.5 flex items-center gap-1 text-xs text-[#778DA9]">
              <MapPin size={10} />
              {h.location}
            </p>
          )}
        </div>
        {h.stars && (
          <div className="flex shrink-0 items-center gap-0.5">
            {Array.from({ length: h.stars }).map((_, i) => (
              <Star key={i} size={12} className="fill-warning-400 text-warning-400" />
            ))}
          </div>
        )}
      </div>

      {h.rating && (
        <div className="mb-3 flex items-center gap-2">
          <span className="rounded bg-success-600 px-2 py-0.5 text-xs font-bold text-white">{h.rating}</span>
          <span className="text-xs text-[#778DA9]">Guest rating</span>
        </div>
      )}

      {h.amenities?.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {h.amenities.slice(0, 4).map((a) => {
            const Icon = amenityIcons[a.toLowerCase()] || null
            return (
              <span key={a} className="flex items-center gap-1 rounded-full border border-[#dbe4ef] bg-[#f8fbff] px-2 py-0.5 text-xs text-[#44566f]">
                {Icon && <Icon size={10} />}
                {a}
              </span>
            )
          })}
        </div>
      )}

      <div className="mt-4 flex items-end justify-between border-t border-[#e6ecf2] pt-4">
        <div>
          {h.price_per_night && (
            <div className="text-lg font-bold text-[#1B263B]">
              ₹{typeof h.price_per_night === 'number'
                ? h.price_per_night.toLocaleString('en-IN')
                : h.price_per_night}
            </div>
          )}
          <div className="text-xs text-[#778DA9]">/night</div>
        </div>
        {total && (
          <div className="text-right">
            <div className="text-sm font-semibold text-[#1B263B]">
              ₹{total.toLocaleString('en-IN')} total
            </div>
            <div className="text-xs text-[#778DA9]">{nights} nights</div>
          </div>
        )}
      </div>

      <Button fullWidth size="sm" variant="secondary" className="mt-4 border border-[#d2dae4] text-[#1B263B] hover:bg-[#f6f9fc]">
        Book Now
      </Button>
    </article>
  )
}

function PGCard({ pg }) {
  return (
    <article className="rounded-xl border border-[#d2dae4] bg-white p-5 shadow-[0_10px_20px_rgba(27,38,59,0.07)] transition-shadow hover:shadow-[0_14px_26px_rgba(27,38,59,0.1)]">
      <div className="mb-2 flex items-center gap-2">
        <Badge variant="blue" size="xs">PG / Serviced</Badge>
        {pg.provider && <span className="text-xs text-[#778DA9]">{pg.provider}</span>}
      </div>
      <h4 className="font-semibold text-[#1B263B]">{pg.name}</h4>
      {pg.location && (
        <p className="mt-0.5 flex items-center gap-1 text-xs text-[#778DA9]">
          <MapPin size={10} />{pg.location}
        </p>
      )}

      {pg.amenities?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {pg.amenities.slice(0, 4).map((a) => (
            <span key={a} className="rounded-full border border-[#dbe4ef] bg-[#f8fbff] px-2 py-0.5 text-xs text-[#44566f]">
              {a}
            </span>
          ))}
        </div>
      )}

      <div className="mt-4 border-t border-[#e6ecf2] pt-4">
        {pg.monthly_rent && (
          <div className="text-lg font-bold text-[#1B263B]">
            ₹{typeof pg.monthly_rent === 'number'
              ? pg.monthly_rent.toLocaleString('en-IN')
              : pg.monthly_rent}
            <span className="text-xs font-normal text-[#778DA9]"> /month</span>
          </div>
        )}
        {pg.price_per_night && (
          <div className="text-lg font-bold text-[#1B263B]">
            ₹{typeof pg.price_per_night === 'number'
              ? pg.price_per_night.toLocaleString('en-IN')
              : pg.price_per_night}
            <span className="text-xs font-normal text-[#778DA9]"> /night</span>
          </div>
        )}
      </div>

      <Button fullWidth size="sm" variant="secondary" className="mt-4 border border-[#d2dae4] text-[#1B263B] hover:bg-[#f6f9fc]">
        Enquire
      </Button>
    </article>
  )
}
