import client from './client'

export const getProfile = async () => {
  const { data } = await client.get('/auth/profile')
  return data
}

export const updateProfile = async (fields) => {
  const { data } = await client.put('/auth/profile', fields)
  return data
}

export const uploadAvatar = async (file) => {
  const formData = new FormData()
  formData.append('avatar', file)
  const { data } = await client.post('/auth/profile/avatar', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}
