import client from './client'

export const planTrip = async (data) => {
  const { data: res } = await client.post('/trips/plan', data)
  return res
}

export const getTrips = async () => {
  const { data } = await client.get('/trips')
  return data
}

export const getTrip = async (id) => {
  const { data } = await client.get(`/trips/${id}`)
  return data
}
