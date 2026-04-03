import { apiClient } from './client'
import type { Family, FamilyMember, GenericMessage, InviteResponse } from '../types/family'

export async function createFamily(name: string, timezone: string): Promise<Family> {
  const response = await apiClient('/api/families', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, timezone }),
  })
  if (!response.ok) {
    throw new Error('Failed to create family')
  }
  return response.json() as Promise<Family>
}

export async function getFamily(familyId: string): Promise<Family> {
  const response = await apiClient(`/api/families/${familyId}`)
  if (!response.ok) {
    throw new Error('Failed to fetch family')
  }
  return response.json() as Promise<Family>
}

export async function sendInvite(familyId: string, email: string): Promise<GenericMessage> {
  const response = await apiClient(`/api/families/${familyId}/invites`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  if (!response.ok) {
    throw new Error('Failed to send invite')
  }
  return response.json() as Promise<GenericMessage>
}

export async function getPendingInvites(): Promise<InviteResponse[]> {
  const response = await apiClient('/api/invites')
  if (!response.ok) {
    throw new Error('Failed to fetch invites')
  }
  return response.json() as Promise<InviteResponse[]>
}

export async function respondToInvite(
  inviteId: string,
  action: 'accept' | 'decline'
): Promise<GenericMessage> {
  const response = await apiClient(`/api/invites/${inviteId}/respond`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  })
  if (!response.ok) {
    throw new Error('Failed to respond to invite')
  }
  return response.json() as Promise<GenericMessage>
}

export async function removeMember(familyId: string, userId: string): Promise<GenericMessage> {
  const response = await apiClient(`/api/families/${familyId}/members/${userId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error('Failed to remove member')
  }
  return response.json() as Promise<GenericMessage>
}

export async function changeRole(
  familyId: string,
  userId: string,
  role: 'admin' | 'member'
): Promise<FamilyMember> {
  const response = await apiClient(`/api/families/${familyId}/members/${userId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  })
  if (!response.ok) {
    throw new Error('Failed to change role')
  }
  return response.json() as Promise<FamilyMember>
}

export async function leaveFamily(familyId: string): Promise<GenericMessage> {
  const response = await apiClient(`/api/families/${familyId}/leave`, {
    method: 'POST',
  })
  if (!response.ok) {
    throw new Error('Failed to leave family')
  }
  return response.json() as Promise<GenericMessage>
}
