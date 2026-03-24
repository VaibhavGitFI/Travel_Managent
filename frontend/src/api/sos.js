import client from './client'

export const triggerSOS = async (city = '', message = '') => {
  const { data } = await client.post('/sos', { city, message })
  return data
}

export const getEmergencyContacts = async (city = '') => {
  const { data } = await client.get('/sos/contacts', { params: { city } })
  return data
}
