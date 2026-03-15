import { useState, useEffect } from 'react'
import { FileText, Plus, Clock, MapPin, Calendar, ChevronRight } from 'lucide-react'
import toast from 'react-hot-toast'
import { getRequests, createRequest } from '../api/requests'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import Select from '../components/ui/Select'
import Badge from '../components/ui/Badge'
import Modal from '../components/ui/Modal'
import StatCard from '../components/ui/StatCard'
import Spinner from '../components/ui/Spinner'

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
  const [requests,   setRequests]   = useState([])
  const [loading,    setLoading]    = useState(true)
  const [modal,      setModal]      = useState(false)
  const [form,       setForm]       = useState(emptyForm)
  const [submitting, setSubmitting] = useState(false)
  const [errors,     setErrors]     = useState({})

  useEffect(() => { fetchRequests() }, [])

  const fetchRequests = async () => {
    try {
      const data = await getRequests()
      setRequests(Array.isArray(data) ? data : data.requests || [])
    } catch { toast.error('Failed to load requests') }
    finally { setLoading(false) }
  }

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }))

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
              <RequestRow key={req.id} request={req} />
            ))}
          </div>
        )}
      </div>

      {/* ── New Request Modal ──────────────────── */}
      <Modal
        open={modal}
        onClose={() => { setModal(false); setForm(emptyForm); setErrors({}) }}
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
        </div>
      </Modal>
    </div>
  )
}

function RequestRow({ request: r }) {
  return (
    <div className="flex flex-col gap-3 px-4 py-4 transition-colors hover:bg-gray-50/50 sm:flex-row sm:items-center sm:gap-4 sm:px-6">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-accent-100 bg-accent-50">
          <FileText size={15} className="text-accent-600" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-gray-800">
            {r.from_city} → {r.to_city}
          </p>
          <div className="mt-0.5 flex flex-wrap items-center gap-2">
            <span className="text-xs text-gray-400">{r.travel_date}</span>
            {r.purpose && (
              <span className="text-xs text-gray-400 capitalize">· {r.purpose.replace('_', ' ')}</span>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center justify-between gap-3 sm:justify-end">
        {r.estimated_budget && (
          <span className="shrink-0 text-sm font-medium text-gray-700">
            ₹{Number(r.estimated_budget).toLocaleString('en-IN')}
          </span>
        )}
        <Badge status={r.status || 'pending'} dot>{r.status || 'Pending'}</Badge>
      </div>
    </div>
  )
}
