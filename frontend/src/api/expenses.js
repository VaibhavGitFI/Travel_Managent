import client from './client'

export const getExpenses = async (tripIdOrParams) => {
  const params = typeof tripIdOrParams === 'object' && tripIdOrParams !== null
    ? tripIdOrParams
    : tripIdOrParams ? { trip_id: tripIdOrParams } : {}
  const { data } = await client.get('/expenses', { params })
  return data
}

export const submitExpense = async (expenseData) => {
  const { data } = await client.post('/expenses', expenseData)
  return data
}

export const getExpenseSummary = async (tripId) => {
  const params = tripId ? { trip_id: tripId } : {}
  const { data } = await client.get('/expenses/summary', { params })
  return data
}

export const uploadAndExtract = async (formData) => {
  const { data } = await client.post('/expense/upload-and-extract', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export const getExpenseAnomalies = async () => {
  const { data } = await client.get('/expenses/anomalies')
  return data
}

// ── Expense Approval Workflow ─────────────────────────────────────────────────

export const submitExpenseForApproval = async (expenseId) => {
  const { data } = await client.post(`/expenses/${expenseId}/submit`)
  return data
}

export const approveExpense = async (expenseId, comments = '') => {
  const { data } = await client.post(`/expenses/${expenseId}/approve`, { comments })
  return data
}

export const rejectExpense = async (expenseId, reason) => {
  const { data } = await client.post(`/expenses/${expenseId}/reject`, { reason })
  return data
}

export const getPendingExpenseApprovals = async () => {
  const { data } = await client.get('/expenses/pending-approvals')
  return data
}
