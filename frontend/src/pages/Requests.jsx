import { useState, useEffect, useRef } from 'react'
import ReactDOM from 'react-dom'
import { cn } from '../lib/cn'
import {
  FileText, Plus, Clock, MapPin, Calendar, ChevronRight, BarChart2, CheckCircle,
  Loader2, TrendingUp, Search, Brain, Plane, Briefcase, IndianRupee, StickyNote,
  ArrowRight, Zap, Shield,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { getRequests, createRequest, updateRequestStatus, getTripReport, getPerDiem, getBudgetForecast } from '../api/requests'
import useStore from '../store/useStore'
import useAutoRefresh from '../hooks/useAutoRefresh'
import usePagination from '../hooks/usePagination'
import Badge from '../components/ui/Badge'
import StatCard from '../components/ui/StatCard'
import Spinner from '../components/ui/Spinner'
import { SkeletonRow } from '../components/ui/Skeleton'
import Pagination from '../components/ui/Pagination'

const NEXT_STATUS = {
  approved:    { label: 'Mark as Booked',    next: 'booked' },
  booked:      { label: 'Trip Started',      next: 'in_progress' },
  in_progress: { label: 'Mark Completed',    next: 'completed' },
}

const PURPOSES = [
  { value: 'client_meeting', label: 'Client Meeting' },
  { value: 'conference',     label: 'Conference' },
  { value: 'training',       label: 'Training' },
  { value: 'site_visit',     label: 'Site Visit' },
  { value: 'sales',          label: 'Sales' },
  { value: 'other',          label: 'Other' },
]

const EMPTY = { from_city: '', to_city: '', travel_date: '', return_date: '', purpose: '', estimated_budget: '', notes: '' }

const STATUS_STYLE = {
  approved:    { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', dot: 'bg-emerald-500' },
  pending:     { bg: 'bg-amber-50',   text: 'text-amber-700',   border: 'border-amber-200',   dot: 'bg-amber-500' },
  rejected:    { bg: 'bg-red-50',     text: 'text-red-700',     border: 'border-red-200',     dot: 'bg-red-500' },
  booked:      { bg: 'bg-sky-50',     text: 'text-sky-700',     border: 'border-sky-200',     dot: 'bg-sky-500' },
  in_progress: { bg: 'bg-blue-50',    text: 'text-blue-700',    border: 'border-blue-200',    dot: 'bg-blue-500' },
  completed:   { bg: 'bg-gray-50',    text: 'text-gray-600',    border: 'border-gray-200',    dot: 'bg-gray-400' },
  draft:       { bg: 'bg-gray-50',    text: 'text-gray-500',    border: 'border-gray-200',    dot: 'bg-gray-300' },
}

const inputBase = 'w-full rounded-lg border border-gray-200 bg-white px-3.5 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 transition-all hover:border-gray-300 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/15'
const inputIcon = 'pl-10'
const labelCls = 'mb-1 block text-[11px] font-semibold uppercase tracking-wide text-gray-500'

export default function Requests() {
  const { auth } = useStore()
  const { items: requests, page, totalPages, total, search, loading, goToPage, setSearch, refresh } = usePagination(getRequests)
  const [modal, setModal] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [submitting, setSubmitting] = useState(false)
  const [errors, setErrors] = useState({})
  const [reportModal, setReportModal] = useState(false)
  const [reportData, setReportData] = useState(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [perDiem, setPerDiem] = useState(null)
  const [forecast, setForecast] = useState(null)
  const [forecastLoading, setForecastLoading] = useState(false)
  const pdTimer = useRef(null)

  useEffect(() => () => clearTimeout(pdTimer.current), [])
  useAutoRefresh('requests', refresh)

  const set = (k, v) => {
    setForm((p) => {
      const next = { ...p, [k]: v }
      const city = next.to_city || next.from_city
      const start = next.travel_date
      const end = next.return_date || start
      if (city && start) {
        const days = Math.max(1, Math.round((new Date(end) - new Date(start)) / 86400000) + 1)
        clearTimeout(pdTimer.current)
        pdTimer.current = setTimeout(() => { getPerDiem(city, days).then(setPerDiem).catch(() => {}) }, 500)
      }
      return next
    })
  }

  const fetchForecast = async () => {
    if (!form.to_city || !form.travel_date) { toast.error('Fill destination and date first'); return }
    setForecastLoading(true); setForecast(null)
    try {
      setForecast(await getBudgetForecast({ origin: form.from_city, destination: form.to_city, start_date: form.travel_date, end_date: form.return_date || form.travel_date, trip_type: 'domestic', num_travelers: 1 }))
    } catch { toast.error('Forecast unavailable') }
    finally { setForecastLoading(false) }
  }

  const handleSubmit = async () => {
    const e = {}
    if (!form.from_city.trim()) e.from_city = 'Required'
    if (!form.to_city.trim()) e.to_city = 'Required'
    if (!form.travel_date) e.travel_date = 'Required'
    if (!form.purpose) e.purpose = 'Required'
    if (Object.keys(e).length) { setErrors(e); return }
    setErrors({}); setSubmitting(true)
    try {
      await createRequest({ ...form, estimated_budget: form.estimated_budget ? parseFloat(form.estimated_budget) : undefined })
      toast.success('Request submitted!'); setModal(false); setForm(EMPTY); setPerDiem(null); setForecast(null); refresh()
    } catch (err) { toast.error(err.response?.data?.error || 'Failed to submit') }
    finally { setSubmitting(false) }
  }

  const handleStatus = async (id, status) => {
    try { await updateRequestStatus(id, status); toast.success(`Status: ${status.replace('_', ' ')}`); refresh() }
    catch (err) { toast.error(err.response?.data?.error || 'Update failed') }
  }

  const viewReport = async (id) => {
    setReportData(null); setReportModal(true); setReportLoading(true)
    try { const r = await getTripReport(id); setReportData(r.report || r) }
    catch { toast.error('Failed to load report'); setReportModal(false) }
    finally { setReportLoading(false) }
  }

  const pending = requests.filter(r => r.status === 'pending').length
  const approved = requests.filter(r => r.status === 'approved').length
  const rejected = requests.filter(r => r.status === 'rejected').length

  return (
    <div className="mx-auto w-full max-w-7xl space-y-5">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-blue-600">
              <FileText size={14} className="text-white" />
            </div>
            <h1 className="font-heading text-xl font-bold text-gray-900">Travel Requests</h1>
            <span className="rounded-full bg-indigo-50 border border-indigo-200 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-indigo-600">
              AI Forecast
            </span>
          </div>
          <p className="mt-1 text-sm text-gray-500">Submit, track, and manage your travel requests</p>
        </div>
        <button onClick={() => setModal(true)}
          className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-blue-500 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:shadow-md hover:brightness-105 sm:w-auto w-full">
          <Plus size={15} /> New Request
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <StatCard icon={<Clock size={20} />} value={loading ? '—' : pending} label="Pending" accentColor="orange" className="rounded-xl border border-gray-200 bg-white shadow-card" loading={loading} />
        <StatCard icon={<CheckCircle size={20} />} value={loading ? '—' : approved} label="Approved" accentColor="green" className="rounded-xl border border-gray-200 bg-white shadow-card" loading={loading} />
        <StatCard icon={<ChevronRight size={20} />} value={loading ? '—' : rejected} label="Rejected" accentColor="red" className="rounded-xl border border-gray-200 bg-white shadow-card" loading={loading} />
      </div>

      {/* Request List */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-card overflow-hidden">
        <div className="flex flex-col gap-3 px-5 py-4 border-b border-gray-100 sm:flex-row sm:items-center sm:justify-between">
          <h3 className="text-sm font-semibold text-gray-900">All Requests</h3>
          <div className="relative w-full sm:w-56">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input type="text" placeholder="Search city or purpose..." value={search} onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-lg border border-gray-200 bg-white py-2 pl-9 pr-3 text-sm text-gray-700 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/15 focus:border-blue-500" />
          </div>
        </div>

        {loading ? (
          <div className="divide-y divide-gray-100">{Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}</div>
        ) : requests.length === 0 ? (
          <div className="py-16 text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-gray-100 to-gray-200">
              <FileText size={24} className="text-gray-400" />
            </div>
            <p className="font-semibold text-gray-700">No requests yet</p>
            <p className="mt-1 text-sm text-gray-500">Submit your first travel request</p>
            <button onClick={() => setModal(true)}
              className="mt-4 inline-flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
              <Plus size={14} /> New Request
            </button>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {requests.map(r => <RequestRow key={r.id || r.request_id} request={r} user={auth.user} onStatus={handleStatus} onReport={viewReport} />)}
          </div>
        )}
        <Pagination page={page} totalPages={totalPages} total={total} onPageChange={goToPage} className="border-t border-gray-100" />
      </div>

      {/* ── New Request Modal ──────────────────── */}
      {modal && ReactDOM.createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center overflow-y-auto p-4"
          onClick={(e) => { if (e.target === e.currentTarget) { setModal(false); setErrors({}); setPerDiem(null); setForecast(null) } }}
          style={{ background: 'rgba(15,23,42,0.6)', backdropFilter: 'blur(6px)', WebkitBackdropFilter: 'blur(6px)' }}>
          <div className="relative w-full max-w-lg rounded-2xl bg-white shadow-2xl max-h-[90vh] overflow-y-auto">
            <div className="border-b border-gray-100 px-6 py-4 sticky top-0 bg-white z-10">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-blue-600">
                  <FileText size={14} className="text-white" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-gray-900">New Travel Request</h3>
                  <p className="text-xs text-gray-500">Fill in details and get AI budget forecast</p>
                </div>
              </div>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <Fld label="From" error={errors.from_city}>
                  <div className="relative">
                    <MapPin size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input className={cn(inputBase, inputIcon)} placeholder="Origin city" value={form.from_city} onChange={(e) => set('from_city', e.target.value)} />
                  </div>
                </Fld>
                <Fld label="To" error={errors.to_city}>
                  <div className="relative">
                    <MapPin size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-indigo-500" />
                    <input className={cn(inputBase, inputIcon)} placeholder="Destination" value={form.to_city} onChange={(e) => set('to_city', e.target.value)} />
                  </div>
                </Fld>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Fld label="Travel Date" error={errors.travel_date}>
                  <input type="date" className={inputBase} value={form.travel_date} onChange={(e) => set('travel_date', e.target.value)} />
                </Fld>
                <Fld label="Return" hint="Optional">
                  <input type="date" className={inputBase} value={form.return_date} onChange={(e) => set('return_date', e.target.value)} />
                </Fld>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Fld label="Purpose" error={errors.purpose}>
                  <div className="relative">
                    <Briefcase size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <select className={cn(inputBase, inputIcon, 'appearance-none')} value={form.purpose} onChange={(e) => set('purpose', e.target.value)}>
                      <option value="">Select</option>
                      {PURPOSES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                    </select>
                  </div>
                </Fld>
                <Fld label="Budget (₹)" hint="Optional">
                  <div className="relative">
                    <IndianRupee size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input type="number" className={cn(inputBase, inputIcon)} placeholder="0" value={form.estimated_budget} onChange={(e) => set('estimated_budget', e.target.value)} />
                  </div>
                </Fld>
              </div>
              <Fld label="Notes" hint="Optional">
                <textarea rows={2} className={cn(inputBase, 'resize-none')} placeholder="Additional context..."
                  value={form.notes} onChange={(e) => set('notes', e.target.value)} />
              </Fld>

              {/* Per Diem */}
              {perDiem?.success && (
                <div className="rounded-lg border border-blue-100 bg-blue-50 p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] font-semibold uppercase tracking-wide text-blue-600">Per Diem Allowance</span>
                    <span className="rounded bg-white border border-blue-100 px-1.5 py-0.5 text-[10px] font-medium text-blue-600 capitalize">{perDiem.tier?.replace('_', ' ')}</span>
                  </div>
                  <p className="text-lg font-bold text-gray-900">₹{Number(perDiem.total_allowance).toLocaleString('en-IN')} <span className="text-xs font-normal text-gray-500">for {perDiem.days} day{perDiem.days !== 1 ? 's' : ''}</span></p>
                </div>
              )}

              {/* Forecast button + result */}
              <button type="button" onClick={fetchForecast} disabled={forecastLoading}
                className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50">
                {forecastLoading ? <Spinner size="xs" /> : <Brain size={13} className="text-indigo-500" />}
                {forecastLoading ? 'Forecasting...' : 'Get AI Budget Forecast'}
              </button>

              {forecast?.success && (
                <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-semibold uppercase tracking-wide text-indigo-600">AI Budget Forecast</span>
                    <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-bold border',
                      forecast.confidence === 'high' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200')}>
                      {forecast.confidence}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    {[
                      { l: 'Min', v: forecast.forecast?.min, c: 'text-emerald-700' },
                      { l: 'Estimate', v: forecast.forecast?.mid, c: 'text-indigo-800 font-bold text-base' },
                      { l: 'Max', v: forecast.forecast?.max, c: 'text-red-600' },
                    ].map(({ l, v, c }) => (
                      <div key={l} className="rounded-lg border border-indigo-100 bg-white py-2">
                        <p className={cn('text-sm', c)}>₹{Number(v || 0).toLocaleString('en-IN')}</p>
                        <p className="text-[10px] text-gray-400">{l}</p>
                      </div>
                    ))}
                  </div>
                  {forecast.ai_insight && <p className="text-xs text-gray-600">{forecast.ai_insight}</p>}
                  <button onClick={() => set('estimated_budget', String(forecast.forecast?.mid || ''))}
                    className="flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-50">
                    <Zap size={11} /> Use ₹{Number(forecast.forecast?.mid || 0).toLocaleString('en-IN')} as budget
                  </button>
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 border-t border-gray-100 px-6 py-4 sticky bottom-0 bg-white">
              <button onClick={() => { setModal(false); setErrors({}); setPerDiem(null); setForecast(null) }}
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Cancel</button>
              <button onClick={handleSubmit} disabled={submitting}
                className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-indigo-600 to-blue-500 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
                {submitting ? <Spinner size="xs" color="white" /> : <FileText size={14} />}
                Submit Request
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* ── Report Modal ──────────────────────── */}
      {reportModal && ReactDOM.createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center overflow-y-auto p-4"
          onClick={(e) => { if (e.target === e.currentTarget) { setReportModal(false); setReportData(null) } }}
          style={{ background: 'rgba(15,23,42,0.6)', backdropFilter: 'blur(6px)', WebkitBackdropFilter: 'blur(6px)' }}>
          <div className="relative w-full max-w-lg rounded-2xl bg-white shadow-2xl">
            <div className="border-b border-gray-100 px-6 py-4">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-500 to-teal-600">
                  <BarChart2 size={14} className="text-white" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-gray-900">Trip Summary Report</h3>
                  <p className="text-xs text-gray-500">{reportData?.destination || 'Loading...'}</p>
                </div>
              </div>
            </div>
            <div className="px-6 py-5">
              {reportLoading ? (
                <div className="flex items-center justify-center py-12"><Spinner size="md" /></div>
              ) : reportData ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { l: 'Budget', v: `₹${Number(reportData.budget || 0).toLocaleString('en-IN')}`, c: 'text-gray-700' },
                      { l: 'Spent', v: `₹${Number(reportData.actual_spend || 0).toLocaleString('en-IN')}`, c: (reportData.actual_spend || 0) > (reportData.budget || 0) ? 'text-red-600' : 'text-emerald-600' },
                      { l: 'Days', v: reportData.duration_days || '—', c: 'text-gray-700' },
                    ].map(({ l, v, c }) => (
                      <div key={l} className="rounded-lg border border-gray-100 bg-gray-50 p-3 text-center">
                        <p className={cn('text-lg font-bold', c)}>{v}</p>
                        <p className="text-[10px] text-gray-400">{l}</p>
                      </div>
                    ))}
                  </div>
                  <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Brain size={13} className="text-indigo-500" />
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">
                        {reportData.ai_generated ? 'AI Summary' : 'Summary'}
                      </span>
                    </div>
                    <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-line">{reportData.narrative}</p>
                  </div>
                  <div className="flex gap-4 text-xs text-gray-500">
                    <span>Expenses: <strong>{reportData.expense_count || 0}</strong></span>
                    <span>Meetings: <strong>{reportData.meeting_count || 0}</strong></span>
                    <span>Variance: <strong className={reportData.variance > 0 ? 'text-red-600' : 'text-emerald-600'}>
                      ₹{Math.abs(Math.round(reportData.variance || 0)).toLocaleString('en-IN')} {(reportData.variance || 0) > 0 ? 'over' : 'under'}
                    </strong></span>
                  </div>
                </div>
              ) : null}
            </div>
            <div className="flex justify-end border-t border-gray-100 px-6 py-4">
              <button onClick={() => { setReportModal(false); setReportData(null) }}
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Close</button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}

function Fld({ label, hint, error, children }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className={labelCls}>{label}</label>
        {hint && <span className="text-[10px] text-gray-400">{hint}</span>}
      </div>
      {children}
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  )
}

function RequestRow({ request: r, user, onStatus, onReport }) {
  const [busy, setBusy] = useState(false)
  const raw = r.raw_status || r.status || 'draft'
  const transition = NEXT_STATUS[raw]
  const isOwner = user && (user.id === r.user_id || user.role === 'admin' || user.role === 'manager')
  const st = STATUS_STYLE[raw] || STATUS_STYLE.draft

  const handleTransition = async () => {
    if (!transition || !isOwner) return
    setBusy(true)
    try { await onStatus(r.request_id || r.id, transition.next) }
    finally { setBusy(false) }
  }

  return (
    <div className="flex flex-col gap-2.5 px-5 py-4 transition-colors hover:bg-gray-50/50">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 border border-indigo-100">
          <Plane size={16} className="text-indigo-600" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-gray-900">{r.from_city || '—'} → {r.to_city || '—'}</p>
          <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-gray-500">
            <span>{r.travel_date || 'Date TBD'}</span>
            {r.return_date && <span>– {r.return_date}</span>}
            {r.purpose && <span className="capitalize">· {r.purpose.replace('_', ' ')}</span>}
            {r.request_id && <span className="text-[10px] text-gray-300 font-mono">{r.request_id}</span>}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {r.estimated_budget ? <span className="text-sm font-semibold text-gray-900">₹{Number(r.estimated_budget).toLocaleString('en-IN')}</span> : null}
          <span className={cn('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold capitalize', st.bg, st.text, st.border)}>
            <span className={cn('h-1.5 w-1.5 rounded-full', st.dot)} />
            {(raw || 'draft').replace('_', ' ')}
          </span>
        </div>
      </div>

      {isOwner && (transition || raw === 'completed') && (
        <div className="flex flex-wrap gap-2 pl-[52px]">
          {transition && (
            <button onClick={handleTransition} disabled={busy}
              className="flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50">
              {busy ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle size={11} />}
              {transition.label}
            </button>
          )}
          {raw === 'completed' && (
            <button onClick={() => onReport(r.request_id || r.id)}
              className="flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100">
              <BarChart2 size={11} /> View Report
            </button>
          )}
        </div>
      )}
    </div>
  )
}
