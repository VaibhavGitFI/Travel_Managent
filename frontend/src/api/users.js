import client from './client'

export const getUsers = async (params = {}) => {
  const { data } = await client.get('/users', { params })
  return data
}

export const getUser = async (userId) => {
  const { data } = await client.get(`/users/${userId}`)
  return data
}

export const updateUserRole = async (userId, role) => {
  const { data } = await client.put(`/users/${userId}/role`, { role })
  return data
}
