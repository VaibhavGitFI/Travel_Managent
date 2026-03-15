import client from './client'

export const getDashboardStats = async () => {
  const { data } = await client.get('/analytics/dashboard')
  return data
}

export const getSpendAnalysis = async () => {
  const { data } = await client.get('/analytics/spend')
  return data
}

export const getComplianceScorecard = async () => {
  const { data } = await client.get('/analytics/compliance')
  return data
}
