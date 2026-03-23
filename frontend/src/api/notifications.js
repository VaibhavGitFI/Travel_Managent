import client from './client'

export async function getNotifications(limit = 30) {
  const { data } = await client.get('/notifications', { params: { limit } })
  return data
}

export async function markNotificationRead(id) {
  const { data } = await client.post(`/notifications/${id}/read`)
  return data
}

export async function markAllNotificationsRead() {
  const { data } = await client.post('/notifications/read-all')
  return data
}
