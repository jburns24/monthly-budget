export interface User {
  id: string
  email: string
  display_name: string
  avatar_url: string | null
  timezone: string
}

export interface AuthCallbackResponse {
  is_new_user: boolean
}

export type MeResponse = User

export interface UserUpdate {
  display_name?: string
  timezone?: string
}
