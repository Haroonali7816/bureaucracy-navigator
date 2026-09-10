import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import client from '../api/client'

export default function UploadPage() {
  const [dragActive, setDragActive] = useState(false)
  const [status, setStatus] = useState('idle') // idle | uploading | processing | error
  const [error, setError] = useState(null)
  const fileInputRef = useRef(null)
  const navigate = useNavigate()

  async function uploadFile(file) {
    if (file.type !== 'image/png') {
      setError('Please upload a PNG image.')
      return
    }
    setError(null)
    setStatus('uploading')

    const formData = new FormData()
    formData.append('file', file)

    try {
      // Deliberately NOT setting Content-Type here: FormData needs a browser-generated
      // multipart boundary (e.g. "boundary=----WebKitFormBoundary...") to mark where the
      // file field starts/ends in the request body. Hardcoding 'multipart/form-data'
      // without one leaves the server unable to parse the body at all.
      const response = await client.post('/letters', formData)
      const { letter_id, job_id } = response.data
      setStatus('processing')
      await pollJob(job_id)
      navigate(`/letters/${letter_id}`)
    } catch (err) {
      // err.message is set to a friendly cold-start explanation by the response
      // interceptor in api/client.js when this was a network error, so prefer it
      // over the generic fallback whenever the server didn't send back a real response.
      setError(err.response?.data?.detail || err.message || 'Upload failed')
      setStatus('error')
    }
  }

  function pollJob(jobId) {
    const MAX_ATTEMPTS = 60 // 60 * 2s = 2 minutes, then give up and surface an error
    let attempts = 0

    return new Promise((resolve, reject) => {
      const interval = setInterval(async () => {
        attempts += 1
        try {
          const response = await client.get(`/job/${jobId}`)
          const job = response.data
          if (job.status === 'done') {
            clearInterval(interval)
            resolve(job)
          } else if (job.status === 'failed') {
            clearInterval(interval)
            reject(new Error(job.error_message || 'Processing failed'))
          } else if (attempts >= MAX_ATTEMPTS) {
            clearInterval(interval)
            reject(
              new Error(
                'This is taking much longer than expected. Check the dashboard later -- the job may still finish in the background.'
              )
            )
          }
          // otherwise still queued/processing -- keep polling
        } catch (err) {
          clearInterval(interval)
          reject(err)
        }
      }, 2000)
    })
  }

  function handleDrop(e) {
    e.preventDefault()
    setDragActive(false)
    const file = e.dataTransfer.files[0]
    if (file) uploadFile(file)
  }

  function handleFileSelect(e) {
    const file = e.target.files[0]
    if (file) uploadFile(file)
  }

  return (
    <div>
      <h1>Upload a letter</h1>
      <div
        className={`dropzone ${dragActive ? 'dropzone-active' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragActive(true)
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current.click()}
      >
        {status === 'idle' && <p>Drag a PNG here, or click to choose a file</p>}
        {status === 'uploading' && <p>Uploading...</p>}
        {status === 'processing' && (
          <p>Processing... this can take a bit (Gemini is reading the letter)</p>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/png"
          onChange={handleFileSelect}
          hidden
        />
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  )
}
