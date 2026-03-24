import { useState, useEffect } from 'react'
import ReactDOM from 'react-dom'
import { cn } from '../lib/cn'
import {
  CheckCircle, XCircle, Clock, Calendar, AlertCircle, Shield,
  Plane, User, IndianRupee, Briefcase, ChevronDown, ChevronUp,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { getApprovals, approveRequest, rejectRequest } from '../api/approvals'
import useAutoRefresh from '../hooks/useAutoRefresh'
import StatCard from '../components/ui/StatCard'
import Spinner from '../components/ui/Spinner'
import { SkeletonRow } from '../components/ui/Skeleton'

const inputBase = 'w-full rounded-lg border border-gray-200 bg-white px-3.5 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 transition-all hover:border-gray-300 focus:border-red-400 focus:outline-none focus:ring-2 focus:ring-red-400/15'

export default function Approvals() {
  const [requests, setRequests] = useState([])
  const [loading, setLoading] = useState(true)
  const [rejectModal, setRejectModal] = useState(false)
  const [selected, setSelected] = useState(null)
  const [reason, setReason] = useState('')
  const [processing, setProcessing] = useState(null)
  const [showHistory, setShowHistory] = useState(false)

  const [view, setView] = useState('manager') // 'manager' or 'employee'

  const fetch = async () => {
    try {
      const data = await getApprovals()
      setRequests(Array.isArray(data) ? data : data.requests || data.approvals || [])
      if (data.view) setView(data.view)
    } catch (err) {
      toast.error('Failed to load approvals')
    }
    finally { setLoading(false) }
  }

  useEffect(() => { fetch() }, [])
  useAutoRefresh('approvals', fetch)

  const handleApprove = async (id) => {
    setProcessing(id)
    try { await approveRequest(id); toast.success('Request approved!'); fetch() }
    catch (err) { toast.error(err.response?.data?.error || 'Approval failed') }
    finally { setProcessing(null) }
  }

  const openReject = (req) => { setSelected(req); setReason(''); setRejectModal(true) }

  const handleReject = async () => {
    if (!selected) return
    const rid = selected.request_id || selected.id
    setProcessing(rid)
    try { await rejectRequest(rid, reason); toast.success('Request rejected.'); setRejectModal(false); fetch() }
    catch (err) { toast.error(err.response?.data?.error || 'Rejection failed') }
    finally { setProcessing(null) }
  }

  const pendingList = requests.filter(r => r.status === 'pending')
  const historyList = requests.filter(r => r.status !== 'pending')
  const approved = requests.filter(r => r.status === 'approved').length
  const rejected = requests.filter(r => r.status === 'rejected').length

  return (
    <div className="mx-auto w-full max-w-7xl space-y-5">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-orange-600">
            <Shield size={14} className="text-white" />
          </div>
          <h1 className="font-heading text-xl font-bold text-gray-900">Approvals</h1>
          {pendingList.length > 0 && (
            <span className="rounded-full bg-amber-50 border border-amber-200 px-2 py-0.5 text-[10px] font-bold text-amber-700">
              {pendingList.length} pending
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-gray-500">Review and approve travel requests from your team</p>
      </div>

      {/* ── Employee tracking view ──────────── */}
      {view === 'employee' && (
        <>
          <div className="rounded-xl border border-gray-200 bg-white shadow-card overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100">
              <h3 className="text-sm font-semibold text-gray-900">Your Request Status</h3>
              <p className="text-xs text-gray-500 mt-0.5">Track where your travel requests are in the approval pipeline</p>
            </div>
            {loading ? (
              <div className="divide-y divide-gray-100">{Array.from({ length: 3 }).map((_, i) => <SkeletonRow key={i} />)}</div>
            ) : requests.length === 0 ? (
              <div className="py-14 text-center">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-gray-100 to-gray-200">
                  <Plane size={24} className="text-gray-400" />
                </div>
                <p className="font-semibold text-gray-700">No requests submitted</p>
                <p className="mt-1 text-sm text-gray-500">Submit a travel request to see its approval status here</p>
              </div>
            ) : (
              <div className="divide-y divide-gray-100">
                {requests.map(r => <EmployeeTrackRow key={r.request_id} request={r} />)}
              </div>
            )}
          </div>
        </>
      )}

      {/* ── Manager approval view ─────────── */}
      {view === 'manager' && <>
      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <StatCard icon={<Clock size={20} />} value={loading ? '—' : pendingList.length} label="Awaiting Approval" accentColor="orange" className="rounded-xl border border-gray-200 bg-white shadow-card" loading={loading} />
        <StatCard icon={<CheckCircle size={20} />} value={loading ? '—' : approved} label="Approved" accentColor="green" className="rounded-xl border border-gray-200 bg-white shadow-card" loading={loading} />
        <StatCard icon={<XCircle size={20} />} value={loading ? '—' : rejected} label="Rejected" accentColor="red" className="rounded-xl border border-gray-200 bg-white shadow-card" loading={loading} />
      </div>

      {/* Pending Requests */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-card overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900">Pending Requests</h3>
          {pendingList.length > 0 && (
            <span className="rounded-full bg-amber-100 border border-amber-200 px-2 py-0.5 text-[10px] font-bold text-amber-700">
              {pendingList.length} awaiting
            </span>
          )}
        </div>

        {loading ? (
          <div className="divide-y divide-gray-100">{Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)}</div>
        ) : pendingList.length === 0 ? (
          <div className="py-16 text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-50 to-green-100">
              <CheckCircle size={24} className="text-emerald-500" />
            </div>
            <p className="font-semibold text-gray-700">All caught up</p>
            <p className="mt-1 text-sm text-gray-500">No pending approvals at the moment</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {pendingList.map(req => (
              <ApprovalRow
                key={req.request_id || req.id}
                request={req}
                onApprove={() => handleApprove(req.request_id || req.id)}
                onReject={() => openReject(req)}
                processing={processing === (req.request_id || req.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* History */}
      {historyList.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white shadow-card overflow-hidden">
          <button onClick={() => setShowHistory(v => !v)}
            className="flex w-full items-center justify-between px-5 py-3.5 text-left hover:bg-gray-50/50 transition-colors">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-gray-900">History</h3>
              <span className="text-xs text-gray-400">{historyList.length} decisions</span>
            </div>
            {showHistory ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
          </button>
          {showHistory && (
            <div className="divide-y divide-gray-100 border-t border-gray-100">
              {historyList.slice(0, 15).map(req => (
                <ApprovalRow key={req.request_id || req.id} request={req} readOnly />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Reject Modal */}
      {rejectModal && ReactDOM.createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center overflow-y-auto p-4"
          onClick={(e) => { if (e.target === e.currentTarget) setRejectModal(false) }}
          style={{ background: 'rgba(15,23,42,0.6)', backdropFilter: 'blur(6px)', WebkitBackdropFilter: 'blur(6px)' }}>
          <div className="relative w-full max-w-md rounded-2xl bg-white shadow-2xl">
            <div className="border-b border-gray-100 px-6 py-4">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-red-500 to-rose-600">
                  <XCircle size={14} className="text-white" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-gray-900">Reject Request</h3>
                  <p className="text-xs text-gray-500">{selected?.from_city} → {selected?.to_city}</p>
                </div>
              </div>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 p-3">
                <AlertCircle size={14} className="text-red-500 mt-0.5 shrink-0" />
                <p className="text-xs text-red-700">This will notify the employee via email, WhatsApp, and Zoho Cliq. Please provide a reason.</p>
              </div>

              {/* Request summary */}
              <div className="rounded-lg bg-gray-50 border border-gray-100 p-3 space-y-1.5">
                <div className="flex items-center gap-2 text-xs text-gray-600">
                  <User size={11} className="text-gray-400" /> {selected?.employee_name || 'Employee'}
                </div>
                <div className="flex items-center gap-2 text-xs text-gray-600">
                  <Plane size={11} className="text-gray-400" /> {selected?.from_city} → {selected?.to_city}
                </div>
                {selected?.travel_date && (
                  <div className="flex items-center gap-2 text-xs text-gray-600">
                    <Calendar size={11} className="text-gray-400" /> {selected.travel_date}
                  </div>
                )}
                {selected?.estimated_budget && (
                  <div className="flex items-center gap-2 text-xs text-gray-600">
                    <IndianRupee size={11} className="text-gray-400" /> ₹{Number(selected.estimated_budget).toLocaleString('en-IN')}
                  </div>
                )}
              </div>

              <div>
                <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-gray-500">Rejection Reason</label>
                <textarea rows={3} placeholder="Enter reason for rejection..."
                  value={reason} onChange={(e) => setReason(e.target.value)}
                  className={cn(inputBase, 'resize-none')} />
              </div>
            </div>
            <div className="flex justify-end gap-2 border-t border-gray-100 px-6 py-4">
              <button onClick={() => setRejectModal(false)}
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">Cancel</button>
              <button onClick={handleReject} disabled={!!processing}
                className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-red-600 to-rose-500 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
                {processing ? <Spinner size="xs" color="white" /> : <XCircle size={14} />}
                Reject Request
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
      </>}
    </div>
  )
}

function EmployeeTrackRow({ request: r }) {
  const stages = ['draft', 'pending', 'approved', 'booked', 'in_progress', 'completed']
  const rejectedStages = ['draft', 'pending', 'rejected']
  const isRejected = r.status === 'rejected'
  const pipeline = isRejected ? rejectedStages : stages
  const currentIdx = Math.max(pipeline.indexOf(r.status), 0)

  const stageLabels = {
    draft: 'Draft', pending: 'Pending', approved: 'Approved',
    booked: 'Booked', in_progress: 'Travelling', completed: 'Done', rejected: 'Rejected',
  }

  return (
    <div className="px-5 py-4 space-y-3 hover:bg-gray-50/50 transition-colors">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-indigo-50 border border-indigo-100">
            <Plane size={15} className="text-indigo-600" />
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900">{r.from_city || '—'} → {r.to_city || '—'}</p>
            <div className="flex items-center gap-2 text-xs text-gray-500 mt-0.5">
              {r.travel_date && <span>{r.travel_date}</span>}
              {r.purpose && <span className="capitalize">· {r.purpose.replace('_', ' ')}</span>}
              {r.estimated_budget ? <span>· ₹{Number(r.estimated_budget).toLocaleString('en-IN')}</span> : null}
            </div>
          </div>
        </div>
        <span className="text-[10px] font-mono text-gray-300">{r.request_id}</span>
      </div>

      {/* Pipeline tracker */}
      <div className="flex items-center gap-0.5 px-1">
        {pipeline.map((stage, i) => {
          const done = i <= currentIdx
          const isCurrent = i === currentIdx
          const isLast = i === pipeline.length - 1
          const color = isRejected && stage === 'rejected' ? 'bg-red-500' : done ? 'bg-emerald-500' : 'bg-gray-200'
          return (
            <div key={stage} className="flex flex-1 items-center">
              <div className="flex flex-col items-center w-full">
                <div className="flex items-center w-full">
                  <div className={cn('h-2.5 w-2.5 rounded-full shrink-0', color, isCurrent && 'ring-2 ring-offset-1 ring-current')}
                    style={isCurrent ? { color: isRejected ? '#ef4444' : '#10b981' } : undefined} />
                  {!isLast && <div className={cn('h-[3px] flex-1 rounded-full', i < currentIdx ? 'bg-emerald-400' : 'bg-gray-200')} />}
                </div>
                <span className={cn('text-[8px] font-semibold mt-1 text-center leading-none',
                  isCurrent ? (isRejected ? 'text-red-600' : 'text-emerald-700') : done ? 'text-gray-600' : 'text-gray-400')}>
                  {stageLabels[stage]}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Approver info */}
      {(r.approver_name || r.comments) && (
        <div className="flex items-center gap-2 text-[11px] text-gray-500 pl-12">
          <User size={10} className="text-gray-400" />
          {r.approver_name && <span>Reviewed by <strong>{r.approver_name}</strong></span>}
          {r.comments && <span>· {r.comments}</span>}
        </div>
      )}
    </div>
  )
}

function ApprovalRow({ request: r, onApprove, onReject, processing, readOnly }) {
  const statusStyle = {
    approved: { icon: CheckCircle, color: 'text-emerald-500', bg: 'bg-emerald-50', border: 'border-emerald-200', label: 'Approved' },
    rejected: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-50', border: 'border-red-200', label: 'Rejected' },
    pending:  { icon: Clock, color: 'text-amber-500', bg: 'bg-amber-50', border: 'border-amber-200', label: 'Pending' },
  }
  const st = statusStyle[r.status] || statusStyle.pending

  return (
    <div className="flex flex-col gap-3 px-5 py-4 transition-colors hover:bg-gray-50/50 sm:flex-row sm:items-center sm:gap-4">
      {/* Icon */}
      <div className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border', readOnly ? `${st.bg} ${st.border}` : 'bg-amber-50 border-amber-100')}>
        {readOnly ? <st.icon size={16} className={st.color} /> : <Plane size={16} className="text-amber-600" />}
      </div>

      {/* Details */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-semibold text-gray-900">{r.from_city || '—'} → {r.to_city || '—'}</p>
          {readOnly && (
            <span className={cn('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold', st.bg, st.color, st.border)}>
              <span className={cn('h-1.5 w-1.5 rounded-full', st.color.replace('text-', 'bg-'))} />
              {st.label}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 mt-1 flex-wrap text-xs text-gray-500">
          {r.employee_name && (
            <span className="flex items-center gap-1 font-medium">
              <User size={11} className="text-gray-400" /> {r.employee_name}
            </span>
          )}
          {r.travel_date && (
            <span className="flex items-center gap-1">
              <Calendar size={11} className="text-gray-400" /> {r.travel_date}
            </span>
          )}
          {r.purpose && (
            <span className="flex items-center gap-1 capitalize">
              <Briefcase size={11} className="text-gray-400" /> {r.purpose.replace('_', ' ')}
            </span>
          )}
          {r.estimated_budget && (
            <span className="font-semibold text-gray-700">₹{Number(r.estimated_budget).toLocaleString('en-IN')}</span>
          )}
        </div>
      </div>

      {/* Actions */}
      {!readOnly && r.status === 'pending' && (
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={onApprove} disabled={processing}
            className="flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-2 text-xs font-semibold text-emerald-700 transition-colors hover:bg-emerald-100 disabled:opacity-50">
            {processing ? <Spinner size="xs" /> : <CheckCircle size={13} />}
            Approve
          </button>
          <button onClick={onReject} disabled={processing}
            className="flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2 text-xs font-semibold text-red-700 transition-colors hover:bg-red-100 disabled:opacity-50">
            <XCircle size={13} />
            Reject
          </button>
        </div>
      )}
    </div>
  )
}
