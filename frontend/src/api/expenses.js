import client from './client'

export const getExpenses = async (tripId) => {
  const params = tripId ? { trip_id: tripId } : {}
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
