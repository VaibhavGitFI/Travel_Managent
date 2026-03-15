import { useState, useEffect, useRef, useMemo } from 'react'
import {
  Receipt, Upload, IndianRupee, CheckCircle,
  FileText, Camera, Clock3, Wallet, Mail, Images, Hand, MoreVertical, Printer,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { getExpenses, submitExpense, uploadAndExtract } from '../api/expenses'
import useStore from '../store/useStore'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import Select from '../components/ui/Select'
import Badge from '../components/ui/Badge'
import Modal from '../components/ui/Modal'
import Spinner from '../components/ui/Spinner'

const categories = [
  { value: 'flight',        label: 'Flight' },
  { value: 'hotel',         label: 'Hotel' },
  { value: 'food',          label: 'Food & Meals' },
  { value: 'transport',     label: 'Local Transport' },
  { value: 'visa',          label: 'Visa / Docs' },
  { value: 'communication', label: 'Communication' },
  { value: 'other',         label: 'Other' },
]

const emptyForm = {
  amount: '',
  category: '',
  description: '',
  expense_date: '',
  vendor: '',
  trip_id: '',
  gst_amount: '',
}

const categoryLabelMap = categories.reduce((acc, item) => {
  acc[item.value] = item.label
  return acc
}, {})

const sortOptions = [
  { value: 'latest', label: 'Latest' },
  { value: 'oldest', label: 'Oldest' },
  { value: 'highest', label: 'Amount: High to Low' },
  { value: 'lowest', label: 'Amount: Low to High' },
]

const pendingStatuses = new Set(['pending', 'submitted', 'in-progress', 'review'])

const formatCurrency = (value) =>
  `₹${Number(value || 0).toLocaleString('en-IN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })}`

const formatDate = (value) => {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

const toTitleCase = (value = '') =>
  String(value)
    .replace(/[-_]/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())

export default function Expenses() {
  const [expenses, setExpenses] = useState([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(false)
  const [form, setForm] = useState(emptyForm)
  const [submitting, setSubmitting] = useState(false)
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrData, setOcrData] = useState(null)
  const [errors, setErrors] = useState({})
  const [sortBy, setSortBy] = useState('latest')

  const fileRef = useRef(null)
  const user = useStore((s) => s.auth.user)
  const firstName = user?.name?.split(' ')[0] || 'Traveler'

  const panelClass = 'rounded-xl border border-[#d2dae4] bg-white shadow-[0_12px_24px_rgba(27,38,59,0.08)]'
  const fieldClass =
    '!rounded-xl !border-[#d7e1ec] !bg-[#f8fbff] !text-[#1B263B] placeholder:!text-[#8c9bae] focus:!border-[#4CC9F0] focus:!ring-2 focus:!ring-[#4CC9F0]/20'

  useEffect(() => {
    fetchExpenses()
  }, [])

  const fetchExpenses = async () => {
    try {
      const data = await getExpenses()
      setExpenses(Array.isArray(data) ? data : data.expenses || [])
    } catch (err) {
      toast.error(err?.response?.data?.error || 'Failed to load expenses')
    } finally {
      setLoading(false)
    }
  }

  const closeModal = () => {
    setModal(false)
    setForm(emptyForm)
    setErrors({})
    setOcrData(null)
  }

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }))

  const handleOcrUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setOcrLoading(true)
    setOcrData(null)

    try {
      const fd = new FormData()
      fd.append('receipt', file)
      const data = await uploadAndExtract(fd)
      setOcrData(data)

      if (data.amount) set('amount', String(data.amount))
      if (data.vendor) set('vendor', data.vendor)
      if (data.date) set('expense_date', data.date)
      if (data.gst) set('gst_amount', String(data.gst))

      toast.success('Receipt scanned! Data extracted.')
    } catch (err) {
      toast.error(err?.response?.data?.error || 'OCR failed. Please enter details manually.')
    } finally {
      setOcrLoading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const validate = () => {
    const e = {}
    if (!form.amount || isNaN(form.amount)) e.amount = 'Valid amount required'
    if (!form.category) e.category = 'Select category'
    if (!form.description.trim()) e.description = 'Description required'
    if (!form.expense_date) e.expense_date = 'Date required'
    return e
  }

  const handleSubmit = async () => {
    const errs = validate()
    if (Object.keys(errs).length) {
      setErrors(errs)
      return
    }

    setErrors({})
    setSubmitting(true)
    try {
      await submitExpense({
        ...form,
        amount: parseFloat(form.amount),
        gst_amount: form.gst_amount ? parseFloat(form.gst_amount) : undefined,
      })
      toast.success('Expense submitted!')
      closeModal()
      fetchExpenses()
    } catch (err) {
      toast.error(err?.response?.data?.error || 'Submission failed')
    } finally {
      setSubmitting(false)
    }
  }

  const normalizedExpenses = useMemo(() => (
    expenses.map((expense) => {
      const status = String(expense.status || 'pending')
        .toLowerCase()
        .replace(/_/g, '-')
      const category = String(expense.category || 'other').toLowerCase()
      const dateValue = expense.expense_date || expense.date || ''
      const amount = Number(expense.amount || 0)

      return {
        ...expense,
        status,
        category,
        dateValue,
        amount,
      }
    })
  ), [expenses])

  const summary = useMemo(() => {
    const totalAmount = normalizedExpenses.reduce((sum, item) => sum + item.amount, 0)
    const approvedAmount = normalizedExpenses
      .filter((item) => item.status === 'approved')
      .reduce((sum, item) => sum + item.amount, 0)
    const pendingAmount = normalizedExpenses
      .filter((item) => pendingStatuses.has(item.status))
      .reduce((sum, item) => sum + item.amount, 0)
    const otherAmount = Math.max(totalAmount - approvedAmount - pendingAmount, 0)
    const approvedCount = normalizedExpenses.filter((item) => item.status === 'approved').length
    const pendingCount = normalizedExpenses.filter((item) => pendingStatuses.has(item.status)).length
    const averageAmount = normalizedExpenses.length
      ? totalAmount / normalizedExpenses.length
      : 0

    return {
      totalAmount,
      approvedAmount,
      pendingAmount,
      otherAmount,
      approvedCount,
      pendingCount,
      averageAmount,
    }
  }, [normalizedExpenses])

  const topCategories = useMemo(() => {
    const totals = normalizedExpenses.reduce((acc, item) => {
      if (!acc[item.category]) {
        acc[item.category] = { amount: 0, count: 0 }
      }
      acc[item.category].amount += item.amount
      acc[item.category].count += 1
      return acc
    }, {})

    return Object.entries(totals)
      .map(([key, value]) => ({
        key,
        label: categoryLabelMap[key] || toTitleCase(key),
        amount: value.amount,
        count: value.count,
      }))
      .sort((a, b) => b.amount - a.amount)
      .slice(0, 3)
  }, [normalizedExpenses])

  const filteredExpenses = useMemo(() => {
    return [...normalizedExpenses].sort((a, b) => {
      if (sortBy === 'highest') return b.amount - a.amount
      if (sortBy === 'lowest') return a.amount - b.amount

      if (sortBy === 'oldest') {
        const aTime = new Date(a.dateValue).getTime()
        const bTime = new Date(b.dateValue).getTime()
        const safeATime = Number.isFinite(aTime) ? aTime : 0
        const safeBTime = Number.isFinite(bTime) ? bTime : 0
        return safeATime - safeBTime
      }

      const aTime = new Date(a.dateValue).getTime()
      const bTime = new Date(b.dateValue).getTime()
      const safeATime = Number.isFinite(aTime) ? aTime : 0
      const safeBTime = Number.isFinite(bTime) ? bTime : 0
        return safeBTime - safeATime
    })
  }, [normalizedExpenses, sortBy])

  const categoryCards = topCategories.length
    ? topCategories
    : categories.slice(0, 3).map((item) => ({
      key: item.value,
      label: item.label,
      amount: 0,
      count: 0,
    }))

  const budgetCards = useMemo(() => (
    categoryCards.map((card) => {
      const projectedBudget = card.amount > 0
        ? Math.max(card.amount * 1.35, summary.averageAmount * 1.75)
        : 0
      const total = projectedBudget > 0 ? Number(projectedBudget.toFixed(2)) : 0
      const remaining = Math.max(total - card.amount, 0)

      return {
        ...card,
        total,
        spent: card.amount,
        remaining,
        utilization: total > 0 ? Math.round((card.amount / total) * 100) : 0,
      }
    })
  ), [categoryCards, summary.averageAmount])

  const handleExportCsv = () => {
    const csvEscape = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`
    const headers = ['Date', 'Category', 'Description', 'Vendor', 'Amount', 'Status']
    const rows = filteredExpenses.map((expense) => ([
      formatDate(expense.dateValue),
      categoryLabelMap[expense.category] || toTitleCase(expense.category),
      expense.description || '',
      expense.vendor || '',
      String(expense.amount || 0),
      toTitleCase(expense.status || 'pending'),
    ]))

    const csv = [headers, ...rows]
      .map((row) => row.map(csvEscape).join(','))
      .join('\n')

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'expenses.csv'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const handlePrint = () => {
    window.print()
  }

  return (
    <div className="mx-auto w-full max-w-[1400px] space-y-4 rounded-3xl border border-[#cdd6e0] bg-[radial-gradient(circle_at_top_left,#f6f9fc_0%,transparent_38%),linear-gradient(180deg,#edf1f5_0%,#E0E1DD_100%)] px-3 pb-6 pt-4 sm:space-y-5 sm:px-5 md:px-6 md:pb-8 lg:space-y-6">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[360px,minmax(0,1fr)] xl:gap-6">
        <section className="space-y-4">
          <div className={`${panelClass} p-5 sm:p-6`}>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#4CC9F0]">
              Expense tracker
            </p>
            <h2 className="mt-1 font-heading text-2xl font-semibold text-[#1B263B] sm:text-[30px]">
              Hello {firstName},
            </h2>
            <p className="mt-1 text-sm text-[#61758c]">
              Take a look at your current balance.
            </p>

            <div className="mt-5">
              <InlineLegend color="#4CC9F0" label="Approved" value={formatCurrency(summary.approvedAmount)} />
            </div>

            <div className="mt-2">
              <ExpenseDonut
                total={summary.totalAmount}
                approved={summary.approvedAmount}
                pending={summary.pendingAmount}
                other={summary.otherAmount}
                size={220}
                strokeWidth={18}
              />
            </div>

            <div className="mt-2 flex justify-end">
              <InlineLegend color="#f4b400" label="Pending" value={formatCurrency(summary.pendingAmount)} />
            </div>

            <div className="mt-4 grid grid-cols-3 gap-2">
              <MetricChip icon={Wallet} label="Average" value={formatCurrency(summary.averageAmount)} />
              <MetricChip icon={Clock3} label="Pending" value={String(summary.pendingCount)} />
              <MetricChip icon={CheckCircle} label="Approved" value={String(summary.approvedCount)} />
            </div>
          </div>

          <div className={`${panelClass} p-4 sm:p-5`}>
            <h3 className="font-heading text-base font-semibold text-[#1B263B]">Add a New Expense</h3>
            <div className="mt-4 grid grid-cols-3 gap-2 sm:gap-3">
              <ActionTile icon={Mail} title="Email" onClick={() => setModal(true)} />
              <ActionTile icon={Images} title="Library" onClick={() => setModal(true)} />
              <ActionTile icon={Hand} title="Manually" onClick={() => setModal(true)} />
            </div>
          </div>
        </section>

        <section className="space-y-4">
          <div>
            <p className="px-1 text-lg font-semibold text-[#677b91]">Your Current Budgets</p>
            <div className="mt-2 grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-3">
              {budgetCards.map((card) => (
                <BudgetOverviewCard
                  key={card.key}
                  title={card.label}
                  spent={card.spent}
                  remaining={card.remaining}
                  total={card.total}
                  entries={card.count}
                  panelClass={panelClass}
                />
              ))}
            </div>
          </div>

          <div className={`${panelClass} overflow-hidden`}>
            <div className="flex flex-col gap-3 border-b border-[#d7dee7] px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
              <div>
                <h3 className="font-heading text-base font-semibold text-[#1B263B]">Your Expenses</h3>
                <p className="mt-0.5 text-xs text-[#778DA9]">
                  {filteredExpenses.length} entries shown
                </p>
              </div>

              <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:justify-end">
                <IconActionButton
                  icon={FileText}
                  label="Export"
                  onClick={handleExportCsv}
                />
                <IconActionButton
                  icon={Printer}
                  label="Print"
                  onClick={handlePrint}
                />
                <Select
                  id="expense-sort"
                  aria-label="Sort expenses"
                  options={sortOptions}
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="w-full sm:w-[180px]"
                  selectClassName={fieldClass}
                />
              </div>
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-14">
                <Spinner size="md" color="accent" />
              </div>
            ) : normalizedExpenses.length === 0 ? (
              <div className="py-16 text-center">
                <Receipt size={34} className="mx-auto mb-3 text-[#9ab2c9]" />
                <p className="font-medium text-[#44566f]">No expenses found</p>
                <p className="mt-1 text-sm text-[#778DA9]">Submit your first expense to start tracking.</p>
                <Button
                  size="sm"
                  className="mt-4 border border-[#4CC9F0] bg-[#4CC9F0] text-[#1B263B] hover:bg-[#35bee9]"
                  onClick={() => setModal(true)}
                >
                  Submit your first expense
                </Button>
              </div>
            ) : (
              <>
                <div className="divide-y divide-[#e6edf4] md:hidden">
                  {filteredExpenses.map((expense) => (
                    <MobileExpenseRow key={expense.id} expense={expense} />
                  ))}
                </div>

                <div className="hidden overflow-x-auto md:block">
                  <table className="w-full table-row-hover">
                    <thead className="bg-[#f3f7fb]">
                      <tr>
                        {['Company', 'Budget', 'Date', 'Amount', 'Status'].map((header) => (
                          <th
                            key={header}
                            className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#6c7f93]"
                          >
                            {header}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#edf2f7]">
                      {filteredExpenses.map((expense) => (
                        <tr key={expense.id}>
                          <td className="px-6 py-4 text-sm text-[#1f2f46]">
                            <div className="flex items-center gap-2">
                              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#f3f7fb] text-[#8194aa]">
                                <Receipt size={14} />
                              </span>
                              <span className="max-w-[16rem] truncate">
                                {expense.vendor || expense.description || 'Expense entry'}
                              </span>
                            </div>
                          </td>
                          <td className="px-6 py-4 text-sm text-[#5f7287]">
                            {categoryLabelMap[expense.category] || toTitleCase(expense.category)}
                          </td>
                          <td className="px-6 py-4 text-sm text-[#5f7287]">{formatDate(expense.dateValue)}</td>
                          <td className="px-6 py-4 text-sm font-semibold text-[#1B263B]">
                            {formatCurrency(expense.amount)}
                          </td>
                          <td className="px-6 py-4">
                            <Badge status={expense.status} dot>{toTitleCase(expense.status || 'pending')}</Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        </section>
      </div>

      <Modal
        open={modal}
        onClose={closeModal}
        title="Submit Expense"
        subtitle="Fill in the details or scan your receipt"
        width="lg"
        footer={(
          <>
            <Button variant="secondary" onClick={closeModal}>Cancel</Button>
            <Button
              loading={submitting}
              leftIcon={<FileText size={15} />}
              className="border border-[#4CC9F0] bg-[#4CC9F0] text-[#1B263B] hover:bg-[#35bee9]"
              onClick={handleSubmit}
            >
              Submit Expense
            </Button>
          </>
        )}
      >
        <div className="space-y-5">
          <div
            className="cursor-pointer rounded-xl border-2 border-dashed border-[#d0deea] bg-[#f8fbff] p-5 text-center transition-colors hover:border-[#4CC9F0] hover:bg-[#f1f9fe]"
            onClick={() => fileRef.current?.click()}
          >
            <input
              ref={fileRef}
              type="file"
              accept="image/*,.pdf"
              className="hidden"
              onChange={handleOcrUpload}
            />
            {ocrLoading ? (
              <div className="flex items-center justify-center gap-2">
                <Spinner size="sm" color="accent" />
                <span className="text-sm text-[#5f7287]">Scanning receipt…</span>
              </div>
            ) : (
              <div>
                <Upload size={20} className="mx-auto mb-2 text-[#7b8ea5]" />
                <p className="text-sm font-medium text-[#30455f]">Upload receipt for auto-scan</p>
                <p className="mt-0.5 text-xs text-[#7b8ea5]">Click to upload image or PDF</p>
              </div>
            )}
          </div>

          {ocrData && (
            <div className="flex items-start gap-3 rounded-lg border border-success-100 bg-success-50 p-3">
              <CheckCircle size={16} className="mt-0.5 shrink-0 text-success-600" />
              <div className="text-sm text-success-700">
                <strong>Receipt scanned</strong> — amount, vendor, and date have been auto-filled.
                Please review and correct if needed.
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="Amount (₹)"
              type="number"
              step="0.01"
              placeholder="0.00"
              value={form.amount}
              onChange={(e) => set('amount', e.target.value)}
              error={errors.amount}
              leftIcon={<IndianRupee size={16} />}
              size="lg"
              inputClassName={fieldClass}
              required
            />
            <Select
              label="Category"
              options={categories}
              placeholder="Select category"
              value={form.category}
              onChange={(e) => set('category', e.target.value)}
              error={errors.category}
              size="lg"
              selectClassName={fieldClass}
              required
            />
          </div>

          <Input
            label="Description"
            placeholder="Brief description of the expense"
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
            error={errors.description}
            size="lg"
            inputClassName={fieldClass}
            required
          />

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="Vendor / Merchant"
              placeholder="e.g. MakeMyTrip"
              value={form.vendor}
              onChange={(e) => set('vendor', e.target.value)}
              size="lg"
              inputClassName={fieldClass}
            />
            <Input
              label="Expense Date"
              type="date"
              value={form.expense_date}
              onChange={(e) => set('expense_date', e.target.value)}
              error={errors.expense_date}
              size="lg"
              inputClassName={fieldClass}
              required
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="GST Amount (₹)"
              type="number"
              step="0.01"
              placeholder="Optional"
              value={form.gst_amount}
              onChange={(e) => set('gst_amount', e.target.value)}
              hint="Auto-detected from receipt when available"
              size="lg"
              inputClassName={fieldClass}
            />
            <Input
              label="Trip ID"
              placeholder="Optional — link to a trip"
              value={form.trip_id}
              onChange={(e) => set('trip_id', e.target.value)}
              size="lg"
              inputClassName={fieldClass}
            />
          </div>
        </div>
      </Modal>
    </div>
  )
}

function InlineLegend({ color, label, value }) {
  return (
    <div className="inline-flex items-center gap-2.5">
      <span className="h-2.5 w-5 rounded-full" style={{ backgroundColor: color }} />
      <div>
        <p className="text-xs text-[#7f93a8]">{label}</p>
        <p className="text-xl font-semibold text-[#1B263B]">{value}</p>
      </div>
    </div>
  )
}

function ExpenseDonut({ total, approved, pending, other, size = 144, strokeWidth = 10 }) {
  const isLarge = size >= 200
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const safeTotal = total > 0 ? total : 1

  const segments = [
    { color: '#4CC9F0', length: (Math.max(approved, 0) / safeTotal) * circumference },
    { color: '#f4b400', length: (Math.max(pending, 0) / safeTotal) * circumference },
    { color: '#9fb0c5', length: (Math.max(other, 0) / safeTotal) * circumference },
  ].filter((segment) => segment.length > 0.001)

  let consumed = 0

  return (
    <div className="relative mx-auto" style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} className="h-full w-full -rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#e4edf5"
          strokeWidth={strokeWidth}
        />
        {segments.map((segment, index) => {
          const start = consumed
          consumed += segment.length

          return (
            <circle
              key={index}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={segment.color}
              strokeWidth={strokeWidth}
              strokeLinecap="round"
              strokeDasharray={`${segment.length} ${circumference - segment.length}`}
              strokeDashoffset={-start}
            />
          )
        })}
      </svg>

      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <p className={`font-medium text-[#8092a6] ${isLarge ? 'text-sm' : 'text-xs'}`}>Total</p>
        <p className={`mt-0.5 font-heading font-semibold text-[#1B263B] ${isLarge ? 'text-[30px]' : 'text-[18px]'}`}>
          {formatCurrency(total)}
        </p>
      </div>
    </div>
  )
}

function ActionTile({ icon: Icon, title, subtitle, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group h-full rounded-xl border border-[#d6deea] bg-[#eef1fd] p-3 text-center transition-colors hover:border-[#4CC9F0]/70 hover:bg-[#e8f5fc]"
    >
      <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-white text-[#2f4f72]">
        <Icon size={17} />
      </div>
      <p className="text-base font-semibold text-[#355a84]">{title}</p>
      {subtitle ? <p className="mt-0.5 text-xs text-[#73869b]">{subtitle}</p> : null}
    </button>
  )
}

function MetricChip({ icon: Icon, label, value }) {
  return (
    <div className="rounded-lg border border-[#dce5ef] bg-[#f9fbfe] px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[#71859b]">
        <Icon size={13} />
        <span className="text-[11px] font-medium">{label}</span>
      </div>
      <p className="mt-1 text-sm font-semibold text-[#1B263B]">{value}</p>
    </div>
  )
}

function BudgetOverviewCard({ title, spent, remaining, total, entries, panelClass }) {
  const utilization = total > 0 ? Math.round((spent / total) * 100) : 0

  return (
    <div className={`${panelClass} p-3.5`}>
      <div className="flex items-center justify-between rounded-lg bg-[#f2f5f9] px-3 py-2">
        <h4 className="truncate pr-2 text-base font-semibold text-[#25374e]">{title}</h4>
        <MoreVertical size={16} className="shrink-0 text-[#7e92a7]" />
      </div>

      <p className="mt-3 font-heading text-2xl font-semibold text-[#1B263B]">{formatCurrency(total)}</p>

      <div className="mt-2 space-y-1.5">
        <BudgetStatRow color="#4CC9F0" label="Spent" value={formatCurrency(spent)} />
        <BudgetStatRow color="#f4b400" label="Remaining" value={formatCurrency(remaining)} />
      </div>

      <div className="mt-2 h-1.5 rounded-full bg-[#e3ecf4]">
        <div
          className="h-full rounded-full bg-[#4CC9F0]"
          style={{ width: `${Math.min(Math.max(utilization, 0), 100)}%` }}
        />
      </div>

      <p className="mt-2 text-xs text-[#7c90a5]">
        {entries} {entries === 1 ? 'entry' : 'entries'} · {utilization}% used
      </p>
    </div>
  )
}

function BudgetStatRow({ color, label, value }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
        <span className="text-sm text-[#62758b]">{label}</span>
      </div>
      <span className="text-sm font-semibold text-[#1B263B]">{value}</span>
    </div>
  )
}

function IconActionButton({ icon: Icon, label, onClick }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#d5e0eb] bg-white text-[#4f6480] transition-colors hover:border-[#4CC9F0]/70 hover:bg-[#edf7fd]"
    >
      <Icon size={17} />
    </button>
  )
}

function MobileExpenseRow({ expense }) {
  return (
    <article className="space-y-3 px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-[#1f3047]">{expense.description || 'Expense entry'}</p>
          <p className="mt-0.5 text-xs text-[#6f8399]">{formatDate(expense.dateValue)}</p>
        </div>
        <p className="shrink-0 text-sm font-semibold text-[#1B263B]">{formatCurrency(expense.amount)}</p>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg border border-[#dfe8f1] bg-[#f8fbff] px-2.5 py-2">
          <p className="text-[#7a8ea4]">Category</p>
          <p className="mt-0.5 font-medium text-[#2e425a]">{categoryLabelMap[expense.category] || toTitleCase(expense.category)}</p>
        </div>
        <div className="rounded-lg border border-[#dfe8f1] bg-[#f8fbff] px-2.5 py-2">
          <p className="text-[#7a8ea4]">Vendor</p>
          <p className="mt-0.5 font-medium text-[#2e425a] truncate">{expense.vendor || '—'}</p>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3">
        <Badge status={expense.status} dot>{toTitleCase(expense.status || 'pending')}</Badge>
        {Number(expense.ocr_confidence) > 0 ? (
          <div className="inline-flex items-center gap-1.5 rounded-full border border-success-100 bg-success-50 px-2 py-1 text-xs font-medium text-success-700">
            <Camera size={12} />
            {Math.round(Number(expense.ocr_confidence) * 100)}% OCR
          </div>
        ) : (
          <span className="text-xs text-[#92a4b7]">No OCR</span>
        )}
      </div>
    </article>
  )
}
