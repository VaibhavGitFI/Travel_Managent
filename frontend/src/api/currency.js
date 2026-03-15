import client from './client'

export const convertCurrency = async (amount, from, to) => {
  const { data } = await client.post('/currency/convert', {
    amount,
    from_currency: from,
    to_currency: to,
  })
  return data
}

export const getTravelInfo = async (destination) => {
  const { data } = await client.get('/currency/travel-info', {
    params: { destination },
  })
  return data
}
