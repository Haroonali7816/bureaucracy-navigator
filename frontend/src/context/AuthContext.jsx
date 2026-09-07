import { createContext, useContext, useState } from 'react'
import client from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('token'))

  async function login(email, password) {
    const form = new URLSearchParams()
    form.append('username', email)
    form.append('password', password)
    const response = await client.post('/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    localStorage.setItem('token', response.data.access_token)
    setToken(response.data.access_token)
  }

  async function signup(email, password) {
    const response = await client.post('/auth/signup', { email, password })
    localStorage.setItem('token', response.data.access_token)
    setToken(response.data.access_token)
  }

  function logout() {
    localStorage.removeItem('token')
    setToken(null)
  }

  const value = { token, isAuthenticated: !!token, login, signup, logout }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components -- context + its hook are meant to live together
export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
