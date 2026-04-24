import client from './client'
import type { AuthUser } from '../store/authStore'

export type AuthResponse = {
  access_token: string
  token_type: string
  user: AuthUser
}

export const authApi = {
  register: (email: string, password: string, full_name?: string) =>
    client.post<AuthResponse>('/auth/register', { email, password, full_name }).then(r => r.data),

  login: (email: string, password: string) =>
    client.post<AuthResponse>('/auth/login', { email, password }).then(r => r.data),

  me: () =>
    client.get<AuthUser>('/auth/me').then(r => r.data),
}
