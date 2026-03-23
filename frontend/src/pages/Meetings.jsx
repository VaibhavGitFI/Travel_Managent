import { useState } from 'react'
import ReactDOM from 'react-dom'
import {
  Users, Plus, MapPin, Calendar, Clock, Edit2, Trash2,
  Sparkles, Building2, Phone, Mail, Linkedin, MessageSquare, FileText, CheckCircle, Search,
  Navigation, Coffee, Briefcase, Star, Brain, ChevronRight,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { getMeetings, createMeeting, updateMeeting, deleteMeeting, suggestSchedule, parseMeetingText, getNearbyVenues } from '../api/meetings'
import { cn } from '../lib/cn'
import useAutoRefresh from '../hooks/useAutoRefresh'
import usePagination from '../hooks/usePagination'
import Pagination from '../components/ui/Pagination'
import Badge from '../components/ui/Badge'
import Spinner from '../components/ui/Spinner'
import { SkeletonCard } from '../components/ui/Skeleton'

const SOURCE_TYPES = [
  { value: 'manual',   label: 'Manual Entry' },
  { value: 'email',    label: 'Email' },
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'phone',    label: 'Phone' },
  { value: 'calendar', label: 'Calendar Invite' },
  { value: 'linkedin', label: 'LinkedIn' },
]

const SOURCE_ICONS = {
  manual: Building2, email: Mail, whatsapp: MessageSquare,
  phone: Phone, calendar: Calendar, linkedin: Linkedin,
}

const EMPTY_FORM = {
  client_name: '', company: '', location: '', meeting_date: '',
  meeting_time: '', duration_minutes: '60', agenda: '',
  source_type: 'manual', contact_info: '',
}

const inputBase = 'w-full rounded-lg border border-gray-200 bg-white px-3.5 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 transition-all hover:border-gray-300 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/15'
const inputWithIcon = 'pl-10'
const labelClass = 'mb-1 block text-[11px] font-semibold uppercase tracking-wide text-gray-500'

