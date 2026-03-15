import { useState, useEffect } from 'react'
import { FileText, Plus, Clock, MapPin, Calendar, ChevronRight, BarChart2, CheckCircle, Loader2, TrendingUp } from 'lucide-react'
import toast from 'react-hot-toast'
import { getRequests, createRequest, updateRequestStatus, getTripReport, getPerDiem, getBudgetForecast } from '../api/requests'
import useStore from '../store/useStore'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import Select from '../components/ui/Select'
import Badge from '../components/ui/Badge'
import Modal from '../components/ui/Modal'
import StatCard from '../components/ui/StatCard'
import Spinner from '../components/ui/Spinner'

// Which next status can an employee/manager take from the current status?
const NEXT_STATUS = {
  approved:    { label: 'Mark as Booked',      next: 'booked' },
  booked:      { label: 'Trip Started',        next: 'in_progress' },
  in_progress: { label: 'Mark as Completed',   next: 'completed' },
}

const purposes = [
  { value: 'client_meeting', label: 'Client Meeting' },
  { value: 'conference',     label: 'Conference' },
  { value: 'training',       label: 'Training' },
  { value: 'site_visit',     label: 'Site Visit' },
  { value: 'sales',          label: 'Sales' },
  { value: 'other',          label: 'Other' },
]

const emptyForm = {
  from_city: '', to_city: '', travel_date: '', return_date: '',
  purpose: '', estimated_budget: '', notes: '',
}

