import client from './client'

export const getPlatformStats = () =>
  client.get('/admin/stats').then(r => r.data)

export const getAllOrgs = (params = {}) =>
  client.get('/admin/orgs', { params }).then(r => r.data)

export const getOrgDetail = (orgId) =>
  client.get(`/admin/orgs/${orgId}`).then(r => r.data)

export const updateOrg = (orgId, data) =>
  client.put(`/admin/orgs/${orgId}`, data).then(r => r.data)

export const activateOrg = (orgId) =>
  client.post(`/admin/orgs/${orgId}/activate`).then(r => r.data)

export const deactivateOrg = (orgId) =>
  client.post(`/admin/orgs/${orgId}/deactivate`).then(r => r.data)

export const suspendOrg = (orgId) =>
  client.post(`/admin/orgs/${orgId}/suspend`).then(r => r.data)

export const getPlans = () =>
  client.get('/admin/plans').then(r => r.data)
