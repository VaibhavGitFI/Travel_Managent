import { useState, useEffect } from 'react'
import { CheckSquare, CheckCircle, XCircle, Clock, MapPin, Calendar, AlertCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { getApprovals, approveRequest, rejectRequest } from '../api/approvals'
import Button from '../components/ui/Button'
import Badge from '../components/ui/Badge'
import Modal from '../components/ui/Modal'
import StatCard from '../components/ui/StatCard'
import Spinner from '../components/ui/Spinner'

export default function Approvals() {
  const [requests,   setRequests]   = useState([])
  const [loading,    setLoading]    = useState(true)
  const [rejectModal, setRejectModal] = useState(false)
  const [selected,   setSelected]   = useState(null)
  const [reason,     setReason]     = useState('')
  const [processing, setProcessing] = useState(null)

  useEffect(() => { fetchApprovals() }, [])

  const fetchApprovals = async () => {
    try {
      const data = await getApprovals()
      setRequests(Array.isArray(data) ? data : data.requests || data.approvals || [])
    } catch { toast.error('Failed to load approvals') }
    finally { setLoading(false) }
  }

  const handleApprove = async (id) => {
    setProcessing(id)
    try {
      await approveRequest(id)
      toast.success('Request approved!')
      fetchApprovals()
    } catch (err) {
      toast.error(err.response?.data?.error || 'Approval failed')
    } finally {
      setProcessing(null)
    }
  }

  const openReject = (req) => {
    setSelected(req)
    setReason('')
    setRejectModal(true)
  }

  const handleReject = async () => {
    if (!selected) return
    setProcessing(selected.id)
    try {
      await rejectRequest(selected.id, reason)
      toast.success('Request rejected.')
      setRejectModal(false)
      fetchApprovals()
    } catch (err) {
      toast.error(err.response?.data?.error || 'Rejection failed')
    } finally {
      setProcessing(null)
    }
  }

  const pending  = requests.filter((r) => r.status === 'pending').length
  const approved = requests.filter((r) => r.status === 'approved').length
  const rejected = requests.filter((r) => r.status === 'rejected').length

  return (
    <div className="mx-auto w-full max-w-7xl space-y-4 rounded-3xl border border-[#cdd6e0] bg-[radial-gradient(circle_at_top_left,#f6f9fc_0%,transparent_38%),linear-gradient(180deg,#edf1f5_0%,#E0E1DD_100%)] px-3 pb-6 pt-4 sm:space-y-5 sm:px-5 md:px-6 md:pb-8">
      <div>
        <h2 className="text-xl font-bold text-gray-900 font-heading">Approvals</h2>
        <p className="text-sm text-gray-500 mt-0.5">Review and approve travel requests from your team</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard icon={<Clock size={20} />}        value={pending}  label="Awaiting Approval" accentColor="orange" loading={loading} />
        <StatCard icon={<CheckCircle size={20} />}  value={approved} label="Approved"           accentColor="green"  loading={loading} />
        <StatCard icon={<XCircle size={20} />}      value={rejected} label="Rejected"            accentColor="red"    loading={loading} />
      </div>

      {/* Requests list */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-card overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-50 flex items-center justify-between">
          <h3 className="font-semibold text-gray-800 font-heading">Pending Requests</h3>
          <Badge variant="orange" dot>{pending} pending</Badge>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12"><Spinner size="md" color="accent" /></div>
        ) : requests.filter((r) => r.status === 'pending').length === 0 ? (
          <div className="py-16 text-center">
            <CheckSquare size={32} className="mx-auto text-gray-200 mb-3" />
            <p className="text-gray-400 font-medium">No pending approvals</p>
            <p className="text-xs text-gray-300 mt-1">All caught up!</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-50">
            {requests
              .filter((r) => r.status === 'pending')
              .map((req) => (
                <ApprovalRow
                  key={req.id}
                  request={req}
                  onApprove={() => handleApprove(req.id)}
                  onReject={() => openReject(req)}
                  processing={processing === req.id}
                />
              ))}
          </div>
        )}

        {/* History section */}
        {requests.filter((r) => r.status !== 'pending').length > 0 && (
          <>
            <div className="px-6 py-3 bg-gray-50 border-t border-gray-100">
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">History</h4>
            </div>
            <div className="divide-y divide-gray-50">
              {requests
                .filter((r) => r.status !== 'pending')
                .slice(0, 10)
                .map((req) => (
                  <ApprovalRow key={req.id} request={req} readOnly />
                ))}
            </div>
          </>
        )}
      </div>

      {/* Reject Modal */}
      <Modal
        open={rejectModal}
        onClose={() => setRejectModal(false)}
        title="Reject Request"
        subtitle={selected ? `${selected.from_city} → ${selected.to_city}` : ''}
        width="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setRejectModal(false)}>Cancel</Button>
            <Button variant="danger" onClick={handleReject} loading={!!processing}>
              Reject Request
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="flex items-start gap-3 p-3 rounded-lg bg-red-50 border border-red-100">
            <AlertCircle size={16} className="text-red-500 mt-0.5 shrink-0" />
            <p className="text-sm text-red-700">
              This action will notify the employee. Please provide a reason.
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-700">Rejection Reason</label>
            <textarea
              rows={3}
              placeholder="Enter reason for rejection..."
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-red-400/20 focus:border-red-400 transition-all resize-none"
            />
          </div>
        </div>
      </Modal>
    </div>
  )
}

function ApprovalRow({ request: r, onApprove, onReject, processing, readOnly }) {
  return (
    <div className="flex flex-col gap-3 px-4 py-4 transition-colors hover:bg-gray-50/50 sm:flex-row sm:items-center sm:gap-4 sm:px-6">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-3 flex-wrap">
          <p className="text-sm font-semibold text-gray-800">
            {r.from_city} → {r.to_city}
          </p>
          <Badge status={r.status} dot>{r.status}</Badge>
        </div>
        <div className="flex items-center gap-3 mt-1 flex-wrap">
          {r.employee_name && (
            <span className="text-xs text-gray-500 font-medium">{r.employee_name}</span>
          )}
          {r.travel_date && (
            <span className="flex items-center gap-1 text-xs text-gray-400">
              <Calendar size={11} />
              {r.travel_date}
            </span>
          )}
          {r.purpose && (
            <span className="text-xs text-gray-400 capitalize">{r.purpose.replace('_', ' ')}</span>
          )}
          {r.estimated_budget && (
            <span className="text-xs text-gray-500 font-medium">
              ₹{Number(r.estimated_budget).toLocaleString('en-IN')}
            </span>
          )}
        </div>
      </div>

      {!readOnly && r.status === 'pending' && (
        <div className="flex items-center justify-end gap-2 shrink-0">
          <Button
            size="sm"
            variant="success"
            leftIcon={<CheckCircle size={14} />}
            onClick={onApprove}
            loading={processing}
            className="!text-xs"
          >
            Approve
          </Button>
          <Button
            size="sm"
            variant="danger"
            leftIcon={<XCircle size={14} />}
            onClick={onReject}
            disabled={processing}
            className="!text-xs"
          >
            Reject
          </Button>
        </div>
      )}

      {readOnly && r.status === 'approved' && (
        <CheckCircle size={18} className="text-success-500 shrink-0" />
      )}
      {readOnly && r.status === 'rejected' && (
        <XCircle size={18} className="text-red-400 shrink-0" />
      )}
    </div>
  )
}
