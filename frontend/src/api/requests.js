import client from './client'

export const getRequests = async () => {
  const { data } = await client.get('/requests')
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
