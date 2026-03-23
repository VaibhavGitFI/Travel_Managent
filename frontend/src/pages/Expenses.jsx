import { useState, useEffect, useRef, useMemo } from 'react'
import ReactDOM from 'react-dom'
import {
  Receipt, Upload, IndianRupee, CheckCircle,
  FileText, Camera, Clock3, Wallet, Mail, Images, Hand, Printer, Search,
  ShieldAlert, AlertTriangle, Info, Copy, Zap, Calendar, Brain, MessageSquare,
  Phone, TrendingUp, TrendingDown, ArrowUpRight, PieChart, BarChart3,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { getExpenses, submitExpense, uploadAndExtract, getExpenseAnomalies } from '../api/expenses'
import useStore from '../store/useStore'
import useAutoRefresh from '../hooks/useAutoRefresh'
import Badge from '../components/ui/Badge'
import StatCard from '../components/ui/StatCard'
import Spinner from '../components/ui/Spinner'
import { SkeletonRow, SkeletonTable } from '../components/ui/Skeleton'
import Pagination from '../components/ui/Pagination'
import usePagination from '../hooks/usePagination'
import { cn } from '../lib/cn'

const CATEGORIES = [
  { value: 'flight',        label: 'Flight',          color: 'bg-blue-50 text-blue-600 border-blue-100' },
  { value: 'hotel',         label: 'Hotel',           color: 'bg-violet-50 text-violet-600 border-violet-100' },
  { value: 'food',          label: 'Food & Meals',    color: 'bg-amber-50 text-amber-600 border-amber-100' },
  { value: 'transport',     label: 'Local Transport', color: 'bg-emerald-50 text-emerald-600 border-emerald-100' },
  { value: 'visa',          label: 'Visa / Docs',     color: 'bg-red-50 text-red-600 border-red-100' },
  { value: 'communication', label: 'Communication',   color: 'bg-sky-50 text-sky-600 border-sky-100' },
  { value: 'other',         label: 'Other',           color: 'bg-gray-50 text-gray-600 border-gray-100' },
]
const CAT_MAP = Object.fromEntries(CATEGORIES.map(c => [c.value, c]))
const EMPTY_FORM = { amount: '', category: '', description: '', expense_date: '', vendor: '', trip_id: '', gst_amount: '' }
const SORT_OPTIONS = [
  { value: 'latest', label: 'Latest' },   { value: 'oldest', label: 'Oldest' },
  { value: 'highest', label: 'High → Low' }, { value: 'lowest', label: 'Low → High' },
]
const PENDING = new Set(['pending', 'submitted', 'in-progress', 'review'])
const fmt = (v) => `₹${Number(v || 0).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
const fmtDate = (v) => { if (!v) return '—'; const d = new Date(v); return Number.isNaN(d.getTime()) ? v : d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) }
const title = (v = '') => String(v).replace(/[-_]/g, ' ').replace(/\b\w/g, l => l.toUpperCase())

const inputBase = 'w-full rounded-lg border border-gray-200 bg-white px-3.5 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 transition-all hover:border-gray-300 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/15'
const inputIcon = 'pl-10'
const labelCls = 'mb-1 block text-[11px] font-semibold uppercase tracking-wide text-gray-500'

export default function Expenses() {
  const {
    items: paginatedExpenses, page, totalPages, total,
    search, loading, goToPage, setSearch, refresh,
  } = usePagination(getExpenses)
  const [expenses, setExpenses] = useState([])
  const [modal, setModal] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrData, setOcrData] = useState(null)
  const [errors, setErrors] = useState({})
  const [sortBy, setSortBy] = useState('latest')
  const [anomalies, setAnomalies] = useState([])
  const [anomalyLoading, setAnomalyLoading] = useState(false)
  const [showAnomalies, setShowAnomalies] = useState(false)
  const fileRef = useRef(null)
  const user = useStore((s) => s.auth.user)

  useEffect(() => { setExpenses(paginatedExpenses) }, [paginatedExpenses])
  useAutoRefresh('expenses', refresh)

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }))

  const norm = useMemo(() => expenses.map(e => ({
    ...e,
    status: String(e.status || 'pending').toLowerCase().replace(/_/g, '-'),
    category: String(e.category || 'other').toLowerCase(),
    dateValue: e.expense_date || e.date || '',
    amount: Number(e.amount || 0),
  })), [expenses])

  const summary = useMemo(() => {
    const tot = norm.reduce((s, i) => s + i.amount, 0)
    const app = norm.filter(i => i.status === 'approved').reduce((s, i) => s + i.amount, 0)
    const pen = norm.filter(i => PENDING.has(i.status)).reduce((s, i) => s + i.amount, 0)
    return {
      total: tot, approved: app, pending: pen, other: Math.max(tot - app - pen, 0),
      approvedCount: norm.filter(i => i.status === 'approved').length,
      pendingCount: norm.filter(i => PENDING.has(i.status)).length,
      avg: norm.length ? tot / norm.length : 0,
    }
  }, [norm])

  const catBreakdown = useMemo(() => {
    const m = {}
    norm.forEach(e => { if (!m[e.category]) m[e.category] = { amount: 0, count: 0 }; m[e.category].amount += e.amount; m[e.category].count++ })
    return Object.entries(m).map(([k, v]) => ({ key: k, ...v, label: CAT_MAP[k]?.label || title(k) })).sort((a, b) => b.amount - a.amount)
  }, [norm])

  const sorted = useMemo(() => [...norm].sort((a, b) => {
    if (sortBy === 'highest') return b.amount - a.amount
    if (sortBy === 'lowest') return a.amount - b.amount
    if (sortBy === 'oldest') return (new Date(a.dateValue) || 0) - (new Date(b.dateValue) || 0)
    return (new Date(b.dateValue) || 0) - (new Date(a.dateValue) || 0)
  }), [norm, sortBy])

  const runScan = async () => {
    setAnomalyLoading(true)
    try { const d = await getExpenseAnomalies(); setAnomalies(d.anomalies || []); setShowAnomalies(true); if (!(d.anomalies || []).length) toast.success('No anomalies detected!') }
    catch { toast.error('Anomaly scan failed') }
    finally { setAnomalyLoading(false) }
  }

  const handleOcr = async (e) => {
    const file = e.target.files?.[0]; if (!file) return
    setOcrLoading(true); setOcrData(null)
    try {
      const fd = new FormData(); fd.append('receipt', file)
      const data = await uploadAndExtract(fd); setOcrData(data)
      if (data.amount) set('amount', String(data.amount))
      if (data.vendor) set('vendor', data.vendor)
      if (data.date) set('expense_date', data.date)
      if (data.gst) set('gst_amount', String(data.gst))
      toast.success('Receipt scanned!')
    } catch (err) { toast.error(err?.response?.data?.error || 'OCR failed') }
    finally { setOcrLoading(false); if (fileRef.current) fileRef.current.value = '' }
  }

  const handleSubmit = async () => {
    const e = {}
    if (!form.amount || isNaN(form.amount)) e.amount = 'Required'
    if (!form.category) e.category = 'Required'
    if (!form.description.trim()) e.description = 'Required'
    if (!form.expense_date) e.expense_date = 'Required'
    if (Object.keys(e).length) { setErrors(e); return }
    setErrors({}); setSubmitting(true)
    try {
      await submitExpense({ ...form, amount: parseFloat(form.amount), gst_amount: form.gst_amount ? parseFloat(form.gst_amount) : undefined })
      toast.success('Expense submitted!'); setModal(false); setForm(EMPTY_FORM); setOcrData(null); refresh()
    } catch (err) { toast.error(err?.response?.data?.error || 'Submission failed') }
    finally { setSubmitting(false) }
  }

  const exportCsv = () => {
    const esc = v => `"${String(v ?? '').replace(/"/g, '""')}"`
    const rows = [['Date','Category','Description','Vendor','Amount','Status'], ...sorted.map(e => [fmtDate(e.dateValue), CAT_MAP[e.category]?.label || title(e.category), e.description || '', e.vendor || '', String(e.amount), title(e.status)])]
    const blob = new Blob([rows.map(r => r.map(esc).join(',')).join('\n')], { type: 'text/csv' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'expenses.csv'; a.click()
  }

  const maxCat = catBreakdown[0]?.amount || 1

  return (
    <div className="mx-auto w-full max-w-7xl space-y-5">
      {/* Header */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-500 to-teal-600">
            <Receipt size={14} className="text-white" />
          </div>
          <h1 className="font-heading text-xl font-bold text-gray-900">Expense Tracker</h1>
          <span className="rounded-full bg-emerald-50 border border-emerald-200 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-600">
            AI OCR
          </span>
        </div>
        <p className="text-sm text-gray-500">Track, scan, and manage your travel expenses with AI-powered receipt scanning.</p>
      </div>

      {/* ── Top Stats ─────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        <StatCard icon={<Wallet size={20} />} value={fmt(summary.total)} label="Total Spend" accentColor="blue" className="rounded-xl border border-gray-200 bg-white shadow-card" />
        <StatCard icon={<CheckCircle size={20} />} value={fmt(summary.approved)} label="Approved" accentColor="green" className="rounded-xl border border-gray-200 bg-white shadow-card" />
        <StatCard icon={<Clock3 size={20} />} value={fmt(summary.pending)} label="Pending" accentColor="orange" className="rounded-xl border border-gray-200 bg-white shadow-card" />
        <StatCard icon={<TrendingUp size={20} />} value={fmt(summary.avg)} label="Average" accentColor="sky" className="rounded-xl border border-gray-200 bg-white shadow-card" />
      </div>

      {/* ── Donut + Category Breakdown + Actions ──────── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Donut */}
        <div className="rounded-xl border border-gray-200 bg-white shadow-card p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Expense Distribution</h3>
          <ExpenseDonut total={summary.total} approved={summary.approved} pending={summary.pending} other={summary.other} />
          <div className="mt-4 flex justify-center gap-5">
            <Legend color="#10b981" label="Approved" />
            <Legend color="#f59e0b" label="Pending" />
            <Legend color="#94a3b8" label="Other" />
          </div>
        </div>

        {/* Category Breakdown */}
        <div className="rounded-xl border border-gray-200 bg-white shadow-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-900">Category Breakdown</h3>
            <BarChart3 size={14} className="text-gray-400" />
          </div>
          {catBreakdown.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-6">No expenses yet</p>
          ) : (
            <div className="space-y-3">
              {catBreakdown.slice(0, 5).map(c => {
                const cat = CAT_MAP[c.key]
                const pct = Math.round((c.amount / maxCat) * 100)
                return (
                  <div key={c.key}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium text-gray-700">{c.label}</span>
                      <span className="text-xs font-bold text-gray-900">{fmt(c.amount)}</span>
                    </div>
                    <div className="h-2 rounded-full bg-gray-100">
                      <div className={cn('h-full rounded-full transition-all', cat?.color?.split(' ')[0] || 'bg-gray-300')}
                        style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Quick Actions + Anomaly Scanner */}
        <div className="space-y-4">
          <div className="rounded-xl border border-gray-200 bg-white shadow-card p-5">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Add Expense</h3>
            <div className="grid grid-cols-3 gap-2">
              {[
                { icon: Camera, label: 'Scan Receipt', desc: 'AI OCR' },
                { icon: Mail, label: 'From Email', desc: 'Extract' },
                { icon: Hand, label: 'Manual', desc: 'Type it' },
              ].map(a => (
                <button key={a.label} onClick={() => setModal(true)}
                  className="group flex flex-col items-center gap-1.5 rounded-xl border border-gray-100 bg-gray-50 p-3 transition-all hover:border-emerald-200 hover:bg-emerald-50">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white border border-gray-200 group-hover:border-emerald-200 transition-colors">
                    <a.icon size={16} className="text-gray-500 group-hover:text-emerald-600" />
                  </div>
                  <span className="text-[11px] font-semibold text-gray-700">{a.label}</span>
                  <span className="text-[9px] text-gray-400">{a.desc}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Anomaly Scanner */}
          <div className="rounded-xl border border-gray-200 bg-white shadow-card p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Brain size={14} className="text-amber-500" />
                <h3 className="text-sm font-semibold text-gray-900">AI Anomaly Scanner</h3>
              </div>
              <button onClick={runScan} disabled={anomalyLoading}
                className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-amber-500 to-orange-500 px-3 py-1.5 text-xs font-semibold text-white transition-all hover:shadow-md disabled:opacity-50">
                {anomalyLoading ? <Spinner size="xs" color="white" /> : <Zap size={11} />} Scan
              </button>
            </div>
            {showAnomalies && anomalies.length > 0 ? (
              <div className="space-y-2 max-h-36 overflow-y-auto">
                {anomalies.slice(0, 6).map((a, i) => <AnomalyRow key={i} anomaly={a} />)}
              </div>
            ) : showAnomalies ? (
              <p className="text-sm text-emerald-600 text-center py-2">All clear — no anomalies found</p>
            ) : (
              <p className="text-xs text-gray-400">Detect duplicates, outliers, and suspicious patterns.</p>
            )}
          </div>
        </div>
      </div>

      {/* ── Expense List ──────────────────────────────── */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-card overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-gray-100 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-sm font-semibold text-gray-900">All Expenses</h3>
            <p className="mt-0.5 text-xs text-gray-400">{sorted.length} entries</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 sm:flex-initial sm:w-44">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input type="text" placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-white py-2 pl-9 pr-3 text-xs text-gray-700 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/15 focus:border-blue-500" />
            </div>
            <button onClick={exportCsv} title="Export CSV"
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-500 hover:bg-gray-50"><FileText size={14} /></button>
            <button onClick={() => window.print()} title="Print"
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-500 hover:bg-gray-50"><Printer size={14} /></button>
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}
              className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500/15 appearance-none">
              {SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>

        {loading ? (
          <div className="divide-y divide-gray-100">
            {Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}
          </div>
        ) : norm.length === 0 ? (
          <div className="py-16 text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-gray-100 to-gray-200">
              <Receipt size={24} className="text-gray-400" />
            </div>
            <p className="font-semibold text-gray-700">No expenses found</p>
            <p className="mt-1 text-sm text-gray-500">Submit your first expense to start tracking</p>
            <button onClick={() => setModal(true)}
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-emerald-600 to-teal-500 px-4 py-2 text-sm font-semibold text-white">
              <Receipt size={14} /> Add Expense
            </button>
          </div>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full">
                <thead className="bg-gray-50">
                  <tr>
                    {['Description', 'Category', 'Date', 'Amount', 'Status'].map(h => (
                      <th key={h} className="px-5 py-3 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {sorted.map(e => {
                    const cat = CAT_MAP[e.category]
                    return (
                      <tr key={e.id} className="transition-colors hover:bg-gray-50/50">
                        <td className="px-5 py-3.5">
                          <div className="flex items-center gap-3">
                            <div className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border', cat?.color || 'bg-gray-50 text-gray-600 border-gray-100')}>
                              <Receipt size={13} />
                            </div>
                            <div className="min-w-0">
                              <p className="text-sm font-medium text-gray-900 truncate max-w-[200px]">{e.vendor || e.description || 'Expense'}</p>
                              {e.vendor && e.description && <p className="text-[11px] text-gray-400 truncate max-w-[200px]">{e.description}</p>}
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-3.5">
                          <span className={cn('inline-flex rounded-md border px-2 py-0.5 text-[10px] font-semibold', cat?.color || 'bg-gray-50 text-gray-600 border-gray-100')}>
                            {cat?.label || title(e.category)}
                          </span>
                        </td>
                        <td className="px-5 py-3.5 text-sm text-gray-500">{fmtDate(e.dateValue)}</td>
                        <td className="px-5 py-3.5 text-sm font-bold text-gray-900">{fmt(e.amount)}</td>
                        <td className="px-5 py-3.5"><Badge status={e.status} dot>{title(e.status)}</Badge></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {/* Mobile */}
            <div className="divide-y divide-gray-100 md:hidden">
              {sorted.map(e => <MobileRow key={e.id} expense={e} />)}
            </div>
          </>
        )}
        <Pagination page={page} totalPages={totalPages} total={total} onPageChange={goToPage} className="border-t border-gray-100" />
      </div>

      {/* ── Submit Modal ──────────────────────────────── */}
      {modal && ReactDOM.createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center overflow-y-auto p-4"
          onClick={(e) => { if (e.target === e.currentTarget) { setModal(false); setErrors({}); setOcrData(null) } }}
          style={{ background: 'rgba(15,23,42,0.6)', backdropFilter: 'blur(6px)', WebkitBackdropFilter: 'blur(6px)' }}>
          <div className="relative w-full max-w-lg rounded-2xl bg-white shadow-2xl">
            <div className="border-b border-gray-100 px-6 py-4">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-500 to-teal-600">
                  <Receipt size={14} className="text-white" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-gray-900">Submit Expense</h3>
                  <p className="text-xs text-gray-500">Scan receipt or enter details manually</p>
                </div>
              </div>
            </div>
            <div className="px-6 py-5 space-y-4">
              {/* OCR Upload */}
              <div className="cursor-pointer rounded-xl border-2 border-dashed border-gray-200 bg-gray-50 p-4 text-center transition-all hover:border-emerald-300 hover:bg-emerald-50/30"
                onClick={() => fileRef.current?.click()}>
                <input ref={fileRef} type="file" accept="image/*,.pdf" className="hidden" onChange={handleOcr} />
                {ocrLoading ? (
                  <div className="flex items-center justify-center gap-2">
                    <Spinner size="sm" /> <span className="text-sm text-gray-500">Scanning receipt...</span>
                  </div>
                ) : (
                  <>
                    <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 border border-emerald-100">
                      <Camera size={18} className="text-emerald-600" />
                    </div>
                    <p className="text-sm font-medium text-gray-700">Upload receipt for AI scan</p>
                    <p className="mt-0.5 text-[11px] text-gray-400">Image or PDF — amount, vendor, date auto-extracted</p>
                  </>
                )}
              </div>

              {ocrData && (
                <div className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
                  <CheckCircle size={14} className="mt-0.5 shrink-0" />
                  <span>Receipt scanned — fields auto-filled. Please review.</span>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <Fld label="Amount (₹)" error={errors.amount}>
                  <div className="relative">
                    <IndianRupee size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input type="number" step="0.01" placeholder="0.00" className={cn(inputBase, inputIcon)}
                      value={form.amount} onChange={(e) => set('amount', e.target.value)} />
                  </div>
                </Fld>
                <Fld label="Category" error={errors.category}>
                  <select className={cn(inputBase, 'appearance-none')} value={form.category} onChange={(e) => set('category', e.target.value)}>
                    <option value="">Select</option>
                    {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                  </select>
                </Fld>
              </div>
              <Fld label="Description" error={errors.description}>
                <input className={inputBase} placeholder="Brief description" value={form.description} onChange={(e) => set('description', e.target.value)} />
              </Fld>
              <div className="grid grid-cols-2 gap-3">
                <Fld label="Vendor">
                  <input className={inputBase} placeholder="e.g. MakeMyTrip" value={form.vendor} onChange={(e) => set('vendor', e.target.value)} />
                </Fld>
                <Fld label="Date" error={errors.expense_date}>
                  <input type="date" className={inputBase} value={form.expense_date} onChange={(e) => set('expense_date', e.target.value)} />
                </Fld>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Fld label="GST (₹)" hint="Optional">
                  <input type="number" step="0.01" placeholder="0.00" className={inputBase}
                    value={form.gst_amount} onChange={(e) => set('gst_amount', e.target.value)} />
                </Fld>
                <Fld label="Trip ID" hint="Optional">
                  <input className={inputBase} placeholder="Link to trip" value={form.trip_id} onChange={(e) => set('trip_id', e.target.value)} />
                </Fld>
              </div>
            </div>
            <div className="flex justify-end gap-2 border-t border-gray-100 px-6 py-4">
              <button onClick={() => { setModal(false); setErrors({}); setOcrData(null) }}
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Cancel</button>
              <button onClick={handleSubmit} disabled={submitting}
                className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-emerald-600 to-teal-500 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
                {submitting ? <Spinner size="xs" color="white" /> : <FileText size={14} />}
                Submit Expense
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}

/* ── Subcomponents ───────────────────────────────────── */

function StatBox({ label, value, icon: Icon, color, iconColor, sub }) {
  return (
    <div className={cn('rounded-xl border p-4', color)}>
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} className={iconColor} />
        <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">{label}</span>
      </div>
      <p className="text-lg font-bold text-gray-900">{value}</p>
      {sub && <p className="text-[10px] text-gray-400 mt-0.5">{sub}</p>}
    </div>
  )
}

function ExpenseDonut({ total, approved, pending, other }) {
  const size = 180, sw = 16, r = (size - sw) / 2, c = 2 * Math.PI * r, safe = total > 0 ? total : 1
  const segs = [
    { color: '#10b981', len: (Math.max(approved, 0) / safe) * c },
    { color: '#f59e0b', len: (Math.max(pending, 0) / safe) * c },
    { color: '#94a3b8', len: (Math.max(other, 0) / safe) * c },
  ].filter(s => s.len > 0.5)
  let off = 0
  return (
    <div className="relative mx-auto" style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} className="h-full w-full -rotate-90">
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#f1f5f9" strokeWidth={sw} />
        {segs.map((s, i) => { const start = off; off += s.len; return (
          <circle key={i} cx={size/2} cy={size/2} r={r} fill="none" stroke={s.color} strokeWidth={sw}
            strokeLinecap="round" strokeDasharray={`${s.len} ${c - s.len}`} strokeDashoffset={-start} />
        )})}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <p className="text-xs text-gray-400">Total</p>
        <p className="text-2xl font-bold text-gray-900">{fmt(total)}</p>
      </div>
    </div>
  )
}

function Legend({ color, label }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
      <span className="text-[11px] text-gray-500">{label}</span>
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

function AnomalyRow({ anomaly: a }) {
  const icons = { duplicate: Copy, weekend: Calendar, outlier: AlertTriangle, round_amount: IndianRupee, rapid_fire: Zap }
  const colors = { warning: 'border-amber-200 bg-amber-50 text-amber-700', info: 'border-blue-200 bg-blue-50 text-blue-700' }
  const Icon = icons[a.type] || Info
  return (
    <div className={cn('flex items-start gap-2 rounded-lg border px-3 py-2 text-xs', colors[a.severity] || colors.info)}>
      <Icon size={12} className="mt-0.5 shrink-0" />
      <div className="min-w-0">
        <p className="font-semibold">{a.title}</p>
        <p className="opacity-80 mt-0.5">{a.message}</p>
      </div>
    </div>
  )
}

function MobileRow({ expense: e }) {
  const cat = CAT_MAP[e.category]
  return (
    <div className="px-4 py-3.5 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900 truncate">{e.description || 'Expense'}</p>
          <p className="text-[11px] text-gray-400">{fmtDate(e.dateValue)} {e.vendor && `• ${e.vendor}`}</p>
        </div>
        <p className="shrink-0 text-sm font-bold text-gray-900">{fmt(e.amount)}</p>
      </div>
      <div className="flex items-center gap-2">
        <span className={cn('inline-flex rounded-md border px-2 py-0.5 text-[10px] font-semibold', cat?.color || 'bg-gray-50 text-gray-600 border-gray-100')}>
          {cat?.label || title(e.category)}
        </span>
        <Badge status={e.status} dot>{title(e.status)}</Badge>
        {Number(e.ocr_confidence) > 0 && (
          <span className="ml-auto flex items-center gap-1 text-[10px] text-emerald-600 font-medium">
            <Camera size={10} /> {Math.round(Number(e.ocr_confidence) * 100)}%
          </span>
        )}
      </div>
    </div>
  )
}
