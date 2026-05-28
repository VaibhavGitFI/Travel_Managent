import client from './client'

export const triggerSOS = async ({ city = '', message = '', latitude, longitude, emergency_type = 'general', country = '' } = {}) => {
  const { data } = await client.post('/sos', { city, message, latitude, longitude, emergency_type, country })
  return data
}

export const getEmergencyContacts = async ({ city = '', country = '', lat, lng } = {}) => {
  const params = {}
  if (city) params.city = city
  if (country) params.country = country
  if (lat) params.lat = lat
  if (lng) params.lng = lng
  const { data } = await client.get('/sos/contacts', { params })
  return data
}

export const reverseGeocode = async (latitude, longitude) => {
  const { data } = await client.post('/sos/reverse-geocode', { latitude, longitude })
  return data
}
