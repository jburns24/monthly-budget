export interface FamilyBrief {
  id: string
  name: string
  role: 'admin' | 'member'
}

export interface FamilyMember {
  user_id: string
  family_id: string
  email: string
  display_name: string
  avatar_url: string | null
  role: 'admin' | 'member'
  joined_at: string
}

export interface Family {
  id: string
  name: string
  timezone: string
  created_by: string
  created_at: string
  members: FamilyMember[]
}

export interface InviteResponse {
  id: string
  family_id: string
  family_name: string
  invited_by_display_name: string
  status: 'pending' | 'accepted' | 'declined'
  created_at: string
  responded_at: string | null
}

export interface FamilyCreate {
  name: string
  timezone: string
}

export interface GenericMessage {
  message: string
}
