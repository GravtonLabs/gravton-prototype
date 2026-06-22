const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ''

export async function login(username: string, password: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) throw new Error('invalid credentials')
  const { token } = await res.json()
  localStorage.setItem('cs_token', token)
  localStorage.setItem('cs_username', username)
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('cs_token')
}

export function getUsername(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('cs_username')
}

export function logout(): void {
  localStorage.removeItem('cs_token')
  localStorage.removeItem('cs_username')
}
