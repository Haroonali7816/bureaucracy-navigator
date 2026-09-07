import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import client from '../api/client'

const AUTHORITIES = [
  'Ausländerbehörde',
  'Finanzamt',
  'Krankenkasse',
  'University',
  'Bürgeramt',
  'Other',
]
const LETTER_TYPES = [
  'appointment_notice',
  'fee_tax_notice',
  'document_request',
  'deadline_warning',
  'informational',
]

function ConfidenceBadge({ level }) {
  if (!level) return null
  return <span className={`badge badge-${level}`}>{level}</span>
}

export default function LetterDetail() {
  const { letterId } = useParams()
  const navigate = useNavigate()

  const [letter, setLetter] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [draft, setDraft] = useState(null)
  const [draftLoading, setDraftLoading] = useState(false)

  const [authority, setAuthority] = useState('')
  const [letterType, setLetterType] = useState('')
  const [consequences, setConsequences] = useState('')
  const [contactInfo, setContactInfo] = useState('')
  const [requiredActions, setRequiredActions] = useState('')
  const [requiredDocuments, setRequiredDocuments] = useState('')

  useEffect(() => {
    loadLetter()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [letterId])

  async function loadLetter() {
    setLoading(true)
    setError(null)
    try {
      const response = await client.get(`/letters/${letterId}`)
      const data = response.data
      setLetter(data)
      setAuthority(data.authority || '')
      setLetterType(data.letter_type || '')
      setConsequences(data.consequences || '')
      setContactInfo(data.contact_info || '')
      setRequiredActions((data.required_actions || []).join('\n'))
      setRequiredDocuments((data.required_documents || []).join('\n'))
      if (data.draft_reply) setDraft(data.draft_reply)
    } catch (err) {
      console.error(err)
      setError('Could not load this letter')
    } finally {
      setLoading(false)
    }
  }

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const payload = {
        authority,
        letter_type: letterType,
        consequences,
        contact_info: contactInfo,
        required_actions: requiredActions
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean),
        required_documents: requiredDocuments
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean),
      }
      const response = await client.patch(`/letters/${letterId}`, payload)
      setLetter(response.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  async function handleApprove() {
    setError(null)
    try {
      await client.post(`/letters/${letterId}/approve`)
      await loadLetter()
    } catch (err) {
      setError(err.response?.data?.detail || 'Approve failed')
    }
  }

  async function handleDownloadIcs() {
    setError(null)
    try {
      const response = await client.get(`/letters/${letterId}/ics`, {
        responseType: 'blob',
      })
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.download = `letter_${letterId}.ics`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error(err)
      setError(
        'Could not download .ics (letter may need no deadlines, or not be approved yet)'
      )
    }
  }

  async function handleGenerateDraft() {
    setDraftLoading(true)
    setError(null)
    try {
      const response = await client.post(`/letters/${letterId}/draft`)
      setDraft(response.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Draft generation failed')
    } finally {
      setDraftLoading(false)
    }
  }

  if (loading) return <p>Loading...</p>
  if (!letter) return <p className="error">{error || 'Letter not found'}</p>

  const fc = letter.field_confidence || {}
  const locked = letter.approved

  return (
    <div>
      <button onClick={() => navigate('/')}>&larr; Back to dashboard</button>
      <h1>Letter #{letter.letter_id}</h1>

      {letter.job_status !== 'done' && (
        <p>This letter is still being processed (status: {letter.job_status}).</p>
      )}

      {letter.needs_human_review && !letter.approved && (
        <p className="warning">
          The self-check flagged this extraction for human review — check the
          fields below carefully before approving.
        </p>
      )}

      {letter.job_status === 'done' && (
        <form onSubmit={handleSave}>
          <label>
            Authority <ConfidenceBadge level={fc.authority} />
            <select
              value={authority}
              onChange={(e) => setAuthority(e.target.value)}
              disabled={locked}
            >
              {AUTHORITIES.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>

          <label>
            Letter type <ConfidenceBadge level={fc.letter_type} />
            <select
              value={letterType}
              onChange={(e) => setLetterType(e.target.value)}
              disabled={locked}
            >
              {LETTER_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>

          <div>
            <p>
              Deadlines <ConfidenceBadge level={fc.deadlines} />
            </p>
            <ul>
              {(letter.deadlines || []).map((d, i) => (
                <li key={i}>
                  {d.date} — {d.description}
                </li>
              ))}
              {(letter.deadlines || []).length === 0 && <li>No deadlines extracted.</li>}
            </ul>
            <p className="hint">(Editing deadline dates isn't wired up yet — read-only for now.)</p>
          </div>

          <label>
            Required actions (one per line) <ConfidenceBadge level={fc.required_actions} />
            <textarea
              value={requiredActions}
              onChange={(e) => setRequiredActions(e.target.value)}
              disabled={locked}
              rows={4}
            />
          </label>

          <label>
            Required documents (one per line) <ConfidenceBadge level={fc.required_documents} />
            <textarea
              value={requiredDocuments}
              onChange={(e) => setRequiredDocuments(e.target.value)}
              disabled={locked}
              rows={4}
            />
          </label>

          <label>
            Consequences <ConfidenceBadge level={fc.consequences} />
            <textarea
              value={consequences}
              onChange={(e) => setConsequences(e.target.value)}
              disabled={locked}
              rows={3}
            />
          </label>

          <label>
            Contact info <ConfidenceBadge level={fc.contact_info} />
            <textarea
              value={contactInfo}
              onChange={(e) => setContactInfo(e.target.value)}
              disabled={locked}
              rows={2}
            />
          </label>

          {letter.review_reasoning && letter.review_reasoning.length > 0 && (
            <div className="reasoning">
              <p>Self-check notes:</p>
              <ul>
                {letter.review_reasoning.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          {error && <p className="error">{error}</p>}

          {!locked && (
            <div className="actions">
              <button type="submit" disabled={saving}>
                {saving ? 'Saving...' : 'Save changes'}
              </button>
              <button type="button" onClick={handleApprove}>
                Approve
              </button>
            </div>
          )}
        </form>
      )}

      {letter.approved && (
        <div className="actions">
          <p className="success">This letter is approved.</p>
          <button onClick={handleDownloadIcs}>Download .ics</button>
          <button onClick={handleGenerateDraft} disabled={draftLoading}>
            {draftLoading ? 'Loading draft...' : draft ? 'Refresh draft view' : 'Generate draft reply'}
          </button>
        </div>
      )}

      {draft && (
        <div className="draft-card">
          <h2>Draft reply</h2>
          <p>
            <strong>Subject:</strong> {draft.subject}
          </p>
          <p>
            <strong>Summary (EN):</strong> {draft.summary_en}
          </p>
          <pre>{draft.body_de}</pre>
        </div>
      )}
    </div>
  )
}
