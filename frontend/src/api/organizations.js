import client from './client'

export const createOrganization = (data) =>
  client.post('/orgs', data).then((r) => r.data)

export const getMyOrganization = () =>
  client.get('/orgs/me').then((r) => r.data)

export const updateOrgSettings = (data) =>
  client.put('/orgs/settings', data).then((r) => r.data)

export const getOrgMembers = () =>
  client.get('/orgs/members').then((r) => r.data)

export const inviteMember = (data) =>
  client.post('/orgs/invite', data).then((r) => r.data)

export const updateMemberRole = (userId, role) =>
  client.put(`/orgs/members/${userId}/role`, { role }).then((r) => r.data)

export const removeMember = (userId) =>
  client.delete(`/orgs/members/${userId}`).then((r) => r.data)