export default function Meetings() {
  const {
    items: meetings, page, totalPages, total,
    search, loading, goToPage, setSearch, refresh,
  } = usePagination(getMeetings)

  const [modal, setModal] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [errors, setErrors] = useState({})
  const [aiModal, setAiModal] = useState(false)
  const [aiResult, setAiResult] = useState(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [venueModal, setVenueModal] = useState(false)
  const [venueLocation, setVenueLocation] = useState('')
  const [venueLoading, setVenueLoading] = useState(false)
  const [venueData, setVenueData] = useState(null)
  const [parseModal, setParseModal] = useState(false)
  const [parseText, setParseText] = useState('')
  const [parseSource, setParseSource] = useState('email')
  const [parseLoading, setParseLoading] = useState(false)
  const [parsedData, setParsedData] = useState(null)

  useAutoRefresh('meetings', refresh)

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }))

  const openNew = () => { setEditing(null); setForm(EMPTY_FORM); setErrors({}); setModal(true) }

  const openEdit = (m) => {
    setEditing(m)
    setForm({
      client_name: m.client_name || '', company: m.company || '', location: m.location || '',
      meeting_date: m.meeting_date || '', meeting_time: m.meeting_time || '',
      duration_minutes: String(m.duration_minutes || 60), agenda: m.agenda || '',
      source_type: m.source_type || 'manual', contact_info: m.contact_info || '',
    })
    setErrors({}); setModal(true)
  }

  const handleSubmit = async () => {
    const e = {}
    if (!form.client_name.trim()) e.client_name = 'Required'
    if (!form.meeting_date) e.meeting_date = 'Required'
    if (Object.keys(e).length) { setErrors(e); return }
    setErrors({}); setSubmitting(true)
    try {
      if (editing) { await updateMeeting(editing.id, form); toast.success('Meeting updated') }
      else { await createMeeting(form); toast.success('Meeting created') }
      setModal(false); refresh()
    } catch (err) { toast.error(err.response?.data?.error || 'Failed to save') }
    finally { setSubmitting(false) }
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this meeting?')) return
    try { await deleteMeeting(id); toast.success('Deleted'); refresh() }
    catch { toast.error('Delete failed') }
  }

  const handleAiSchedule = async () => {
    setAiLoading(true)
    try { const d = await suggestSchedule({ meetings: meetings.slice(0, 10) }); setAiResult(d); setAiModal(true) }
    catch { toast.error('AI scheduling failed') }
    finally { setAiLoading(false) }
  }

  const handleVenueSearch = async () => {
    if (!venueLocation.trim()) { toast.error('Enter a location'); return }
    setVenueLoading(true); setVenueData(null)
    try { setVenueData(await getNearbyVenues({ location: venueLocation })) }
    catch { toast.error('Venue search failed') }
    finally { setVenueLoading(false) }
  }

  const handleParse = async () => {
    if (!parseText.trim()) { toast.error('Paste some text first'); return }
    setParseLoading(true)
    try {
      const r = await parseMeetingText(parseText, parseSource)
      if (r.success) { setParsedData(r); toast.success('Details extracted!') }
      else toast.error(r.error || 'Could not extract details')
    } catch (err) { toast.error(err.response?.data?.error || 'Parse failed') }
    finally { setParseLoading(false) }
  }

  const useExtractedData = () => {
    if (!parsedData?.extracted) return
    const ex = parsedData.extracted
    setForm({
      client_name: ex.client_name || '', company: ex.company || '', location: ex.location || '',
      meeting_date: ex.meeting_date || '', meeting_time: ex.meeting_time || '',
      duration_minutes: String(ex.duration_minutes || ex.duration || 60),
      agenda: ex.agenda || '', source_type: parsedData.source_type || parseSource || 'email',
      contact_info: ex.contact_info || '',
    })
    setEditing(null); setErrors({}); setParseModal(false); setModal(true)
  }

  return (
    <div className="mx-auto w-full max-w-7xl space-y-5">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600">
              <Users size={14} className="text-white" />
            </div>
            <h1 className="font-heading text-xl font-bold text-gray-900">Client Meetings</h1>
            <span className="rounded-full bg-blue-50 border border-blue-200 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-blue-600">
              AI Scheduling
            </span>
          </div>
          <p className="mt-1 text-sm text-gray-500">Manage, schedule, and optimize your client meetings</p>
        </div>
        <button onClick={openNew}
          className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-500 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:shadow-md hover:brightness-105 sm:w-auto w-full">
          <Plus size={15} /> Add Meeting
        </button>
      </div>

      {/* Action bar */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input type="text" placeholder="Search client, company..." value={search} onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-gray-200 bg-white py-2.5 pl-10 pr-3 text-sm text-gray-700 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500/15 focus:border-blue-500 transition-all" />
        </div>
        <div className="flex gap-2">
          {[
            { label: 'Parse Email/WA', icon: FileText, onClick: () => { setParseText(''); setParsedData(null); setParseSource('email'); setParseModal(true) } },
            { label: 'Find Venues', icon: Navigation, onClick: () => { setVenueData(null); setVenueModal(true) } },
            { label: 'AI Schedule', icon: Brain, onClick: handleAiSchedule, loading: aiLoading },
          ].map((a) => (
            <button key={a.label} onClick={a.onClick} disabled={a.loading}
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 hover:border-gray-300 disabled:opacity-50">
              {a.loading ? <Spinner size="xs" /> : <a.icon size={13} />}
              <span className="hidden sm:inline">{a.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Meeting grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : meetings.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50/50 py-16 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-gray-100 to-gray-200">
            <Users size={24} className="text-gray-400" />
          </div>
          <p className="font-semibold text-gray-700">No meetings scheduled</p>
          <p className="mt-1 text-sm text-gray-500">Schedule your first client meeting</p>
          <button onClick={openNew}
            className="mt-4 inline-flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50">
            <Plus size={14} /> Add Meeting
          </button>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {meetings.map((m) => (
              <MeetingCard key={m.id} meeting={m} onEdit={() => openEdit(m)} onDelete={() => handleDelete(m.id)} />
            ))}
          </div>
          <Pagination page={page} totalPages={totalPages} total={total} onPageChange={goToPage} />
        </>
      )}

      {/* ── Create/Edit Modal ──────────────────────── */}
      {modal && (
        <Overlay onClose={() => { setModal(false); setErrors({}) }}>
          <div className="rounded-2xl bg-white shadow-2xl">
            <div className="border-b border-gray-100 px-6 py-4">
              <h3 className="text-base font-semibold text-gray-900">{editing ? 'Edit Meeting' : 'Schedule Meeting'}</h3>
              <p className="text-xs text-gray-500 mt-0.5">Fill in the details below</p>
            </div>
            <div className="space-y-3 px-6 py-5">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Client Name" error={errors.client_name}>
                  <input className={inputBase} placeholder="e.g. Rajesh Kumar"
                    value={form.client_name} onChange={(e) => set('client_name', e.target.value)} />
                </Field>
                <Field label="Company">
                  <input className={inputBase} placeholder="e.g. Acme Corp"
                    value={form.company} onChange={(e) => set('company', e.target.value)} />
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Date" error={errors.meeting_date}>
                  <input type="date" className={inputBase} value={form.meeting_date} onChange={(e) => set('meeting_date', e.target.value)} />
                </Field>
                <Field label="Time">
                  <input type="time" className={inputBase} value={form.meeting_time} onChange={(e) => set('meeting_time', e.target.value)} />
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Location">
                  <div className="relative">
                    <MapPin size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input className={cn(inputBase, inputWithIcon)} placeholder="Office / Cafe / Virtual"
                      value={form.location} onChange={(e) => set('location', e.target.value)} />
                  </div>
                </Field>
                <Field label="Duration (min)">
                  <input type="number" min="15" max="480" step="15" className={inputBase}
                    value={form.duration_minutes} onChange={(e) => set('duration_minutes', e.target.value)} />
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Source">
                  <select className={cn(inputBase, 'appearance-none')} value={form.source_type} onChange={(e) => set('source_type', e.target.value)}>
                    {SOURCE_TYPES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                </Field>
                <Field label="Contact">
                  <input className={inputBase} placeholder="Phone / email" value={form.contact_info} onChange={(e) => set('contact_info', e.target.value)} />
                </Field>
              </div>
              <Field label="Agenda">
                <textarea rows={2} className={cn(inputBase, 'resize-none')} placeholder="Meeting agenda or notes..."
                  value={form.agenda} onChange={(e) => set('agenda', e.target.value)} />
              </Field>
            </div>
            <div className="flex justify-end gap-2 border-t border-gray-100 px-6 py-4">
              <button onClick={() => setModal(false)} className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Cancel</button>
              <button onClick={handleSubmit} disabled={submitting}
                className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-500 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
                {submitting ? <Spinner size="xs" color="white" /> : null}
                {editing ? 'Save Changes' : 'Create Meeting'}
              </button>
            </div>
          </div>
        </Overlay>
      )}

      {/* ── AI Schedule Modal ──────────────────────── */}
      {aiModal && (
        <Overlay onClose={() => setAiModal(false)}>
          <div className="rounded-2xl bg-white shadow-2xl">
            <div className="border-b border-gray-100 px-6 py-4">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-purple-600">
                  <Brain size={14} className="text-white" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-gray-900">AI Schedule Optimization</h3>
                  <p className="text-xs text-gray-500">Smart suggestions based on your meetings</p>
                </div>
              </div>
            </div>
            <div className="px-6 py-5">
              {aiResult ? (
                <div className="space-y-3">
                  {aiResult.suggestions?.map((s, i) => (
                    <div key={i} className="rounded-xl border border-blue-100 bg-blue-50/50 p-4">
                      <p className="text-sm font-medium text-gray-900">{s.suggestion || s}</p>
                      {s.reason && <p className="text-xs text-gray-500 mt-1">{s.reason}</p>}
                    </div>
                  ))}
                  {aiResult.message && <p className="text-sm text-gray-600 leading-relaxed">{aiResult.message}</p>}
                </div>
              ) : (
                <div className="flex items-center justify-center py-8"><Spinner size="md" /></div>
              )}
            </div>
            <div className="flex justify-end border-t border-gray-100 px-6 py-4">
              <button onClick={() => setAiModal(false)} className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Close</button>
            </div>
          </div>
        </Overlay>
      )}

      {/* ── Parse Email/WA Modal ───────────────────── */}
      {parseModal && (
        <Overlay onClose={() => { setParseModal(false); setParsedData(null) }}>
          <div className="rounded-2xl bg-white shadow-2xl">
            <div className="border-b border-gray-100 px-6 py-4">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-500 to-teal-600">
                  <Sparkles size={14} className="text-white" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-gray-900">AI Meeting Extractor</h3>
                  <p className="text-xs text-gray-500">Paste email or WhatsApp text to auto-extract details</p>
                </div>
              </div>
            </div>
            <div className="px-6 py-5">
              {!parsedData ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-2">
                    {['email', 'whatsapp'].map((s) => (
                      <button key={s} type="button" onClick={() => setParseSource(s)}
                        className={cn('rounded-lg border py-2.5 text-sm font-medium transition-colors',
                          parseSource === s ? 'border-blue-400 bg-blue-50 text-blue-700' : 'border-gray-200 bg-white text-gray-500 hover:bg-gray-50')}>
                        {s === 'whatsapp' ? 'WhatsApp' : 'Email'}
                      </button>
                    ))}
                  </div>
                  <div>
                    <label className={labelClass}>Paste {parseSource === 'whatsapp' ? 'WhatsApp message' : 'email body'}</label>
                    <textarea rows={6} className={cn(inputBase, 'resize-none')} value={parseText} onChange={(e) => setParseText(e.target.value)}
                      placeholder={parseSource === 'whatsapp'
                        ? 'e.g. "Hi, can we meet on 20 March at 3pm at BKC office? - Rajan, Acme Corp"'
                        : 'e.g. "Dear Mr. Sharma, Please confirm meeting on March 20th at 10:00 AM at Lower Parel..."'} />
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
                    <CheckCircle size={14} />
                    <span>Details extracted successfully
                      {parsedData.confidence === 'low' && ' (low confidence — please review)'}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(parsedData.extracted || {}).map(([key, value]) => (
                      <div key={key} className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 mb-0.5">{key.replace(/_/g, ' ')}</p>
                        <p className="text-sm text-gray-800 break-words">{String(value)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 border-t border-gray-100 px-6 py-4">
              {parsedData ? (
                <>
                  <button onClick={() => setParsedData(null)} className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Try Again</button>
                  <button onClick={useExtractedData}
                    className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-emerald-600 to-teal-500 px-4 py-2 text-sm font-semibold text-white">
                    <CheckCircle size={14} /> Use These Details
                  </button>
                </>
              ) : (
                <>
                  <button onClick={() => setParseModal(false)} className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Cancel</button>
                  <button onClick={handleParse} disabled={parseLoading}
                    className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-emerald-600 to-teal-500 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
                    {parseLoading ? <Spinner size="xs" color="white" /> : <Sparkles size={14} />}
                    Extract Details
                  </button>
                </>
              )}
            </div>
          </div>
        </Overlay>
      )}

      {/* ── Nearby Venues Modal ────────────────────── */}
      {venueModal && (
        <Overlay onClose={() => setVenueModal(false)}>
          <div className="rounded-2xl bg-white shadow-2xl">
            <div className="border-b border-gray-100 px-6 py-4">
              <h3 className="text-base font-semibold text-gray-900">Find Nearby Venues</h3>
              <p className="text-xs text-gray-500 mt-0.5">Hotels, coworking spaces, and cafes near your meeting</p>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <MapPin size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input className={cn(inputBase, inputWithIcon)} placeholder="Enter city or area (e.g. BKC Mumbai)"
                    value={venueLocation} onChange={(e) => setVenueLocation(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleVenueSearch()} />
                </div>
                <button onClick={handleVenueSearch} disabled={venueLoading}
                  className="flex items-center gap-1.5 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-60">
                  {venueLoading ? <Spinner size="xs" color="white" /> : <Search size={14} />}
                  Search
                </button>
              </div>

              {venueData?.venues && (
                <div className="space-y-4 max-h-[400px] overflow-y-auto">
                  {[
                    { key: 'hotels_conference', label: 'Hotels with Conference Rooms', icon: Briefcase, color: 'bg-blue-50 text-blue-600 border-blue-100' },
                    { key: 'coworking', label: 'Coworking Spaces', icon: Building2, color: 'bg-violet-50 text-violet-600 border-violet-100' },
                    { key: 'cafes', label: 'Cafes & Casual Spots', icon: Coffee, color: 'bg-amber-50 text-amber-600 border-amber-100' },
                  ].map(({ key, label, icon: Icon, color }) => {
                    const venues = venueData.venues[key] || []
                    if (!venues.length) return null
                    return (
                      <div key={key}>
                        <div className="flex items-center gap-2 mb-2">
                          <div className={cn('flex h-6 w-6 items-center justify-center rounded-md border', color)}>
                            <Icon size={12} />
                          </div>
                          <h4 className="text-xs font-semibold text-gray-700">{label}</h4>
                        </div>
                        <div className="space-y-1.5">
                          {venues.map((v, i) => (
                            <div key={i} className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50 px-3 py-2.5">
                              <div className="min-w-0 flex-1">
                                <p className="text-sm font-medium text-gray-800 truncate">{v.name}</p>
                                {v.vicinity && <p className="text-xs text-gray-400 truncate">{v.vicinity}</p>}
                              </div>
                              {v.rating && (
                                <div className="flex items-center gap-1 shrink-0 ml-2">
                                  <Star size={11} className="text-amber-400 fill-amber-400" />
                                  <span className="text-xs font-medium text-gray-600">{v.rating}</span>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
            <div className="flex justify-end border-t border-gray-100 px-6 py-4">
              <button onClick={() => setVenueModal(false)} className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Close</button>
            </div>
          </div>
        </Overlay>
      )}
    </div>
  )
}

// ── Overlay (Modal backdrop) ────────────────────────────────
function Overlay({ onClose, children }) {
  return ReactDOM.createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center overflow-y-auto p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.() }}
      style={{ background: 'rgba(15,23,42,0.6)', backdropFilter: 'blur(6px)', WebkitBackdropFilter: 'blur(6px)' }}>
      <div className="relative w-full max-w-lg">{children}</div>
    </div>,
    document.body
  )
}

// ── Field wrapper ───────────────────────────────────────────
function Field({ label, error, children }) {
  return (
    <div>
      <label className={labelClass}>{label}</label>
      {children}
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  )
}

// ── Meeting Card ────────────────────────────────────────────
function MeetingCard({ meeting: m, onEdit, onDelete }) {
  const SourceIcon = SOURCE_ICONS[m.source_type] || Building2
  const mins = m.duration_minutes || 60
  const hours = Math.floor(mins / 60)
  const rem = mins % 60
  const dur = hours ? `${hours}h${rem ? ` ${rem}m` : ''}` : `${mins}m`

  return (
    <div className="group rounded-xl border border-gray-200 bg-white p-5 shadow-card transition-all hover:border-gray-300 hover:shadow-md">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-50 border border-blue-100 text-blue-600">
            <SourceIcon size={16} />
          </div>
          <div>
            <p className="font-semibold text-gray-900 leading-tight">{m.client_name}</p>
            {m.company && <p className="text-xs text-gray-500 mt-0.5">{m.company}</p>}
          </div>
        </div>
        <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={onEdit} className="p-1.5 rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors">
            <Edit2 size={13} />
          </button>
          <button onClick={onDelete} className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors">
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {/* Details */}
      <div className="space-y-2">
        {m.meeting_date && (
          <div className="flex items-center gap-2 text-xs text-gray-600">
            <Calendar size={12} className="text-gray-400" />
            {m.meeting_date}{m.meeting_time && ` at ${m.meeting_time}`}
          </div>
        )}
        {m.location && (
          <div className="flex items-center gap-2 text-xs text-gray-600">
            <MapPin size={12} className="text-gray-400" />
            {m.location}
          </div>
        )}
        <div className="flex items-center gap-2 text-xs text-gray-600">
          <Clock size={12} className="text-gray-400" />
          {dur}
          <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500 capitalize">{m.source_type || 'manual'}</span>
        </div>
      </div>

      {/* Agenda */}
      {m.agenda && (
        <p className="text-xs text-gray-500 mt-3 pt-3 border-t border-gray-100 line-clamp-2">{m.agenda}</p>
      )}
    </div>
  )
}
