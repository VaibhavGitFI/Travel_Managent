import client from './client'

export const getRequests = async (params) => {
  const { data } = await client.get('/requests', { params })
  return data
}

export const createRequest = async (requestData) => {
  const { data } = await client.post('/requests', requestData)
  return data
}

export const getRequest = async (id) => {
  const { data } = await client.get(`/requests/${id}`)
  return data
}

export const updateRequestStatus = async (id, status) => {
  const { data } = await client.put(`/requests/${id}/status`, { status })
  return data
}

export const getTripReport = async (id) => {
  const { data } = await client.get(`/requests/${id}/report`)
  return data
}

export const getPerDiem = async (city, days) => {
  const { data } = await client.get('/requests/per-diem', { params: { city, days } })
  return data
}

export const getBudgetForecast = async (params) => {
  const { data } = await client.post('/requests/budget-forecast', params)
  return data
}
