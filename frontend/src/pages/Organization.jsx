import { useState, useEffect, useCallback, useRef } from 'react'
import { Building2, Users, Mail, Shield, UserPlus, Trash2, Crown, ChevronDown, Globe, Zap, FileText, Receipt, Camera, Loader2 } from 'lucide-react'
import { motion } from 'framer-motion'
import toast from 'react-hot-toast'
import useStore from '../store/useStore'
import {
  createOrganization,
  getMyOrganization,
  getOrgMembers,
  inviteMember,
  updateMemberRole,
  removeMember,
  updateOrgSettings,
} from '../api/organizations'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import Badge from '../components/ui/Badge'
import Spinner from '../components/ui/Spinner'

const ORG_ROLES = [
  { value: 'org_owner', label: 'Owner', color: 'amber' },
  { value: 'org_admin', label: 'Admin', color: 'blue' },
  { value: 'org_manager', label: 'Manager', color: 'green' },
  { value: 'member', label: 'Member', color: 'gray' },
]

function roleBadge(role) {
  const r = ORG_ROLES.find((x) => x.value === role) || { label: role, color: 'gray' }
  return <Badge variant={r.color}>{r.label}</Badge>
}

// ── Create Org Form ──────────────────────────────────────────────────────────
function CreateOrgForm({ onCreated }) {
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!name.trim()) return toast.error('Organization name is required')
    setLoading(true)
    try {
      const data = await createOrganization({ name: name.trim() })
      if (data.success) {
        toast.success(data.message || 'Organization created!')
        onCreated()
      } else {
        toast.error(data.error || 'Failed to create organization')
      }
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to create organization')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <Card className="w-full max-w-md">
        <div className="text-center mb-6">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-cyan-500 text-white shadow-lg">
            <Building2 size={28} />
          </div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">Create Your Organization</h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Set up your company workspace to manage travel, expenses, and approvals.
          </p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Organization Name"
            placeholder="e.g. Acme Corp"
            value={name}
            onChange={(e) => setName(e.target.value)}
            icon={Building2}
            autoFocus
          />
          <Button type="submit" loading={loading} className="w-full">
            Create Organization
          </Button>
        </form>
      </Card>
    </div>
  )
}

// ── Invite Form ──────────────────────────────────────────────────────────────
function InviteForm({ onInvited }) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('member')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!email.trim()) return toast.error('Email is required')
    setLoading(true)
    try {
      const data = await inviteMember({ email: email.trim(), role })
      if (data.success) {
        toast.success(data.message || 'Member invited!')
        setEmail('')
        onInvited()
      } else {
        toast.error(data.error || 'Failed to invite member')
      }
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to invite')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
      <div className="flex-1 min-w-[200px]">
        <Input
          label="Invite by Email"
          placeholder="user@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          icon={Mail}
        />
      </div>
      <div className="w-36">
        <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Role</label>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-white"
        >
          <option value="member">Member</option>
          <option value="org_manager">Manager</option>
          <option value="org_admin">Admin</option>
        </select>
      </div>
      <Button type="submit" loading={loading} variant="primary" className="shrink-0">
        <UserPlus size={16} className="mr-1.5" /> Invite
      </Button>
    </form>
  )
}