export default function Requests() {
  const { auth } = useStore()
  const [requests,    setRequests]   = useState([])
  const [loading,     setLoading]    = useState(true)
  const [modal,       setModal]      = useState(false)
  const [form,        setForm]       = useState(emptyForm)
  const [submitting,  setSubmitting] = useState(false)
  const [errors,      setErrors]     = useState({})
  const [reportModal, setReportModal] = useState(false)
  const [reportData,  setReportData]  = useState(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [perDiem,         setPerDiem]         = useState(null)
  const [forecast,        setForecast]        = useState(null)
  const [forecastLoading, setForecastLoading] = useState(false)

  useEffect(() => { fetchRequests() }, [])

  const fetchRequests = async () => {
    try {
      const data = await getRequests()
      setRequests(Array.isArray(data) ? data : data.requests || [])
    } catch { toast.error('Failed to load requests') }
    finally { setLoading(false) }
  }

  const set = (k, v) => {
    setForm((p) => {
      const next = { ...p, [k]: v }
      const city = next.to_city || next.from_city
      const start = next.travel_date
      const end = next.return_date || start
      if (city && start) {
        const days = end
          ? Math.max(1, Math.round((new Date(end) - new Date(start)) / 86400000) + 1)
          : 1
        getPerDiem(city, days).then(setPerDiem).catch(() => {})
      }
      return next
    })
  }

  const fetchForecast = async () => {
    const { from_city, to_city, travel_date, return_date } = form
    if (!to_city || !travel_date) {
      toast.error('Fill in destination and travel date first')
      return
    }
    setForecastLoading(true)
    setForecast(null)
    try {
      const result = await getBudgetForecast({
        origin: from_city,
        destination: to_city,
        start_date: travel_date,
        end_date: return_date || travel_date,
        trip_type: form.trip_type || 'domestic',
        num_travelers: 1,
      })
      setForecast(result)
    } catch {
      toast.error('Budget forecast unavailable')
    } finally {
      setForecastLoading(false)
    }
  }

  const validate = () => {
    const e = {}
    if (!form.from_city.trim())  e.from_city  = 'Required'
    if (!form.to_city.trim())    e.to_city    = 'Required'
    if (!form.travel_date)       e.travel_date = 'Required'
    if (!form.purpose)           e.purpose    = 'Select purpose'
    return e
  }

  const handleSubmit = async () => {
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setErrors({})
    setSubmitting(true)
    try {
      await createRequest({
        ...form,
        estimated_budget: form.estimated_budget ? parseFloat(form.estimated_budget) : undefined,
      })
      toast.success('Travel request submitted!')
      setModal(false)
      setForm(emptyForm)
      fetchRequests()
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to submit request')
    } finally {
      setSubmitting(false)
    }
  }

  const handleStatusUpdate = async (requestId, newStatus) => {
    try {
      await updateRequestStatus(requestId, newStatus)
      toast.success(`Status updated to ${newStatus.replace('_', ' ')}`)
      fetchRequests()
    } catch (err) {
      toast.error(err.response?.data?.error || 'Status update failed')
    }
  }

  const viewReport = async (requestId) => {
    setReportData(null)
    setReportModal(true)
    setReportLoading(true)
    try {
      const result = await getTripReport(requestId)
      setReportData(result.report || result)
    } catch {
      toast.error('Failed to load report')
      setReportModal(false)
    } finally {
      setReportLoading(false)
    }
  }

  const pending   = requests.filter((r) => r.status === 'pending').length
  const approved  = requests.filter((r) => r.status === 'approved').length
  const rejected  = requests.filter((r) => r.status === 'rejected').length

  return (
    <div className="mx-auto w-full max-w-7xl space-y-4 rounded-3xl border border-[#cdd6e0] bg-[radial-gradient(circle_at_top_left,#f6f9fc_0%,transparent_38%),linear-gradient(180deg,#edf1f5_0%,#E0E1DD_100%)] px-3 pb-6 pt-4 sm:space-y-5 sm:px-5 md:px-6 md:pb-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900 font-heading">Travel Requests</h2>
          <p className="text-sm text-gray-500 mt-0.5">Submit and track your travel requests</p>
        </div>
        <Button leftIcon={<Plus size={16} />} onClick={() => setModal(true)} className="w-full justify-center sm:w-auto">
          New Request
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard icon={<Clock size={20} />}      value={pending}  label="Pending"  accentColor="orange" loading={loading} />
        <StatCard icon={<FileText size={20} />}   value={approved} label="Approved" accentColor="green"  loading={loading} />
        <StatCard icon={<ChevronRight size={20} />} value={rejected} label="Rejected" accentColor="red"   loading={loading} />
      </div>

      {/* Requests list */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-card overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-50">
          <h3 className="font-semibold text-gray-800 font-heading">All Requests</h3>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12"><Spinner size="md" color="accent" /></div>
        ) : requests.length === 0 ? (
          <div className="py-16 text-center">
            <FileText size={32} className="mx-auto text-gray-200 mb-3" />
            <p className="text-gray-400 font-medium">No requests yet</p>
            <Button size="sm" variant="outline" className="mt-4" onClick={() => setModal(true)}>
              Submit your first request
            </Button>
          </div>
        ) : (
          <div className="divide-y divide-gray-50">
            {requests.map((req) => (
              <RequestRow
                key={req.id || req.request_id}
                request={req}
                currentUser={auth.user}
                onStatusUpdate={handleStatusUpdate}
                onViewReport={viewReport}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Trip Report Modal ─────────────────── */}
      <Modal
        open={reportModal}
        onClose={() => { setReportModal(false); setReportData(null) }}
        title="Trip Summary Report"
        subtitle={reportData?.destination ? `${reportData.destination} · ${reportData.dates || ''}` : 'Loading...'}
        width="lg"
      >
        {reportLoading ? (
          <div className="flex items-center justify-center py-12">
            <Spinner size="md" color="accent" />
          </div>
        ) : reportData ? (
          <div className="space-y-4">
            {/* Stats row */}
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: 'Budget',  value: `₹${Number(reportData.budget || 0).toLocaleString('en-IN')}`, color: 'text-gray-700' },
                { label: 'Spent',   value: `₹${Number(reportData.actual_spend || 0).toLocaleString('en-IN')}`,
                  color: (reportData.actual_spend || 0) > (reportData.budget || 0) ? 'text-red-600' : 'text-green-600' },
                { label: 'Days',    value: reportData.duration_days || '—', color: 'text-gray-700' },
              ].map(({ label, value, color }) => (
                <div key={label} className="rounded-xl border border-gray-100 bg-gray-50 p-3 text-center">
                  <p className={`text-lg font-bold ${color}`}>{value}</p>
                  <p className="text-xs text-gray-400">{label}</p>
                </div>
              ))}
            </div>
            {/* Narrative */}
            <div className="rounded-xl border border-gray-100 bg-white p-4">
              <div className="flex items-center gap-2 mb-3">
                <BarChart2 size={14} className="text-accent-500" />
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                  {reportData.ai_generated ? 'AI Executive Summary' : 'Trip Summary'}
                </p>
              </div>
              <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-line">{reportData.narrative}</p>
            </div>
            <div className="flex gap-4 text-xs text-gray-500">
              <span>Expenses: <strong>{reportData.expense_count || 0}</strong></span>
              <span>Meetings: <strong>{reportData.meeting_count || 0}</strong></span>
              <span>Variance: <strong className={reportData.variance > 0 ? 'text-red-600' : 'text-green-600'}>
                ₹{Math.abs(Math.round(reportData.variance || 0)).toLocaleString('en-IN')} {(reportData.variance || 0) > 0 ? 'over' : 'under'}
              </strong></span>
            </div>
          </div>
        ) : null}
      </Modal>

      {/* ── New Request Modal ──────────────────── */}
      <Modal
        open={modal}
        onClose={() => { setModal(false); setForm(emptyForm); setErrors({}); setPerDiem(null); setForecast(null) }}
        title="New Travel Request"
        width="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setModal(false)}>Cancel</Button>
            <Button loading={submitting} onClick={handleSubmit}>Submit Request</Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="From City"
              placeholder="e.g. Mumbai"
              value={form.from_city}
              onChange={(e) => set('from_city', e.target.value)}
              error={errors.from_city}
              leftIcon={<MapPin size={16} />}
              required
            />
            <Input
              label="To City"
              placeholder="e.g. Delhi"
              value={form.to_city}
              onChange={(e) => set('to_city', e.target.value)}
              error={errors.to_city}
              leftIcon={<MapPin size={16} />}
              required
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="Travel Date"
              type="date"
              value={form.travel_date}
              onChange={(e) => set('travel_date', e.target.value)}
              error={errors.travel_date}
              leftIcon={<Calendar size={16} />}
              required
            />
            <Input
              label="Return Date"
              type="date"
              value={form.return_date}
              onChange={(e) => set('return_date', e.target.value)}
              leftIcon={<Calendar size={16} />}
              hint="Optional"
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Select
              label="Purpose"
              options={purposes}
              placeholder="Select purpose"
              value={form.purpose}
              onChange={(e) => set('purpose', e.target.value)}
              error={errors.purpose}
              required
            />
            <Input
              label="Estimated Budget (₹)"
              type="number"
              placeholder="Optional"
              value={form.estimated_budget}
              onChange={(e) => set('estimated_budget', e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-700">Notes</label>
            <textarea
              rows={3}
              placeholder="Additional context or requirements..."
              value={form.notes}
              onChange={(e) => set('notes', e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-accent-500/20 focus:border-accent-500 transition-all resize-none hover:border-gray-300"
            />
          </div>

          {/* Per Diem Estimate */}
          {perDiem?.success && (
            <div className="rounded-xl border border-accent-100 bg-accent-50 p-4">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-semibold text-accent-700 uppercase tracking-wide">
                  Estimated Per Diem Allowance
                </p>
                <span className="rounded-full border border-accent-200 bg-white px-2 py-0.5 text-[10px] font-medium text-accent-600 capitalize">
                  {perDiem.tier?.replace('_', ' ')}
                </span>
              </div>
              <p className="text-2xl font-bold text-accent-900">
                ₹{Number(perDiem.total_allowance).toLocaleString('en-IN')}
                <span className="text-sm font-normal text-accent-600 ml-2">for {perDiem.days} day{perDiem.days !== 1 ? 's' : ''}</span>
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {Object.entries(perDiem.daily_rates || {}).map(([key, val]) => (
                  <span key={key} className="text-xs text-accent-600 bg-white rounded-lg border border-accent-100 px-2 py-1">
                    {key.replace('_', ' ')}: ₹{val}/day
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Budget Forecast */}
          <div>
            <Button
              variant="secondary"
              size="sm"
              leftIcon={forecastLoading ? <Loader2 size={14} className="animate-spin" /> : <TrendingUp size={14} />}
              onClick={fetchForecast}
              disabled={forecastLoading}
              className="border border-[#d5deea] bg-white text-[#1B263B] hover:bg-[#f6fafe]"
            >
              {forecastLoading ? 'Forecasting...' : 'Get Budget Forecast'}
            </Button>

            {forecast?.success && (
              <div className="mt-3 rounded-xl border border-emerald-100 bg-emerald-50 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold text-emerald-700 uppercase tracking-wide">
                    AI Budget Forecast · {forecast.duration_days} day{forecast.duration_days !== 1 ? 's' : ''}
                  </p>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium border ${
                    forecast.confidence === 'high'   ? 'bg-emerald-100 text-emerald-700 border-emerald-200' :
                    forecast.confidence === 'medium' ? 'bg-yellow-100 text-yellow-700 border-yellow-200' :
                                                       'bg-gray-100 text-gray-600 border-gray-200'
                  }`}>
                    {forecast.confidence} confidence
                  </span>
                </div>

                {/* Range bar */}
                <div className="grid grid-cols-3 gap-2 text-center">
                  {[
                    { label: 'Min',  val: forecast.forecast?.min,  cls: 'text-emerald-600' },
                    { label: 'Mid',  val: forecast.forecast?.mid,  cls: 'text-emerald-800 font-bold text-lg' },
                    { label: 'Max',  val: forecast.forecast?.max,  cls: 'text-red-500' },
                  ].map(({ label, val, cls }) => (
                    <div key={label} className="rounded-lg border border-emerald-100 bg-white py-2 px-1">
                      <p className={`text-sm ${cls}`}>₹{Number(val || 0).toLocaleString('en-IN')}</p>
                      <p className="text-[10px] text-gray-400 mt-0.5">{label}</p>
                    </div>
                  ))}
                </div>

                {/* Breakdown */}
                <div className="flex flex-wrap gap-2 text-xs">
                  {[
                    { k: 'Flight', v: forecast.breakdown?.flight?.mid },
                    { k: 'Hotel', v: forecast.breakdown?.hotel },
                    { k: 'Per Diem', v: forecast.breakdown?.per_diem },
                    { k: 'Misc', v: forecast.breakdown?.misc_buffer },
                  ].map(({ k, v }) => v != null && (
                    <span key={k} className="rounded-lg border border-emerald-100 bg-white px-2 py-1 text-emerald-700">
                      {k}: ₹{Number(v).toLocaleString('en-IN')}
                    </span>
                  ))}
                </div>

                {forecast.historical_trips > 0 && (
                  <p className="text-xs text-emerald-600">
                    Based on {forecast.historical_trips} historical trip{forecast.historical_trips !== 1 ? 's' : ''} to {forecast.destination}
                    {forecast.historical_avg ? ` · avg spend ₹${Number(forecast.historical_avg).toLocaleString('en-IN')}` : ''}
                  </p>
                )}

                {forecast.ai_insight && (
                  <p className="text-xs text-gray-600 italic border-t border-emerald-100 pt-2">{forecast.ai_insight}</p>
                )}

                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => set('estimated_budget', String(forecast.forecast?.mid || ''))}
                  className="border border-emerald-200 bg-white text-emerald-700 hover:bg-emerald-50 text-xs"
                >
                  Use ₹{Number(forecast.forecast?.mid || 0).toLocaleString('en-IN')} as Budget
                </Button>
              </div>
            )}
          </div>
        </div>
      </Modal>
    </div>
  )
}

function RequestRow({ request: r, currentUser, onStatusUpdate, onViewReport }) {
  const [transitioning, setTransitioning] = useState(false)
  const rawStatus = r.raw_status || r.status || ''
  const transition = NEXT_STATUS[rawStatus]
  const isOwner = currentUser && (currentUser.id === r.user_id || currentUser.role === 'admin' || currentUser.role === 'manager')

  const handleTransition = async () => {
    if (!transition || !isOwner) return
    setTransitioning(true)
    try {
      await onStatusUpdate(r.request_id || r.id, transition.next)
    } finally {
      setTransitioning(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 px-4 py-4 transition-colors hover:bg-gray-50/50 sm:px-6">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-accent-100 bg-accent-50">
          <FileText size={15} className="text-accent-600" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-gray-800">
            {r.from_city} → {r.to_city}
          </p>
          <div className="mt-0.5 flex flex-wrap items-center gap-2">
            <span className="text-xs text-gray-400">{r.travel_date}</span>
            {r.purpose && (
              <span className="text-xs text-gray-400 capitalize">· {r.purpose.replace('_', ' ')}</span>
            )}
            {r.request_id && (
              <span className="text-[10px] text-gray-300 font-mono">{r.request_id}</span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {r.estimated_budget ? (
            <span className="text-sm font-medium text-gray-700">
              ₹{Number(r.estimated_budget).toLocaleString('en-IN')}
            </span>
          ) : null}
          <Badge status={rawStatus || 'pending'} dot>
            {(rawStatus || 'pending').replace('_', ' ')}
          </Badge>
        </div>
      </div>

      {/* Status action buttons */}
      {isOwner && (transition || rawStatus === 'completed') && (
        <div className="flex flex-wrap gap-2 pl-12">
          {transition && (
            <button
              type="button"
              onClick={handleTransition}
              disabled={transitioning}
              className="flex items-center gap-1.5 rounded-lg border border-accent-200 bg-accent-50 px-3 py-1.5 text-xs font-medium text-accent-700 transition-colors hover:bg-accent-100 disabled:opacity-50"
            >
              {transitioning
                ? <Loader2 size={11} className="animate-spin" />
                : <CheckCircle size={11} />}
              {transition.label}
            </button>
          )}
          {rawStatus === 'completed' && (
            <button
              type="button"
              onClick={() => onViewReport(r.request_id || r.id)}
              className="flex items-center gap-1.5 rounded-lg border border-green-200 bg-green-50 px-3 py-1.5 text-xs font-medium text-green-700 transition-colors hover:bg-green-100"
            >
              <BarChart2 size={11} />
              View Report
            </button>
          )}
        </div>
      )}
    </div>
  )
}
