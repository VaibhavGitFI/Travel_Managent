import { useState, useEffect } from 'react'
import {
  Users, Plus, MapPin, Calendar, Clock, Edit2, Trash2,
  Sparkles, Building2, Phone, Mail, Linkedin, MessageSquare, FileText, CheckCircle,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { getMeetings, createMeeting, updateMeeting, deleteMeeting, suggestSchedule, parseMeetingText } from '../api/meetings'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import Select from '../components/ui/Select'
import Badge from '../components/ui/Badge'
import Modal from '../components/ui/Modal'
import Spinner from '../components/ui/Spinner'

const sourceTypes = [
  { value: 'manual',    label: 'Manual Entry' },
  { value: 'email',     label: 'Email' },
  { value: 'whatsapp',  label: 'WhatsApp' },
  { value: 'phone',     label: 'Phone' },
  { value: 'calendar',  label: 'Calendar Invite' },
  { value: 'linkedin',  label: 'LinkedIn' },
]

const sourceIcons = {
  manual:   Building2,
  email:    Mail,
  whatsapp: MessageSquare,
  phone:    Phone,
  calendar: Calendar,
  linkedin: Linkedin,
}

const emptyForm = {
  client_name: '', company: '', location: '', meeting_date: '',
  meeting_time: '', duration_minutes: '60', agenda: '',
  source_type: 'manual', contact_info: '',
}

export default function Meetings() {
  const [meetings, setMeetings]     = useState([])
  const [loading,  setLoading]      = useState(true)
  const [modal,    setModal]        = useState(false)
  const [editing,  setEditing]      = useState(null)
  const [form,     setForm]         = useState(emptyForm)
  const [submitting, setSubmitting] = useState(false)
  const [errors,   setErrors]       = useState({})
  const [aiModal,  setAiModal]      = useState(false)
  const [aiResult, setAiResult]     = useState(null)
  const [aiLoading, setAiLoading]   = useState(false)

  // ── Parse Email/WA state ─────────────────────────────────────────────────
  const [parseModal,   setParseModal]   = useState(false)
  const [parseText,    setParseText]    = useState('')
  const [parseSource,  setParseSource]  = useState('email')
  const [parseLoading, setParseLoading] = useState(false)
  const [parsedData,   setParsedData]   = useState(null)

  useEffect(() => { fetchMeetings() }, [])

  const fetchMeetings = async () => {
    try {
      const data = await getMeetings()
      setMeetings(Array.isArray(data) ? data : data.meetings || [])
    } catch { toast.error('Failed to load meetings') }
    finally { setLoading(false) }
  }

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }))

  const openNew = () => {
    setEditing(null)
    setForm(emptyForm)
    setErrors({})
    setModal(true)
  }

  const openEdit = (m) => {
    setEditing(m)
    setForm({
      client_name:      m.client_name || '',
      company:          m.company     || '',
      location:         m.location    || '',
      meeting_date:     m.meeting_date || '',
      meeting_time:     m.meeting_time || '',
      duration_minutes: String(m.duration_minutes || 60),
      agenda:           m.agenda      || '',
      source_type:      m.source_type || 'manual',
      contact_info:     m.contact_info || '',
    })
    setErrors({})
    setModal(true)
  }

  const validate = () => {
    const e = {}
    if (!form.client_name.trim()) e.client_name = 'Client name required'
    if (!form.meeting_date)       e.meeting_date = 'Date required'
    return e
  }

  const handleSubmit = async () => {
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setErrors({})
    setSubmitting(true)
    try {
      if (editing) {
        await updateMeeting(editing.id, form)
        toast.success('Meeting updated!')
      } else {
        await createMeeting(form)
        toast.success('Meeting created!')
      }
      setModal(false)
      fetchMeetings()
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to save meeting')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this meeting?')) return
    try {
      await deleteMeeting(id)
      toast.success('Meeting deleted')
      fetchMeetings()
    } catch { toast.error('Delete failed') }
  }

  const handleAiSchedule = async () => {
    setAiLoading(true)
    try {
      const data = await suggestSchedule({ meetings: meetings.slice(0, 10) })
      setAiResult(data)
      setAiModal(true)
    } catch { toast.error('AI scheduling failed') }
    finally { setAiLoading(false) }
  }

  const openParseModal = () => {
    setParseText('')
    setParsedData(null)
    setParseSource('email')
    setParseModal(true)
  }

  const handleParse = async () => {
    if (!parseText.trim()) { toast.error('Paste some text first'); return }
    setParseLoading(true)
    try {
      const result = await parseMeetingText(parseText, parseSource)
      if (result.success) {
        setParsedData(result)
        toast.success('Meeting details extracted!')
      } else {
        toast.error(result.error || 'Could not extract details')
      }
    } catch (err) {
      toast.error(err.response?.data?.error || 'Parse failed')
    } finally {
      setParseLoading(false)
    }
  }

  const useExtractedData = () => {
    if (!parsedData?.extracted) return
    const ex = parsedData.extracted
    setForm({
      client_name:      ex.client_name      || '',
      company:          ex.company          || '',
      location:         ex.location         || '',
      meeting_date:     ex.meeting_date     || '',
      meeting_time:     ex.meeting_time     || '',
      duration_minutes: '60',
      agenda:           ex.agenda           || '',
      source_type:      parsedData.source_type || parseSource || 'email',
      contact_info:     ex.contact_info     || '',
    })
    setEditing(null)
    setErrors({})
    setParseModal(false)
    setModal(true)
  }

  return (
    <div className="mx-auto w-full max-w-7xl space-y-4 rounded-3xl border border-[#cdd6e0] bg-[radial-gradient(circle_at_top_left,#f6f9fc_0%,transparent_38%),linear-gradient(180deg,#edf1f5_0%,#E0E1DD_100%)] px-3 pb-6 pt-4 sm:space-y-5 sm:px-5 md:px-6 md:pb-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900 font-heading">Client Meetings</h2>
          <p className="text-sm text-gray-500 mt-0.5">Manage and schedule client meetings</p>
        </div>
        <div className="flex w-full flex-wrap gap-2 sm:w-auto">
          <Button
            variant="secondary"
            leftIcon={<FileText size={15} />}
            onClick={openParseModal}
            className="w-full justify-center sm:w-auto"
          >
            Parse Email/WA
          </Button>
          <Button
            variant="secondary"
            leftIcon={<Sparkles size={15} />}
            onClick={handleAiSchedule}
            loading={aiLoading}
            className="w-full justify-center sm:w-auto"
          >
            AI Schedule
          </Button>
          <Button leftIcon={<Plus size={16} />} onClick={openNew} className="w-full justify-center sm:w-auto">
            Add Meeting
          </Button>
        </div>
      </div>

      {/* Meeting grid */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Spinner size="md" color="accent" />
        </div>
      ) : meetings.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-100 shadow-card py-16 text-center">
          <Users size={36} className="mx-auto text-gray-200 mb-3" />
          <p className="text-gray-400 font-medium">No meetings scheduled</p>
          <Button size="sm" variant="outline" className="mt-4" onClick={openNew}>
            Schedule a meeting
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {meetings.map((m) => (
            <MeetingCard
              key={m.id}
              meeting={m}
              onEdit={() => openEdit(m)}
              onDelete={() => handleDelete(m.id)}
            />
          ))}
        </div>
      )}

      {/* ── Create/Edit Modal ──────────────────── */}
      <Modal
        open={modal}
        onClose={() => { setModal(false); setErrors({}) }}
        title={editing ? 'Edit Meeting' : 'Schedule Meeting'}
        width="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setModal(false)}>Cancel</Button>
            <Button loading={submitting} onClick={handleSubmit}>
              {editing ? 'Save Changes' : 'Create Meeting'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="Client Name"
              placeholder="e.g. Rajesh Kumar"
              value={form.client_name}
              onChange={(e) => set('client_name', e.target.value)}
              error={errors.client_name}
              required
            />
            <Input
              label="Company"
              placeholder="e.g. Acme Corp"
              value={form.company}
              onChange={(e) => set('company', e.target.value)}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="Meeting Date"
              type="date"
              value={form.meeting_date}
              onChange={(e) => set('meeting_date', e.target.value)}
              error={errors.meeting_date}
              required
            />
            <Input
              label="Time"
              type="time"
              value={form.meeting_time}
              onChange={(e) => set('meeting_time', e.target.value)}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="Location"
              placeholder="Office / Cafe / Virtual"
              value={form.location}
              onChange={(e) => set('location', e.target.value)}
              leftIcon={<MapPin size={16} />}
            />
            <Input
              label="Duration (minutes)"
              type="number"
              min="15"
              max="480"
              step="15"
              value={form.duration_minutes}
              onChange={(e) => set('duration_minutes', e.target.value)}
              leftIcon={<Clock size={16} />}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Select
              label="Source"
              options={sourceTypes}
              value={form.source_type}
              onChange={(e) => set('source_type', e.target.value)}
            />
            <Input
              label="Contact Info"
              placeholder="Phone / email"
              value={form.contact_info}
              onChange={(e) => set('contact_info', e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-700">Agenda</label>
            <textarea
              rows={3}
              placeholder="Meeting agenda or notes..."
              value={form.agenda}
              onChange={(e) => set('agenda', e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-accent-500/20 focus:border-accent-500 transition-all resize-none hover:border-gray-300"
            />
          </div>
        </div>
      </Modal>

      {/* ── AI Schedule Modal ──────────────────── */}
      <Modal
        open={aiModal}
        onClose={() => setAiModal(false)}
        title="AI Schedule Suggestions"
        subtitle="Optimized by Gemini AI"
        width="lg"
      >
        {aiResult ? (
          <div className="space-y-4">
            {aiResult.suggestions?.map((s, i) => (
              <div key={i} className="p-4 rounded-xl bg-accent-50 border border-accent-100">
                <p className="text-sm font-medium text-accent-900">{s.suggestion || s}</p>
                {s.reason && <p className="text-xs text-accent-600 mt-1">{s.reason}</p>}
              </div>
            ))}
            {aiResult.message && (
              <p className="text-sm text-gray-600 leading-relaxed">{aiResult.message}</p>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-center py-8">
            <Spinner size="md" color="accent" />
          </div>
        )}
      </Modal>

      {/* ── Parse Email/WA Modal ───────────────── */}
      <Modal
        open={parseModal}
        onClose={() => { setParseModal(false); setParsedData(null) }}
        title="Parse Email / WhatsApp"
        subtitle="Paste raw text — Gemini will extract meeting details"
        width="lg"
        footer={
          parsedData ? (
            <>
              <Button variant="secondary" onClick={() => setParsedData(null)}>Try Again</Button>
              <Button leftIcon={<CheckCircle size={15} />} onClick={useExtractedData}>
                Use These Details
              </Button>
            </>
          ) : (
            <>
              <Button variant="secondary" onClick={() => setParseModal(false)}>Cancel</Button>
              <Button
                leftIcon={<Sparkles size={15} />}
                loading={parseLoading}
                onClick={handleParse}
              >
                Extract Details
              </Button>
            </>
          )
        }
      >
        {!parsedData ? (
          <div className="space-y-4">
            <div className="flex gap-3">
              {['email', 'whatsapp'].map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setParseSource(s)}
                  className={`flex-1 rounded-lg border py-2 text-sm font-medium transition-colors capitalize ${
                    parseSource === s
                      ? 'border-accent-400 bg-accent-50 text-accent-700'
                      : 'border-gray-200 bg-white text-gray-500 hover:bg-gray-50'
                  }`}
                >
                  {s === 'whatsapp' ? 'WhatsApp' : 'Email'}
                </button>
              ))}
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-gray-700">
                Paste {parseSource === 'whatsapp' ? 'WhatsApp message' : 'email body'}
              </label>
              <textarea
                rows={8}
                placeholder={
                  parseSource === 'whatsapp'
                    ? 'e.g. "Hi, can we meet on 20 March at 3pm at our BKC office? - Rajan, Acme Corp +91 9876543210"'
                    : 'e.g. "Dear Mr. Sharma, Please confirm the meeting on March 20th at 10:00 AM at our office in Lower Parel..."'
                }
                value={parseText}
                onChange={(e) => setParseText(e.target.value)}
                className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-accent-500/20 focus:border-accent-500 transition-all resize-none hover:border-gray-300"
              />
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-100 rounded-lg px-3 py-2">
              <CheckCircle size={14} />
              <span>
                Details extracted via{' '}
                <strong>{parsedData.ai_source === 'gemini' ? 'Gemini AI' : 'Pattern Matching'}</strong>
                {parsedData.confidence === 'low' && ' (low confidence — please review)'}
              </span>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {Object.entries(parsedData.extracted || {}).map(([key, value]) => (
                <div key={key} className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
                  <p className="text-[10px] font-medium uppercase tracking-wide text-gray-400 mb-0.5">
                    {key.replace(/_/g, ' ')}
                  </p>
                  <p className="text-sm text-gray-800 break-words">{String(value)}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}

function MeetingCard({ meeting: m, onEdit, onDelete }) {
  const SourceIcon = sourceIcons[m.source_type] || Building2
  const mins = m.duration_minutes || 60
  const hours = Math.floor(mins / 60)
  const rem   = mins % 60
  const dur   = hours ? `${hours}h${rem ? ` ${rem}m` : ''}` : `${mins}m`

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-card p-5 card-hover">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-accent-50 border border-accent-100 flex items-center justify-center text-accent-600">
            <SourceIcon size={16} />
          </div>
          <div>
            <p className="font-semibold text-gray-900 leading-tight">{m.client_name}</p>
            {m.company && <p className="text-xs text-gray-400">{m.company}</p>}
          </div>
        </div>
        <div className="flex gap-1">
          <button onClick={onEdit} className="p-1.5 rounded-lg text-gray-400 hover:text-accent-600 hover:bg-accent-50 transition-colors">
            <Edit2 size={14} />
          </button>
          <button onClick={onDelete} className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors">
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      <div className="space-y-1.5">
        {m.meeting_date && (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <Calendar size={12} className="text-gray-300" />
            {m.meeting_date}
            {m.meeting_time && ` at ${m.meeting_time}`}
          </div>
        )}
        {m.location && (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <MapPin size={12} className="text-gray-300" />
            {m.location}
          </div>
        )}
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Clock size={12} className="text-gray-300" />
          {dur}
          <Badge variant="gray" size="xs" className="ml-1 capitalize">{m.source_type || 'manual'}</Badge>
        </div>
      </div>

      {m.agenda && (
        <p className="text-xs text-gray-500 mt-3 pt-3 border-t border-gray-50 line-clamp-2">
          {m.agenda}
        </p>
      )}
    </div>
  )
}