// ── Member Row ───────────────────────────────────────────────────────────────
function MemberRow({ member, currentUserId, myRole, onRefresh }) {
  const [changingRole, setChangingRole] = useState(false)
  const [removing, setRemoving] = useState(false)
  const isMe = member.user_id === currentUserId
  const canManage = ['org_owner', 'org_admin'].includes(myRole) && !isMe && member.org_role !== 'org_owner'

  const handleRoleChange = async (newRole) => {
    setChangingRole(true)
    try {
      const data = await updateMemberRole(member.user_id, newRole)
      if (data.success) {
        toast.success(data.message)
        onRefresh()
      } else {
        toast.error(data.error)
      }
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to update role')
    } finally {
      setChangingRole(false)
    }
  }

  const handleRemove = async () => {
    if (!confirm(`Remove ${member.full_name || member.username} from the organization?`)) return
    setRemoving(true)
    try {
      const data = await removeMember(member.user_id)
      if (data.success) {
        toast.success('Member removed')
        onRefresh()
      } else {
        toast.error(data.error)
      }
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to remove')
    } finally {
      setRemoving(false)
    }
  }

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3 dark:border-gray-700 dark:bg-gray-800">
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-cyan-500 text-sm font-bold text-white">
          {member.avatar_initials || (member.full_name || '?')[0].toUpperCase()}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-gray-900 dark:text-white truncate">
              {member.full_name || member.username}
            </span>
            {isMe && <Badge variant="sky">You</Badge>}
            {member.org_role === 'org_owner' && <Crown size={14} className="text-amber-500" />}
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-400 truncate block">{member.email}</span>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {canManage ? (
          <div className="relative">
            <select
              value={member.org_role}
              onChange={(e) => handleRoleChange(e.target.value)}
              disabled={changingRole}
              className="appearance-none rounded-md border border-gray-300 bg-white py-1 pl-2 pr-7 text-xs font-medium dark:border-gray-600 dark:bg-gray-700 dark:text-white"
            >
              <option value="member">Member</option>
              <option value="org_manager">Manager</option>
              <option value="org_admin">Admin</option>
            </select>
            <ChevronDown size={12} className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 text-gray-400" />
          </div>
        ) : (
          roleBadge(member.org_role)
        )}
        {canManage && (
          <button
            onClick={handleRemove}
            disabled={removing}
            className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20"
            title="Remove member"
          >
            {removing ? <Spinner size="xs" /> : <Trash2 size={15} />}
          </button>
        )}
      </div>
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────────────────────────
export default function Organization() {
  const { auth, org, setOrg, setOrgMembers } = useStore()
  const [members, setMembers] = useState([])
  const [loading, setLoading] = useState(true)
  const [orgData, setOrgData] = useState(org?.current || null)
  const logoRef = useRef(null)
  const [uploadingLogo, setUploadingLogo] = useState(false)

  const loadOrg = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getMyOrganization()
      const o = data.organization || null
      setOrgData(o)
      setOrg(o)
      if (o) {
        const mData = await getOrgMembers()
        setMembers(mData.members || [])
        setOrgMembers(mData.members || [])
      }
    } catch {
      // not in org
    } finally {
      setLoading(false)
    }
  }, [setOrg, setOrgMembers])

  useEffect(() => { loadOrg() }, [loadOrg])

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Spinner size="lg" />
      </div>
    )
  }

  // No org yet — show create form
  if (!orgData) {
    return <CreateOrgForm onCreated={loadOrg} />
  }

  const myRole = orgData.my_role || 'member'
  const isAdmin = ['org_owner', 'org_admin'].includes(myRole)
  const imgBase = import.meta.env.DEV ? 'http://localhost:3399' : ''
  const orgLogoUrl = orgData.logo_url ? `${imgBase}/api/uploads/${orgData.logo_url}` : null

  const handleLogoUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.size > 2 * 1024 * 1024) { toast.error('Max 2 MB'); return }
    setUploadingLogo(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      // Use axios client — auto-attaches CSRF token
      const { default: client } = await import('../api/client')
      const { data: uploadData } = await client.post('/uploads', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      if (!uploadData.success && !uploadData.url) { toast.error('Upload failed'); return }
      const filename = uploadData.url?.split('/').pop() || uploadData.filename
      const resp = await updateOrgSettings({ logo_url: filename })
      if (resp.success) {
        toast.success('Logo updated')
        loadOrg()
      }
    } catch (err) { toast.error(err.response?.data?.error || 'Failed to upload logo') }
    finally { setUploadingLogo(false); if (logoRef.current) logoRef.current.value = '' }
  }

  return (
    <div className="space-y-6">
      {/* Header with gradient banner */}
      <motion.div
        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}
        className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden"
      >
        <div className="bg-gradient-to-r from-[#0a1628] via-[#0d2a5e] to-[#1a3a6e] px-6 py-5 relative">
          <div className="absolute inset-0 opacity-20" style={{ backgroundImage: 'radial-gradient(circle at 20% 50%, rgba(255,255,255,0.3) 0%, transparent 50%), radial-gradient(circle at 80% 50%, rgba(56,189,248,0.2) 0%, transparent 50%)' }} />
          <div className="relative flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="relative group">
                <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-white/15 backdrop-blur-sm text-white text-2xl font-bold shadow-lg border border-white/20 overflow-hidden">
                  {orgLogoUrl
                    ? <img src={orgLogoUrl + '?v=' + Date.now()} alt="" className="h-full w-full object-cover" onError={(e) => { e.target.style.display='none' }} />
                    : (orgData.name || '?')[0].toUpperCase()
                  }
                </div>
                {isAdmin && (
                  <button onClick={() => logoRef.current?.click()} disabled={uploadingLogo}
                    className="absolute inset-0 flex items-center justify-center rounded-xl bg-black/40 text-white opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer">
                    {uploadingLogo ? <Loader2 size={16} className="animate-spin" /> : <Camera size={16} />}
                  </button>
                )}
                <input ref={logoRef} type="file" accept="image/*" className="hidden" onChange={handleLogoUpload} />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">{orgData.name}</h1>
                <p className="text-xs text-blue-200 flex items-center gap-2">
                  <Globe size={11} /> {orgData.slug} &middot; {(orgData.plan || 'free').toUpperCase()} plan
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {roleBadge(myRole)}
            </div>
          </div>
        </div>
        <div className="px-6 pb-5">

          {/* Quick stats row */}
          <div className="grid grid-cols-3 gap-3 mt-4">
            <div className="text-center p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <p className="text-lg font-bold text-blue-600">{orgData.member_count || members.length}</p>
              <p className="text-[10px] text-gray-500 flex items-center justify-center gap-1"><Users size={10} /> Members</p>
            </div>
            <div className="text-center p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <p className="text-lg font-bold text-green-600">{(orgData.plan || 'free').toUpperCase()}</p>
              <p className="text-[10px] text-gray-500 flex items-center justify-center gap-1"><Zap size={10} /> Plan</p>
            </div>
            <div className="text-center p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <p className="text-lg font-bold text-purple-600">{orgData.max_members || 50}</p>
              <p className="text-[10px] text-gray-500 flex items-center justify-center gap-1"><Shield size={10} /> Max Members</p>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Invite (admin only) */}
      {isAdmin && (
        <Card title="Invite Members" subtitle="Add team members to your organization">
          <InviteForm onInvited={loadOrg} />
        </Card>
      )}

      {/* Members list */}
      <Card
        title={<span className="flex items-center gap-2"><Users size={18} /> Members ({members.length})</span>}
      >
        {members.length === 0 ? (
          <p className="text-center text-gray-500 py-8">No members yet. Invite your team!</p>
        ) : (
          <div className="space-y-2">
            {members.map((m) => (
              <MemberRow
                key={m.user_id}
                member={m}
                currentUserId={auth.user?.id}
                myRole={myRole}
                onRefresh={loadOrg}
              />
            ))}
          </div>
        )}
      </Card>

      {/* Org Settings (admin only) */}
      {isAdmin && (
        <OrgSettingsCard orgData={orgData} onUpdated={loadOrg} />
      )}
    </div>
  )
}

function OrgSettingsCard({ orgData, onUpdated }) {
  const [name, setName] = useState(orgData.name || '')
  const [billingEmail, setBillingEmail] = useState(orgData.billing_email || '')
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try {
      const data = await updateOrgSettings({ name: name.trim(), billing_email: billingEmail.trim() })
      if (data.success) {
        toast.success('Settings updated')
        onUpdated()
      } else {
        toast.error(data.error)
      }
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card title={<span className="flex items-center gap-2"><Shield size={18} /> Organization Settings</span>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Input
          label="Organization Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          icon={Building2}
        />
        <Input
          label="Billing Email"
          value={billingEmail}
          onChange={(e) => setBillingEmail(e.target.value)}
          icon={Mail}
        />
      </div>
      <div className="mt-4 flex justify-end">
        <Button onClick={handleSave} loading={saving}>
          Save Changes
        </Button>
      </div>
    </Card>
  )
}
