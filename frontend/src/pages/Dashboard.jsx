import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import client from '../api/client'
import StatusPill from '../components/StatusPill'

export default function Dashboard() {
  const [letters, setLetters] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function loadLetters() {
      try {
        const response = await client.get('/letters')
        if (!cancelled) setLetters(response.data)
      } catch (err) {
        console.error(err)
        if (!cancelled) setError('Could not load your letters')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    loadLetters()
    return () => {
      cancelled = true
    }
  }, [])

  if (loading) return <p>Loading letters...</p>
  if (error) return <p className="error">{error}</p>

  return (
    <div>
      <h1>Your letters</h1>
      {letters.length === 0 && <p>No letters yet. Upload one to get started.</p>}
      <ul className="letter-list">
        {letters
          .filter((letter) => letter.job_status !== 'failed')
          .map((letter) => (
          <li key={letter.letter_id}>
            <Link to={`/letters/${letter.letter_id}`}>
              <span className="letter-authority">
                {letter.authority || 'Processing...'}
              </span>
              <span className="letter-type">{letter.letter_type || ''}</span>
              <StatusPill
                jobStatus={letter.job_status}
                needsReview={letter.needs_human_review}
                approved={letter.approved}
              />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
