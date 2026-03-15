import client from './client'

export const getMeetings = async (tripId) => {
  const params = tripId ? { trip_id: tripId } : {}
  const { data } = await client.get('/meetings', { params })
  return data
}

export const createMeeting = async (meetingData) => {
  const { data } = await client.post('/meetings', meetingData)
  return data
}

export const updateMeeting = async (id, meetingData) => {
  const { data } = await client.put(`/meetings/${id}`, meetingData)
  return data
}

export const deleteMeeting = async (id) => {
  const { data } = await client.delete(`/meetings/${id}`)
  return data
}

export const suggestSchedule = async (scheduleData) => {
  const { data } = await client.post('/meetings/suggest-schedule', scheduleData)
  return data
}

export const getNearbyVenues = async (venueData) => {
  const { data } = await client.post('/meetings/nearby-venues', venueData)
  return data
}
