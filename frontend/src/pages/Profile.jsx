import { useState, useEffect, useRef } from 'react'
import { Camera, Save, User, Mail, Phone, Building, Briefcase, Shield, Calendar, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { getProfile, updateProfile, uploadAvatar } from '../api/profile'
import useStore from '../store/useStore'
import { cn } from '../lib/cn'
import { format } from 'date-fns'

const ROLE_COLORS = {
  super_admin: 'bg-red-100 text-red-700 border-red-200',
  admin: 'bg-blue-100 text-blue-700 border-blue-200',
  manager: 'bg-violet-100 text-violet-700 border-violet-200',
  employee: 'bg-emerald-100 text-emerald-700 border-emerald-200',
}

const ROLE_LABELS = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  manager: 'Manager',
  employee: 'Employee',
}

export default function Profile() {
  const { auth, setUser, theme } = useStore()
  const dark = theme === 'dark'
  const fileRef = useRef(null)

  const [profile, setProfile] = useState(null)
  const [form, setForm] = useState({ full_name: '', phone: '', department: '', sub_role: '' })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)

  useEffect(() => { loadProfile() }, [])

  const loadProfile = async () => {
    try {
      const data = await getProfile()
      if (data.success && data.user) {
        setProfile(data.user)
        setForm({
          full_name: data.user.full_name || data.user.name || '',
          phone: data.user.phone || '',
          department: data.user.department || '',
          sub_role: data.user.sub_role || '',
        })
      }
    } catch {}
    finally { setLoading(false) }
  }

  const handleSave = async () => {
    if (!form.full_name.trim()) { toast.error('Name is required'); return }
    setSaving(true)
    try {
      const data = await updateProfile(form)
      if (data.success) {
        setProfile(data.user)
        setUser({ ...auth.user, ...data.user, name: data.user.full_name || data.user.name })
        toast.success('Profile updated')
      } else {
        toast.error(data.error || 'Failed to update')
      }
    } catch { toast.error('Failed to update profile') }
    finally { setSaving(false) }
  }

  const handleAvatarUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.size > 5 * 1024 * 1024) { toast.error('Max 5 MB'); return }
    setUploading(true)
    try {
      const data = await uploadAvatar(file)
      if (data.success) {
        setProfile(prev => ({ ...prev, profile_picture: data.url?.split('/').pop() }))
        setUser({ ...auth.user, profile_picture: data.url?.split('/').pop() })
        toast.success('Avatar updated')
      } else {
        toast.error(data.error || 'Upload failed')
      }
    } catch { toast.error('Upload failed') }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = '' }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    )
  }

  const initials = profile?.avatar_initials || profile?.name?.charAt(0)?.toUpperCase() || 'U'
  const avatarUrl = profile?.profile_picture ? `/api/uploads/${profile.profile_picture}` : null
  const roleCls = ROLE_COLORS[profile?.role] || ROLE_COLORS.employee
  const memberSince = profile?.created_at
    ? (() => { try { const d = new Date(profile.created_at); return format(d, 'MMMM yyyy') } catch { return '' } })()
    : ''

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* Profile Header Card */}
      <div className={cn('rounded-2xl border p-6 shadow-card', dark ? 'border-navy-700 bg-navy-800' : 'border-gray-200 bg-white')}>
        <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
          {/* Avatar */}
          <div className="relative group">
            <div className={cn(
              'flex h-24 w-24 items-center justify-center rounded-full text-2xl font-bold shadow-md overflow-hidden',
              avatarUrl ? '' : 'bg-gradient-to-br from-brand-dark to-brand-mid text-white'
            )}>
              {avatarUrl
                ? <img src={avatarUrl} alt="Avatar" className="h-full w-full object-cover" />
                : initials
              }
            </div>
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40 text-white opacity-0 group-hover:opacity-100 transition-opacity"
            >
              {uploading ? <Loader2 size={20} className="animate-spin" /> : <Camera size={20} />}
            </button>
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleAvatarUpload} />
          </div>

          {/* Info */}
          <div className="flex-1 text-center sm:text-left">
            <h2 className={cn('text-xl font-bold', dark ? 'text-brand-light' : 'text-gray-900')}>
              {profile?.full_name || profile?.name}
            </h2>
            <p className={cn('text-sm', dark ? 'text-brand-muted' : 'text-gray-500')}>@{profile?.username}</p>
            <div className="mt-2 flex flex-wrap items-center justify-center gap-2 sm:justify-start">
              <span className={cn('rounded-full border px-2.5 py-0.5 text-xs font-semibold', roleCls)}>
                {ROLE_LABELS[profile?.role] || profile?.role}
              </span>
              {profile?.sub_role && (
                <span className={cn('rounded-full border px-2.5 py-0.5 text-xs font-medium',
                  dark ? 'border-navy-600 text-brand-muted' : 'border-gray-200 text-gray-500')}>
                  {profile.sub_role}
                </span>
              )}
              {memberSince && (
                <span className={cn('flex items-center gap-1 text-xs', dark ? 'text-navy-400' : 'text-gray-400')}>
                  <Calendar size={11} /> Joined {memberSince}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Edit Form Card */}
      <div className={cn('rounded-2xl border p-6 shadow-card', dark ? 'border-navy-700 bg-navy-800' : 'border-gray-200 bg-white')}>
        <h3 className={cn('text-sm font-semibold mb-4', dark ? 'text-brand-light' : 'text-gray-900')}>
          Edit Profile
        </h3>
        <div className="space-y-4">
          <Field icon={User} label="Full Name" value={form.full_name} onChange={v => setForm(f => ({ ...f, full_name: v }))} dark={dark} />
          <Field icon={Mail} label="Email" value={profile?.email || ''} readOnly dark={dark} />
          <Field icon={Shield} label="Username" value={profile?.username || ''} readOnly dark={dark} />
          <Field icon={Phone} label="Phone" value={form.phone} onChange={v => setForm(f => ({ ...f, phone: v }))} placeholder="+91 98765 43210" dark={dark} />
          <Field icon={Building} label="Department" value={form.department} onChange={v => setForm(f => ({ ...f, department: v }))} placeholder="e.g. Engineering, Sales" dark={dark} />
          <Field icon={Briefcase} label="Designation" value={form.sub_role} onChange={v => setForm(f => ({ ...f, sub_role: v }))} placeholder="e.g. Senior Developer, Team Lead" dark={dark} />

          <button
            onClick={handleSave}
            disabled={saving}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-dark to-brand-mid py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:opacity-90 disabled:opacity-50 sm:w-auto sm:px-8"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            Save Changes
          </button>
        </div>
      </div>
    </div>
  )
}

function Field({ icon: Icon, label, value, onChange, readOnly, placeholder, dark }) {
  return (
    <div>
      <label className={cn('mb-1 flex items-center gap-1.5 text-xs font-medium', dark ? 'text-brand-muted' : 'text-gray-500')}>
        <Icon size={12} /> {label}
      </label>
      <input
        type="text"
        value={value}
        onChange={onChange ? e => onChange(e.target.value) : undefined}
        readOnly={readOnly}
        placeholder={placeholder}
        className={cn(
          'w-full rounded-lg border px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-brand-cyan/20 focus:border-brand-cyan',
          readOnly && (dark ? 'bg-navy-900 text-brand-muted cursor-not-allowed' : 'bg-gray-50 text-gray-400 cursor-not-allowed'),
          dark ? 'border-navy-600 bg-navy-900 text-brand-light' : 'border-gray-200 bg-white text-gray-900'
        )}
      />
    </div>
  )
}
