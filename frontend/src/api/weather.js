import client from './client'

export const getWeatherForecast = async (city, dates) => {
  const { data } = await client.post('/weather', { city, travel_dates: dates })
  return data
}

export const getCurrentWeather = async (city) => {
  const { data } = await client.get('/weather/current', { params: { city } })
  return data
}
