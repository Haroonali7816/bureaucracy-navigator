import { Routes, Route, Navigate, Link, useNavigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Signup from './pages/Signup'
import Dashboard from './pages/Dashboard'
import UploadPage from './pages/Upload'
import LetterDetail from './pages/LetterDetail'
import PriorityQueue from './pages/PriorityQueue'
import './App.css'

function NavBar() {
  const { isAuthenticated, logout } = useAuth()
  const navigate = useNavigate()

  if (!isAuthenticated) return null

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <nav className="navbar">
      <span className="brand">
        <span className="brand-mark">AZ</span>
        Bureaucracy Navigator
      </span>
      <div className="nav-links">
        <Link to="/">Dashboard</Link>
        <Link to="/upload">Upload</Link>
        <Link to="/priorities">Priority Queue</Link>
      </div>
      <button className="btn-ghost" onClick={handleLogout}>
        Log out
      </button>
    </nav>
  )
}

function App() {
  return (
    <>
      <NavBar />
      <main className="page">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/upload"
            element={
              <ProtectedRoute>
                <UploadPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/letters/:letterId"
            element={
              <ProtectedRoute>
                <LetterDetail />
              </ProtectedRoute>
            }
          />
          <Route
            path="/priorities"
            element={
              <ProtectedRoute>
                <PriorityQueue />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  )
}

export default App
