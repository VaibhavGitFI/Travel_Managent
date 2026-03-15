import client from './client'

export const getApprovals = async () => {
  const { data } = await client.get('/approvals')
  return data
}

export const approveRequest = async (id) => {
  const { data } = await client.post(`/approvals/${id}/approve`)
  return data
}

export const rejectRequest = async (id, reason) => {
  const { data } = await client.post(`/approvals/${id}/reject`, { reason })
  return data
}
