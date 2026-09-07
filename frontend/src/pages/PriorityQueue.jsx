import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import client from '../api/client'

export default function PriorityQueue() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const response = await client.get('/priorities')
        if (!cancelled) setData(response.data)
      } catch (err) {
        console.error(err)
        if (!cancelled) setError('Could not load priority queue')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  if (loading) return <p>Loading...</p>
  if (error) return <p className="error">{error}</p>

  const conflictedLetterIds = new Set()
  data.conflicts.forEach((c) => {
    conflictedLetterIds.add(c.letter_id_a)
    conflictedLetterIds.add(c.letter_id_b)
  })

  return (
    <div>
      <h1>Priority queue</h1>
      {data.queue.length === 0 && (
        <p>Nothing pending — every unapproved letter has been handled.</p>
      )}
      <ol className="priority-list">
        {data.queue.map((item) => (
          <li
            key={item.letter_id}
            className={conflictedLetterIds.has(item.letter_id) ? 'conflict' : ''}
          >
            <Link to={`/letters/${item.letter_id}`}>
              <strong>{item.authority}</strong> — {item.deadline_description} (
              {item.deadline_date})
              <span className="score">
                score {item.score} · {item.days_left} days left
              </span>
            </Link>
            {conflictedLetterIds.has(item.letter_id) && (
              <span className="conflict-flag">⚠ conflict</span>
            )}
          </li>
        ))}
      </ol>

      {data.conflicts.length > 0 && (
        <div className="conflicts">
          <h2>Flagged conflicts</h2>
          <ul>
            {data.conflicts.map((c, i) => (
              <li key={i}>
                Letter #{c.letter_id_a} vs #{c.letter_id_b} — {c.reason}: {c.detail}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
